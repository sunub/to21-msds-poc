"""추출 모델 LoRA·QLoRA 학습 (11/03 F, 11/04 메모리 점검). GPU 서버(RunPod)에서 저장소 최상위 폴더 기준으로 돌린다.

    pip install -r finetune/requirements.txt
    python finetune/train_qlora.py --config finetune/configs/<모델>.yaml --data data/finetune/<이름> --check-data    길이만 본다
    python finetune/train_qlora.py --config finetune/configs/<모델>.yaml --data data/finetune/<이름> --check-memory  한 걸음만 재 본다
    python finetune/train_qlora.py --config finetune/configs/<모델>.yaml --data data/finetune/<이름>                 학습

입력  <data>/train.jsonl·val.jsonl (backend/scripts/ft_build_data.py). 예시마다 messages = system·user·assistant
출력  <output_dir>/<run_name>/
        adapter/            LoRA 가중치와 토크나이저 (vLLM --lora-modules, merge_adapter.py가 읽는다)
        train_info.yaml     설정, 데이터 기록(data_info.yaml), 길이 통계, 뺀 예시, 손실, 매개변수 크기, LoRA가 붙은 층,
                            최대 GPU 메모리, 라이브러리 버전, GPU, 걸린 시간
        log_history.json    단계별 손실·학습률
        check_memory.yaml   --check-memory 결과(가장 긴 예시 한 걸음의 최대 메모리·걸린 시간)

메모리 (11/04)
- transformers 5는 MoE 전문가를 층마다 큰 3차원 묶음 하나로 둔다. bitsandbytes 4bit는 nn.Linear만 바꾸므로 전문가는 bf16 그대로다.
  그래서 MoE 모델은 4bit로 올려도 거의 줄지 않는다(Qwen3-30B-A3B 전문가 약 58GB). MoE는 4bit 없이 bf16 LoRA로 돌린다(모델별 설정).
- peft의 4bit 준비 함수는 4bit가 아닌 bf16 매개변수를 모두 fp32로 바꾼다. 큰 bf16 묶음이 있으면 두 배가 되어 넘치므로
  늘어나는 크기가 quantization.upcast_max_gb보다 크면 바꾸지 않는다(quantization.upcast_rest: auto).
- 손실은 정답 토큰에만 걸리므로 출력 확률(logits)도 정답 자리만 만든다(train.completion_logits_only). 어휘가 15만~25만이라
  16k 토큰 전체의 logits는 fp32로 10~16GB다. 손실 값은 전체로 만들 때와 같다.
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

def deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_config(path: Path, overrides: dict) -> dict:
    """설정을 읽는다. 'base: <같은 폴더의 설정 파일>'이 있으면 그 파일을 먼저 읽고 이 파일의 값으로 덮는다(모델별 설정)."""
    path = Path(path)
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if cfg.get("base"):
        cfg = deep_merge(load_config(path.parent / cfg.pop("base"), {}), cfg)
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
    """오른쪽을 채운다. completion_logits_only면 logits_to_keep(끝에서 몇 자리의 logits를 만들지)도 넣는다:
    묶음에서 가장 앞선 정답 토큰 바로 앞 자리부터 끝까지. 그 앞 자리의 logits는 손실에 쓰이지 않는다."""

    def __init__(self, pad_id: int, completion_logits_only: bool = False):
        self.pad_id, self.completion_logits_only = pad_id, completion_logits_only

    def __call__(self, batch: list[dict]) -> dict:
        import torch
        n = max(len(b["input_ids"]) for b in batch)
        ids = [b["input_ids"] + [self.pad_id] * (n - len(b["input_ids"])) for b in batch]
        labels = [b["labels"] + [IGNORE] * (n - len(b["labels"])) for b in batch]
        mask = [[1] * len(b["input_ids"]) + [0] * (n - len(b["input_ids"])) for b in batch]
        out = {"input_ids": torch.tensor(ids), "labels": torch.tensor(labels), "attention_mask": torch.tensor(mask)}
        if self.completion_logits_only:
            first = min(next((i for i, v in enumerate(lab) if v != IGNORE), n) for lab in labels)
            out["logits_to_keep"] = max(n - first + 1, 1)
        return out


def completion_loss(outputs, labels, num_items_in_batch=None):
    """정답 토큰의 교차 엔트로피. 모델이 끝 k자리 logits만 냈으면(logits_to_keep) labels 끝 k-1자리와 맞춘다.
    k가 전체 길이면 보통의 다음 토큰 손실과 같다. 학습 때는 합을 num_items_in_batch(쌓는 단계 전체의 정답 토큰 수)로 나누고,
    검증 때(None)는 이 묶음의 평균이다. 모델이 labels로 내는 손실과 같은 값이다."""
    import torch
    logits = outputs["logits"] if isinstance(outputs, dict) else outputs[0]
    k = logits.shape[1]
    labels = labels.to(logits.device)
    pred, tgt = logits[:, :-1, :], labels[:, labels.shape[1] - k + 1:]
    loss = torch.nn.functional.cross_entropy(pred.float().reshape(-1, pred.shape[-1]), tgt.reshape(-1),
                                             ignore_index=IGNORE, reduction="sum")
    n = num_items_in_batch if num_items_in_batch is not None else (tgt != IGNORE).sum().clamp(min=1)
    return loss / (n.to(loss.device) if torch.is_tensor(n) else n)


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
    if torch.cuda.is_available():                        # 한 장이면 GPU 0에 바로 올린다. 여러 장에 나누려면 device_map: auto
        kw["device_map"] = cfg.get("device_map") or {"": 0}
    try:
        return AutoModelForCausalLM.from_pretrained(cfg["base_model"], **kw)
    except ValueError:                                   # 글 전용 클래스가 없는 멀티모달 체크포인트
        from transformers import AutoModelForImageTextToText
        return AutoModelForImageTextToText.from_pretrained(cfg["base_model"], **kw)


def _is_4bit(p) -> bool:
    return p.__class__.__name__ == "Params4bit"


def upcast_plan(model, cfg: dict) -> tuple[bool, float]:
    """4bit로 줄지 않은 bf16·fp16 매개변수를 fp32로 바꿀지와, 바꾸면 늘어나는 크기(GB).
    quantization.upcast_rest: true·false면 그대로, auto(기본)면 늘어나는 크기가 upcast_max_gb(기본 16) 이하일 때만 바꾼다.
    밀집 모델은 임베딩·정규화 층 정도라 바꾸고(peft 기본), MoE 전문가처럼 큰 묶음이 남은 모델은 bf16 그대로 둔다."""
    import torch
    extra = sum(p.numel() * 2 for p in model.parameters()
                if p.dtype in (torch.float16, torch.bfloat16) and not _is_4bit(p)) / 1e9
    q = cfg.get("quantization") or {}
    mode = q.get("upcast_rest", "auto")
    if isinstance(mode, bool):
        return mode, extra
    return extra <= float(q.get("upcast_max_gb", 16)), extra


def prepare_for_training(model, cfg: dict, use_4bit: bool):
    """기울기 체크포인트를 켜고 원래 가중치를 얼린다. 4bit면 upcast_plan에 따라 peft 준비 함수를 쓰거나(fp32로 바꿈) 건너뛴다."""
    from peft import prepare_model_for_kbit_training

    gc = cfg["train"].get("gradient_checkpointing", True)
    model.config.use_cache = False
    info = {"load_in_4bit": use_4bit, "upcast_rest": False, "upcast_extra_gb": None}
    if use_4bit:
        upcast, extra = upcast_plan(model, cfg)
        info.update(upcast_rest=upcast, upcast_extra_gb=round(extra, 2))
        if upcast:
            model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=gc,
                                                    gradient_checkpointing_kwargs={"use_reentrant": False})
            return model, info
        print(f"참고: 4bit로 줄지 않은 bf16 매개변수가 커서(fp32로 바꾸면 +{extra:.1f}GB) 바꾸지 않고 bf16 그대로 학습합니다."
              " MoE 전문가 묶음이 보통 그렇습니다. 이 경우 4bit로 아끼는 메모리가 적으니 bf16 LoRA(load_in_4bit: false)도 고려합니다.")
    for p in model.parameters():
        p.requires_grad = False
    if gc:
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        model.enable_input_require_grads()
    return model, info


def add_lora(model, cfg: dict, init_adapter: str | None = None):
    """새 LoRA를 붙인다. init_adapter가 있으면 이미 학습한 LoRA를 이어서 학습하도록 불러온다(2단계 학습: 교사 답 → 골드)."""
    from peft import LoraConfig, PeftModel, get_peft_model

    if init_adapter:
        return PeftModel.from_pretrained(model, init_adapter, is_trainable=True)
    lo = cfg["lora"]
    config = LoraConfig(r=lo["r"], lora_alpha=lo["alpha"], lora_dropout=lo.get("dropout", 0.0), bias="none",
                        task_type="CAUSAL_LM", target_modules=lo["target_modules"],
                        exclude_modules=lo.get("exclude_modules"))
    return get_peft_model(model, config)


def param_breakdown(model) -> dict:
    """저장 방식별 매개변수 크기(GB)와 4bit가 아닌 가장 큰 묶음(층 번호는 N으로 모은다)."""
    import re
    by, rest = Counter(), Counter()
    for name, p in model.named_parameters():
        size = p.numel() * p.element_size()
        kind = "4bit" if _is_4bit(p) else str(p.dtype).replace("torch.", "")
        by[kind] += size
        if kind != "4bit":
            rest[re.sub(r"\.\d+\.", ".N.", name.removeprefix("base_model.model."))] += size
    gb = lambda v: round(v / 1e9, 2)                     # noqa: E731
    return {"by_dtype_gb": {k: gb(v) for k, v in by.most_common()}, "total_gb": gb(sum(by.values())),
            "largest_not_4bit_gb": {k: gb(v) for k, v in rest.most_common(4)}}


def lora_coverage(model) -> dict:
    """LoRA가 붙은 곳: 모듈 이름별 수와 글 모델 층 중 붙은 층 수. 층마다 구조가 다른 모델(Qwen3.5·3.6·3.8 계열은
    4층 중 3층이 Gated DeltaNet)은 q/k/v/o만 적으면 일부 층에만 붙는다. 이미지 쪽 층은 세지 않는다."""
    import re
    layers, hit, by = set(), set(), Counter()
    for name, m in model.named_modules():
        if re.search(r"visual|vision", name):
            continue
        mm = re.search(r"\.layers\.(\d+)(?:\.|$)", name)
        if mm:
            layers.add(int(mm.group(1)))
        if len(getattr(m, "lora_A", None) or {}):     # peft LoraLayer
            by[name.rsplit(".", 1)[-1]] += 1
            if mm:
                hit.add(int(mm.group(1)))
    return {"modules": sum(by.values()), "by_name": dict(sorted(by.items())), "layers": len(layers),
            "layers_with_lora": len(hit), "layers_without_lora": sorted(layers - hit)[:12]}


def gpu_gb(peak: bool = False) -> list | None:
    """GPU마다 쓰는(peak면 최대) 메모리 GB. GPU가 없으면 None."""
    import torch
    if not torch.cuda.is_available():
        return None
    f = torch.cuda.max_memory_allocated if peak else torch.cuda.memory_allocated
    return [round(f(i) / 1e9, 1) for i in range(torch.cuda.device_count())]


def print_model_report(params: dict, prep: dict, cov: dict, after_load: list | None) -> None:
    dt = ", ".join(f"{k} {v}GB" for k, v in params["by_dtype_gb"].items())
    print(f"\n매개변수: {dt} (합 {params['total_gb']}GB). 올린 뒤 GPU 메모리: {after_load or '-'}GB")
    print("4bit가 아닌 큰 묶음: " + ", ".join(f"{k} {v}GB" for k, v in params["largest_not_4bit_gb"].items()))
    if prep["load_in_4bit"]:
        print(f"4bit 아닌 부분 fp32 변환: {'함' if prep['upcast_rest'] else '안 함'} (바꾸면 +{prep['upcast_extra_gb']}GB)")
    print(f"LoRA: {cov['modules']}곳 {cov['by_name']}, 글 모델 {cov['layers']}층 중 {cov['layers_with_lora']}층")
    if cov["layers"] and cov["layers_with_lora"] < cov["layers"]:
        print(f"주의: LoRA가 {cov['layers']}층 중 {cov['layers_with_lora']}층에만 붙었습니다(빠진 층 예: {cov['layers_without_lora']})."
              " 층마다 구조가 다른 모델이면 lora.target_modules에 그 층의 투영 이름을 더합니다"
              "(Qwen3.5·3.6·3.8 계열 Gated DeltaNet: in_proj_qkv, in_proj_z, out_proj).")


def check_memory(model, examples: list[dict], collator, cfg: dict) -> dict:
    """가장 긴 예시 하나로 순전파·역전파를 두 번 해(첫 번은 준비 운동) 최대 GPU 메모리와 한 걸음 시간을 잰다. 학습은 하지 않는다.
    최적화기 상태(LoRA 가중치만)는 작아 학습 때 최대 메모리는 이 값보다 1~3GB 더 나올 수 있다."""
    import contextlib
    import torch
    x = max(examples, key=lambda e: len(e["input_ids"]))
    batch = collator([x])
    labels = batch.pop("labels")
    dev = model.get_input_embeddings().weight.device
    batch = {k: v.to(dev) if torch.is_tensor(v) else v for k, v in batch.items()}
    cuda = torch.cuda.is_available()
    bf16 = cuda and cfg["train"].get("bf16", True)
    model.train()
    secs, loss = [], None
    for i in range(2):
        if cuda:
            torch.cuda.synchronize()
            if i == 1:
                for d in range(torch.cuda.device_count()):
                    torch.cuda.reset_peak_memory_stats(d)
        t = time.time()
        with torch.autocast("cuda", dtype=torch.bfloat16) if bf16 else contextlib.nullcontext():
            out = model(**batch) if "logits_to_keep" in batch else model(**batch, labels=labels)
            loss = completion_loss(out, labels) if "logits_to_keep" in batch else out.loss
        loss.backward()
        model.zero_grad(set_to_none=True)
        if cuda:
            torch.cuda.synchronize()
        secs.append(round(time.time() - t, 2))
    total_tokens = sum(len(e["input_ids"]) for e in examples)
    epochs = float(cfg["train"].get("epochs", 1))
    props = [torch.cuda.get_device_properties(d).total_memory / 1e9 for d in range(torch.cuda.device_count())] if cuda else None
    return {"example_id": x["id"], "tokens": len(x["input_ids"]), "completion_tokens": x["completion_tokens"],
            "logits_to_keep": batch.get("logits_to_keep"), "loss": round(float(loss.detach()), 4), "seconds_per_step": secs,
            "peak_gb": gpu_gb(peak=True), "gpu_total_gb": [round(v, 1) for v in props] if props else None,
            # 한 걸음 시간이 길이에 비례한다고 본 대략값(주의 계산은 길이 제곱이라 긴 예시가 많으면 더 걸린다)
            "rough_train_hours": round(secs[-1] * total_tokens / len(x["input_ids"]) * epochs / 3600, 2)}


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
    ap.add_argument("--check-memory", action="store_true",
                    help="모델을 올리고 가장 긴 예시로 한 걸음만 돌려 최대 GPU 메모리와 시간을 잰다(학습·저장 안 함)")
    ap.add_argument("--max-steps", type=int, default=-1, help="시험용: 이 단계에서 멈춘다")
    ap.add_argument("--init-adapter", help="이미 학습한 LoRA 폴더에서 이어서 학습한다(lora 설정은 그 폴더의 것을 쓴다)")
    ap.add_argument("--no-4bit", action="store_true", help="4bit 양자화 없이 올린다(CPU 시험용. GPU에서는 quantization.load_in_4bit=false와 같다)")
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
    tr = cfg["train"]
    collator = Collator(tok.pad_token_id, bool(tr.get("completion_logits_only", True)))
    t0 = time.time()
    model = load_model(cfg, use_4bit)
    after_load = gpu_gb()
    model, prep = prepare_for_training(model, cfg, use_4bit)
    model = add_lora(model, cfg, a.init_adapter)
    model.print_trainable_parameters()
    params, cov = param_breakdown(model), lora_coverage(model)
    print_model_report(params, prep, cov, after_load)
    model_info = {"after_load_gb": after_load, "params": params, "prep": prep, "lora": cov,
                  "experts_implementation": getattr(model.config, "_experts_implementation", None),   # MoE: grouped_mm이 빠르다
                  "device_map": sorted({str(v) for v in (getattr(model, "hf_device_map", None) or {}).values()}) or None,
                  "completion_logits_only": collator.completion_logits_only, "load_seconds": round(time.time() - t0)}

    if a.check_memory:
        mem = check_memory(model, train_x + val_x, collator, cfg)
        info = {"run_name": cfg["run_name"], "base_model": cfg["base_model"], "max_seq_len": max_len,
                "model": model_info, "check": mem, "versions": versions(), "git_commit": git_commit()}
        (out / "check_memory.yaml").write_text(yaml.safe_dump(info, allow_unicode=True, sort_keys=False), encoding="utf-8")
        total = mem["gpu_total_gb"]
        print(f"\n가장 긴 예시 {mem['example_id']} ({mem['tokens']}토큰, 정답 {mem['completion_tokens']}): "
              f"최대 GPU 메모리 {mem['peak_gb'] or '-'}GB / {total or '-'}GB, 한 걸음 {mem['seconds_per_step'][-1]}초, "
              f"학습 대략 {mem['rough_train_hours']}시간({tr.get('epochs')}에폭)")
        if total and mem["peak_gb"] and max(p / t for p, t in zip(mem["peak_gb"], total)) > 0.92:
            print("주의: 여유가 8% 밑입니다. 학습 중 넘칠 수 있습니다. max_seq_len을 줄이거나 더 큰 GPU를 씁니다.")
        print(f"기록: {out / 'check_memory.yaml'}")
        return

    wb = start_wandb(cfg, train_stat, val_stat, data_info)
    if wb:
        wb.summary.update({"model/params_gb": params["by_dtype_gb"], "model/lora_layers": cov["layers_with_lora"],
                           "model/layers": cov["layers"], "model/after_load_gb": after_load})
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
        prediction_loss_only=True,                       # 검증 때 logits를 모으지 않는다(긴 예시 logits는 수 GB)
        seed=tr.get("seed", 2026), use_cpu=not cuda,
    )
    trainer = Trainer(model=model, args=args, train_dataset=ListDataset(train_x),
                      eval_dataset=ListDataset(val_x) if val_x else None, data_collator=collator,
                      compute_loss_func=completion_loss if collator.completion_logits_only else None)
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
        "model": model_info, "peak_gb": gpu_gb(peak=True), "init_adapter": a.init_adapter,
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
                           "seconds": info["seconds"], "peak_gb": info["peak_gb"]})
        wb.finish()
        print(f"W&B: {info['wandb_url'] or '오프라인 기록(wandb sync로 올림)'}")


if __name__ == "__main__":
    main()
