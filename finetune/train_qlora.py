"""추출 모델 QLoRA 학습 (11/03 F). GPU 서버(RunPod A100 80GB 한 장)에서 저장소 최상위 폴더 기준으로 돌린다.

    pip install -r finetune/requirements.txt
    python finetune/train_qlora.py --config finetune/configs/qlora.yaml --data data/finetune/<이름> --check-data   길이만 본다
    python finetune/train_qlora.py --config finetune/configs/qlora.yaml --data data/finetune/<이름>                학습

입력  <data>/train.jsonl·val.jsonl (backend/scripts/ft_build_data.py). 예시마다 messages = system·user·assistant
출력  <output_dir>/<run_name>/
        adapter/            LoRA 가중치와 토크나이저 (vLLM --lora-modules, merge_adapter.py가 읽는다)
        train_info.yaml     설정, 데이터 기록(data_info.yaml), 길이 통계, 뺀 예시, 손실, 라이브러리 버전, GPU, 걸린 시간
        log_history.json    단계별 손실·학습률
W&B(선택, 설정 wandb.enabled): 손실·학습률·기울기 크기·GPU 사용량과 설정·데이터 통계를 실시간으로 본다.
  학습 글(안내문·MSDS 원문)과 모델·체크포인트는 보내지 않는다(D-47). 키는 RunPod 환경변수 WANDB_API_KEY로만 둔다.

학습 글을 만드는 방법
- 프롬프트는 추론 때와 같다: 대화 틀(apply_chat_template)에 system·user만 넣고 add_generation_prompt=True로 만든 글.
  vLLM도 같은 틀로 만든 글을 특수 토큰 추가 없이 토큰화한다. chat_template_kwargs도 추론 설정과 같게 둔다.
- 정답은 전체 대화(system·user·assistant)를 틀로 만든 글에서 프롬프트 뒤 부분이다(끝 토큰 <|im_end|> 등 포함, how=template).
  틀이 마지막 답을 프롬프트와 다르게 감싸 앞부분이 맞지 않으면(예: 생각 모드 끈 프롬프트에만 빈 <think>가 붙는 틀)
  프롬프트 + 정답 + eos로 쓴다(how=eos). 어느 쪽이든 프롬프트 토큰은 추론 때와 같다.
- 손실은 정답 토큰에만 건다(프롬프트 토큰은 -100).
- max_seq_len보다 긴 예시는 자르지 않고 뺀다. 정답 끝이 잘리면 끝나지 않는 글을 배운다.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import yaml

IGNORE = -100


# ── 설정·데이터 ────────────────────────────────────────

def load_config(path: Path, overrides: dict) -> dict:
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    for key, value in overrides.items():          # "train.lr" 같은 점 경로
        node = cfg
        *parents, last = key.split(".")
        for p in parents:
            node = node.setdefault(p, {})
        node[last] = value
    return cfg


def read_jsonl(path: Path) -> list[dict]:
    if not Path(path).exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class ChatRenderer:
    """대화 틀로 글을 만든다. 토크나이저에 틀이 없는 모델(일부 멀티모달)은 프로세서의 틀을 쓴다."""

    def __init__(self, tokenizer, base_model: str, kwargs: dict, trust_remote_code: bool = False):
        self.tok, self.kwargs, self.proc = tokenizer, dict(kwargs or {}), None
        if not getattr(tokenizer, "chat_template", None):
            from transformers import AutoProcessor
            self.proc = AutoProcessor.from_pretrained(base_model, trust_remote_code=trust_remote_code)

    def render(self, messages: list[dict], add_generation_prompt: bool) -> str:
        if self.proc is None:
            return self.tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=add_generation_prompt,
                                                **self.kwargs)
        parts = [{"role": m["role"], "content": [{"type": "text", "text": m["content"]}]} for m in messages]
        return self.proc.apply_chat_template(parts, tokenize=False, add_generation_prompt=add_generation_prompt,
                                             **self.kwargs)


def encode(example: dict, renderer: ChatRenderer) -> dict:
    """예시 하나 → input_ids·labels. how: 'template'(틀로 정답 부분을 잘라냄) 또는 'eos'(정답 + eos 토큰)."""
    tok = renderer.tok
    msgs = example["messages"]
    if msgs[-1]["role"] != "assistant":
        raise ValueError(f"{example.get('id')}: 마지막 메시지가 assistant가 아님")
    answer = msgs[-1]["content"]
    prompt = renderer.render(msgs[:-1], add_generation_prompt=True)
    full = renderer.render(msgs, add_generation_prompt=False)
    completion, how = full[len(prompt):].rstrip("\n"), "template"
    if not full.startswith(prompt) or answer not in completion or completion.endswith(answer):
        completion, how = answer + (tok.eos_token or ""), "eos"   # 앞부분이 다르거나 끝 토큰이 없으면
    p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
    c_ids = tok(completion, add_special_tokens=False)["input_ids"]
    return {"id": example.get("id"), "section": example.get("section"), "input_ids": p_ids + c_ids,
            "labels": [IGNORE] * len(p_ids) + c_ids, "prompt_tokens": len(p_ids), "completion_tokens": len(c_ids),
            "how": how}


def encode_all(examples: list[dict], renderer: ChatRenderer, max_len: int) -> tuple[list[dict], dict]:
    kept, too_long, how = [], [], Counter()
    for e in examples:
        x = encode(e, renderer)
        how[x["how"]] += 1
        (kept if len(x["input_ids"]) <= max_len else too_long).append(x)
    return kept, {"kept": len(kept), "too_long": len(too_long), "too_long_ids": [x["id"] for x in too_long][:20],
                  "how": dict(how), "lengths": length_stats(kept + too_long)}


def length_stats(xs: list[dict]) -> dict:
    """항별 전체·정답 토큰 수(중앙값·최대). max_seq_len을 정할 때 본다."""
    def summary(vals):
        vals = sorted(vals)
        return {"n": len(vals), "median": int(statistics.median(vals)), "p95": vals[int(0.95 * (len(vals) - 1))],
                "max": vals[-1]} if vals else {}
    by = {}
    for sec in sorted({x["section"] for x in xs}, key=lambda s: (s is None, s)):
        ys = [x for x in xs if x["section"] == sec]
        by[str(sec)] = {"total": summary([len(y["input_ids"]) for y in ys]),
                        "completion": summary([y["completion_tokens"] for y in ys])}
    by["all"] = {"total": summary([len(x["input_ids"]) for x in xs]),
                 "completion": summary([x["completion_tokens"] for x in xs])}
    return by


class Collator:
    def __init__(self, pad_id: int):
        self.pad_id = pad_id

    def __call__(self, batch: list[dict]) -> dict:
        import torch
        n = max(len(b["input_ids"]) for b in batch)
        ids = [b["input_ids"] + [self.pad_id] * (n - len(b["input_ids"])) for b in batch]
        labels = [b["labels"] + [IGNORE] * (n - len(b["labels"])) for b in batch]
        mask = [[1] * len(b["input_ids"]) + [0] * (n - len(b["input_ids"])) for b in batch]
        return {"input_ids": torch.tensor(ids), "labels": torch.tensor(labels), "attention_mask": torch.tensor(mask)}


class ListDataset:
    def __init__(self, rows: list[dict]):
        self.rows = rows

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        return self.rows[i]


# ── 모델 ───────────────────────────────────────────────

def load_model(cfg: dict, use_4bit: bool):
    import torch
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig

    kw = {"dtype": torch.bfloat16 if cfg["train"].get("bf16", True) else torch.float32,
          "trust_remote_code": cfg.get("trust_remote_code", False)}
    if cfg.get("attn_implementation"):
        kw["attn_implementation"] = cfg["attn_implementation"]
    if use_4bit:
        q = cfg.get("quantization") or {}
        kw["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type=q.get("quant_type", "nf4"),
            bnb_4bit_use_double_quant=q.get("double_quant", True), bnb_4bit_compute_dtype=torch.bfloat16)
        kw["device_map"] = {"": 0}
    try:
        return AutoModelForCausalLM.from_pretrained(cfg["base_model"], **kw)
    except ValueError:                                   # 글 전용 클래스가 없는 멀티모달 체크포인트
        from transformers import AutoModelForImageTextToText
        return AutoModelForImageTextToText.from_pretrained(cfg["base_model"], **kw)


def add_lora(model, cfg: dict, use_4bit: bool):
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

    gc = cfg["train"].get("gradient_checkpointing", True)
    model.config.use_cache = False
    if use_4bit:
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=gc,
                                                gradient_checkpointing_kwargs={"use_reentrant": False})
    elif gc:
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        model.enable_input_require_grads()
    lo = cfg["lora"]
    config = LoraConfig(r=lo["r"], lora_alpha=lo["alpha"], lora_dropout=lo.get("dropout", 0.0), bias="none",
                        task_type="CAUSAL_LM", target_modules=lo["target_modules"],
                        exclude_modules=lo.get("exclude_modules"))
    return get_peft_model(model, config)


# ── 기록 ───────────────────────────────────────────────

def versions() -> dict:
    out = {"python": platform.python_version()}
    for name in ("torch", "transformers", "peft", "bitsandbytes", "accelerate"):
        try:
            out[name] = str(__import__(name).__version__)   # torch는 str을 상속한 버전 객체라 yaml이 못 쓴다
        except Exception:      # 없는 라이브러리(CPU 시험의 bitsandbytes 등)
            out[name] = None
    try:
        import torch
        out["gpu"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    except Exception:
        out["gpu"] = None
    return out


def git_commit() -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def start_wandb(cfg: dict, train_stat: dict, val_stat: dict, data_info: dict | None):
    """W&B 실행을 연다(설정 wandb.enabled가 참일 때만). 열면 Trainer가 같은 실행에 손실·학습률·GPU 사용량을 남긴다.
    보내는 것: 설정, 예시 수·뺀 수·길이 통계(숫자), 학생 설정·교사 모델 이름. 학습 글과 모델 파일은 보내지 않는다(D-47).
    WANDB_MODE=offline이면 RunPod 디스크에만 남기고 나중에 `wandb sync`로 올린다."""
    w = cfg.get("wandb") or {}
    if not w.get("enabled"):
        return None
    try:
        import wandb
    except ImportError:
        sys.exit("wandb가 없습니다: pip install -r finetune/requirements.txt (안 쓰려면 --set wandb.enabled=false)")
    os.environ["WANDB_LOG_MODEL"] = "false"     # 체크포인트를 올리지 않는다
    os.environ["WANDB_WATCH"] = "false"         # 가중치·기울기 분포를 올리지 않는다
    di = data_info or {}
    summary = {"train_kept": train_stat["kept"], "train_too_long": train_stat["too_long"], "val_kept": val_stat["kept"],
               "val_too_long": val_stat["too_long"], "answer_cut": train_stat["how"],
               "tokens_all": train_stat["lengths"].get("all"),
               "student_tag": di.get("student_tag"), "rows_sections": di.get("rows_sections"),
               "json_mode": di.get("json_mode"), "prompt_version": di.get("prompt_version"),
               "teacher_models": [t.get("model_tag") for t in di.get("teacher_runs") or []],
               "examples_by_section": di.get("sections"), "dropped_when_building": di.get("dropped")}
    run = wandb.init(project=w.get("project") or "to21-msds-qlora", entity=w.get("entity") or None,
                     name=cfg["run_name"], tags=list(w.get("tags") or []),
                     config={k: cfg.get(k) for k in ("base_model", "chat_template_kwargs", "max_seq_len", "quantization",
                                                     "lora", "train")} | {"data": summary})
    rows = [[sec, s["total"]["n"], s["total"]["median"], s["total"]["p95"], s["total"]["max"],
             s["completion"]["median"], s["completion"]["max"]]
            for sec, s in train_stat["lengths"].items() if s["total"]]
    run.log({"data/lengths": wandb.Table(columns=["항", "예시", "전체 중앙값", "전체 95%", "전체 최대", "정답 중앙값", "정답 최대"],
                                         data=rows)})
    return run


def print_lengths(stats: dict, max_len: int) -> None:
    print(f"\n예시 길이(토큰). max_seq_len {max_len}")
    print("항   예시  전체 중앙값  전체 95%  전체 최대  정답 중앙값  정답 최대")
    for sec, s in stats.items():
        t, c = s["total"], s["completion"]
        if t:
            print(f"{sec:>4} {t['n']:>5} {t['median']:>10} {t['p95']:>9} {t['max']:>9} {c['median']:>11} {c['max']:>9}")


# ── 실행 ───────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="finetune/configs/qlora.yaml")
    ap.add_argument("--data", required=True, help="train.jsonl·val.jsonl이 있는 폴더")
    ap.add_argument("--check-data", action="store_true", help="토크나이저만 받아 길이와 뺄 예시를 보고 끝낸다(GPU 불필요)")
    ap.add_argument("--set", nargs="*", default=[], metavar="KEY=VALUE", help="설정 덮어쓰기. 예: train.lr=5e-5 base_model=...")
    ap.add_argument("--max-steps", type=int, default=-1, help="시험용: 이 단계에서 멈춘다")
    ap.add_argument("--no-4bit", action="store_true", help="시험용(CPU): 4bit 양자화 없이 올린다")
    a = ap.parse_args()

    overrides = {k: yaml.safe_load(v) for k, v in (s.split("=", 1) for s in a.set)}
    cfg = load_config(Path(a.config), overrides)
    data = Path(a.data)
    train_rows, val_rows = read_jsonl(data / "train.jsonl"), read_jsonl(data / "val.jsonl")
    if not train_rows:
        sys.exit(f"학습 예시가 없습니다: {data / 'train.jsonl'}")

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(cfg["base_model"], trust_remote_code=cfg.get("trust_remote_code", False))
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    renderer = ChatRenderer(tok, cfg["base_model"], cfg.get("chat_template_kwargs"), cfg.get("trust_remote_code", False))
    max_len = int(cfg["max_seq_len"])
    train_x, train_stat = encode_all(train_rows, renderer, max_len)
    val_x, val_stat = encode_all(val_rows, renderer, max_len)
    print(f"학습 {train_stat['kept']}개(뺀 긴 예시 {train_stat['too_long']}), 검증 {val_stat['kept']}개"
          f"(뺀 {val_stat['too_long']}). 정답 자르기: {train_stat['how']}")
    print_lengths(train_stat["lengths"], max_len)
    if train_stat["how"].get("eos"):
        print(f"참고: 대화 틀이 마지막 답을 프롬프트와 다르게 감싸 '정답 + eos 토큰({tok.eos_token})'으로 끝을 맞춘 예시가 있습니다."
              " eos 토큰이 추론 때 끝 토큰과 같은지 확인하세요(Qwen 지시형은 <|im_end|>).")
    if a.check_data:
        return

    import torch
    from transformers import Trainer, TrainingArguments

    use_4bit = bool((cfg.get("quantization") or {}).get("load_in_4bit")) and not a.no_4bit
    cuda = torch.cuda.is_available()
    if use_4bit and not cuda:
        sys.exit("4bit(QLoRA)는 NVIDIA GPU가 필요합니다. CPU 시험은 --no-4bit로 돌립니다.")
    out = Path(cfg["output_dir"]) / cfg["run_name"]
    out.mkdir(parents=True, exist_ok=True)
    data_info = yaml.safe_load((data / "data_info.yaml").read_text(encoding="utf-8")) if (data / "data_info.yaml").exists() else None
    wb = start_wandb(cfg, train_stat, val_stat, data_info)
    t0 = time.time()
    model = add_lora(load_model(cfg, use_4bit), cfg, use_4bit)
    model.print_trainable_parameters()
    tr = cfg["train"]
    args = TrainingArguments(
        output_dir=str(out / "checkpoints"), per_device_train_batch_size=tr["batch_size"], per_device_eval_batch_size=1,
        gradient_accumulation_steps=tr["grad_accum"], num_train_epochs=tr["epochs"], max_steps=a.max_steps,
        learning_rate=float(tr["lr"]), lr_scheduler_type=tr.get("scheduler", "cosine"), warmup_steps=tr.get("warmup", 0),
        weight_decay=tr.get("weight_decay", 0.0), max_grad_norm=tr.get("max_grad_norm", 1.0),
        logging_steps=tr.get("logging_steps", 5), logging_first_step=True,
        eval_strategy="steps" if val_x else "no", eval_steps=tr.get("eval_steps", 25),
        save_strategy="steps", save_steps=tr.get("save_steps", 50), save_total_limit=2, save_only_model=True,
        bf16=bool(tr.get("bf16", True)) and cuda, optim=tr.get("optim", "paged_adamw_8bit") if cuda else "adamw_torch",
        report_to="wandb" if wb else "none", run_name=cfg["run_name"], remove_unused_columns=False,
        seed=tr.get("seed", 2026), use_cpu=not cuda,
    )
    trainer = Trainer(model=model, args=args, train_dataset=ListDataset(train_x),
                      eval_dataset=ListDataset(val_x) if val_x else None, data_collator=Collator(tok.pad_token_id))
    before = trainer.evaluate() if val_x and tr.get("eval_before", True) else None
    result = trainer.train()
    after = trainer.evaluate() if val_x else None
    model.save_pretrained(out / "adapter")
    tok.save_pretrained(out / "adapter")

    info = {
        "run_name": cfg["run_name"], "config": cfg, "data_dir": str(data), "data_info": data_info,
        "train_examples": train_stat, "val_examples": val_stat,
        "eval_loss_before": before.get("eval_loss") if before else None,
        "eval_loss_after": after.get("eval_loss") if after else None,
        "train_loss": result.training_loss, "steps": result.global_step, "seconds": round(time.time() - t0),
        "versions": versions(), "git_commit": git_commit(), "smoke_test": bool(a.no_4bit or a.max_steps > 0),
        "wandb_url": getattr(wb, "url", None) if wb else None,
    }
    (out / "train_info.yaml").write_text(yaml.safe_dump(info, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (out / "log_history.json").write_text(json.dumps(trainer.state.log_history, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n검증 손실 {info['eval_loss_before']} → {info['eval_loss_after']}, 학습 손실 {result.training_loss:.4f}, "
          f"{result.global_step}단계, {info['seconds']}초")
    print(f"LoRA: {out / 'adapter'}")
    if wb:
        wb.summary.update({"eval_loss_before": info["eval_loss_before"], "eval_loss_after": info["eval_loss_after"],
                           "seconds": info["seconds"]})
        wb.finish()
        print(f"W&B: {info['wandb_url'] or '오프라인 기록(wandb sync로 올림)'}")


if __name__ == "__main__":
    main()
