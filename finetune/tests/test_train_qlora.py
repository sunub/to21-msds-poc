"""QLoRA 학습 스크립트 시험 (CPU, 작은 가짜 모델). GPU·인터넷 없이 돈다. transformers·peft·torch가 없으면 건너뛴다.

    python -m pytest finetune/tests -q

- 정답 토큰에만 손실이 걸리고, 프롬프트는 추론 때(add_generation_prompt=True) 글과 같다.
- 밀집 모델(Qwen3)과 MoE 모델(Qwen3-MoE)에서 LoRA가 주의 투영에 붙고 몇 단계 학습해 LoRA 가중치를 저장한다.
- (11/04) 정답 자리 logits만으로 구한 손실이 전체 logits 손실과 같다. 큰 bf16 묶음(MoE 전문가)은 fp32로 바꾸지 않는다.
  층마다 구조가 다른 모델(Qwen3.5-MoE 계열)에서 LoRA가 붙은 층을 센다. --check-memory는 한 걸음만 재고 저장하지 않는다.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

transformers = pytest.importorskip("transformers")
pytest.importorskip("peft")
pytest.importorskip("torch")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import train_qlora as tq  # noqa: E402

# Qwen 계열 ChatML 틀을 줄인 것 (생각 모드 인자를 받는다)
TEMPLATE = (
    "{% for m in messages %}<|im_start|>{{ m.role }}\n{{ m.content }}<|im_end|>\n{% endfor %}"
    "{% if add_generation_prompt %}<|im_start|>assistant\n"
    "{% if enable_thinking is defined and enable_thinking is false %}<think>\n\n</think>\n\n{% endif %}{% endif %}")


def _examples(n=6):
    rows = []
    for i in range(n):
        rows.append({"id": f"D{i}_m0_s03", "section": 3, "messages": [
            {"role": "system", "content": "너는 MSDS 3항 추출기다. 행 형식으로 쓴다."},
            {"role": "user", "content": f"[3항 원문]\np2:L{i} 가상물질 갑 | 1234-56-6 | 10 ~ 20"},
            {"role": "assistant", "content": f"### components\nname | cas_no | content | line\n가상물질 갑 | 1234-56-6 | 10 ~ 20 % | p2:L{i}"}]})
    return rows


@pytest.fixture(scope="module")
def tiny(tmp_path_factory):
    """작은 BPE 토크나이저와 무작위 가중치의 Qwen3·Qwen3-MoE 모델 두 개."""
    from tokenizers import Tokenizer, models, pre_tokenizers, trainers, decoders
    from transformers import PreTrainedTokenizerFast, Qwen3Config, Qwen3ForCausalLM, Qwen3MoeConfig, Qwen3MoeForCausalLM

    root = tmp_path_factory.mktemp("tiny")
    text = [m["content"] for e in _examples() for m in e["messages"]] + ["<think>\n\n</think>"]
    tk = Tokenizer(models.BPE(unk_token="<unk>"))
    tk.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tk.decoder = decoders.ByteLevel()
    special = ["<unk>", "<|endoftext|>", "<|im_start|>", "<|im_end|>"]
    tk.train_from_iterator(text * 5, trainers.BpeTrainer(vocab_size=600, special_tokens=special,
                                                          initial_alphabet=pre_tokenizers.ByteLevel.alphabet()))
    tok = PreTrainedTokenizerFast(tokenizer_object=tk, eos_token="<|im_end|>", pad_token="<|endoftext|>", unk_token="<unk>")
    tok.chat_template = TEMPLATE
    out = {}
    for name, cfg_cls, model_cls, extra in (
            ("dense", Qwen3Config, Qwen3ForCausalLM, {}),
            ("moe", Qwen3MoeConfig, Qwen3MoeForCausalLM, {"num_experts": 4, "num_experts_per_tok": 2,
                                                          "moe_intermediate_size": 32})):
        d = root / name
        cfg = cfg_cls(vocab_size=len(tok), hidden_size=64, intermediate_size=128, num_hidden_layers=2,
                      num_attention_heads=4, num_key_value_heads=2, head_dim=16, max_position_embeddings=512,
                      eos_token_id=tok.eos_token_id, pad_token_id=tok.pad_token_id, **extra)
        model_cls(cfg).save_pretrained(d)
        tok.save_pretrained(d)
        out[name] = d
    return out


def test_정답_토큰에만_손실을_걸고_프롬프트는_추론_글과_같다(tiny):
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(tiny["dense"])
    for kwargs in ({}, {"enable_thinking": False}):
        r = tq.ChatRenderer(tok, str(tiny["dense"]), kwargs)
        e = _examples(1)[0]
        x = tq.encode(e, r)
        assert x["how"] == ("template" if not kwargs else "eos")   # 생각 끈 프롬프트에만 빈 <think>를 붙이는 틀
        prompt = tok.apply_chat_template(e["messages"][:2], tokenize=False, add_generation_prompt=True, **kwargs)
        assert x["input_ids"][:x["prompt_tokens"]] == tok(prompt, add_special_tokens=False)["input_ids"]
        assert all(v == tq.IGNORE for v in x["labels"][:x["prompt_tokens"]])
        answer = tok.decode([v for v in x["labels"] if v != tq.IGNORE])
        assert answer == e["messages"][2]["content"] + "<|im_end|>"          # 끝 토큰까지 배운다


def test_너무_긴_예시는_자르지_않고_뺀다(tiny):
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(tiny["dense"])
    r = tq.ChatRenderer(tok, str(tiny["dense"]), {})
    kept, stat = tq.encode_all(_examples(3), r, max_len=10)
    assert kept == [] and stat["too_long"] == 3 and stat["lengths"]["3"]["total"]["n"] == 3


def _train(tmp_path, model_dir, *extra, env=None):
    """가짜 데이터 6개(학습 4·검증 2)로 2단계 학습. 반환: 실행 결과."""
    data = tmp_path / "data"
    data.mkdir()
    rows = _examples(6)
    (data / "train.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows[:4]), encoding="utf-8")
    (data / "val.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows[4:]), encoding="utf-8")
    (data / "data_info.yaml").write_text("examples: 6\n", encoding="utf-8")
    cmd = [sys.executable, str(HERE.parent / "train_qlora.py"), "--config", str(HERE.parent / "configs" / "qlora.yaml"),
           "--data", str(data), "--no-4bit", "--max-steps", "2",
           "--set", f"base_model={model_dir}", f"output_dir={tmp_path / 'out'}", "run_name=t", "train.bf16=false",
           "train.grad_accum=1", "train.eval_steps=1", "max_seq_len=512", "attn_implementation=eager", *extra]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)


@pytest.mark.parametrize("kind", ["dense", "moe"])
def test_CPU에서_몇_단계_학습하고_LoRA를_저장한다(tiny, tmp_path, kind):
    p = _train(tmp_path, tiny[kind])
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-3000:]
    run = tmp_path / "out" / "t"
    adapter = json.loads((run / "adapter" / "adapter_config.json").read_text(encoding="utf-8"))
    assert set(adapter["target_modules"]) == {"q_proj", "k_proj", "v_proj", "o_proj"}
    import yaml
    info = yaml.safe_load((run / "train_info.yaml").read_text(encoding="utf-8"))
    assert info["steps"] == 2 and info["eval_loss_before"] is not None and info["eval_loss_after"] is not None
    assert info["train_examples"]["how"] == {"template": 4} and info["data_info"] == {"examples": 6}
    assert info["model"]["completion_logits_only"] is True
    assert info["model"]["lora"]["layers"] == info["model"]["lora"]["layers_with_lora"] == 2
    if kind == "dense":                                                    # 합치기도 한 번 확인한다
        merged = tmp_path / "merged"
        p = subprocess.run([sys.executable, str(HERE.parent / "merge_adapter.py"), "--adapter", str(run / "adapter"),
                            "--out", str(merged)], capture_output=True, text=True, timeout=600)
        assert p.returncode == 0, p.stderr[-3000:]
        from transformers import AutoModelForCausalLM, AutoTokenizer
        m = AutoModelForCausalLM.from_pretrained(merged)
        assert not any("lora" in n for n, _ in m.named_parameters()) and AutoTokenizer.from_pretrained(merged).eos_token == "<|im_end|>"


def test_W_B를_켜면_학습_곡선만_남기고_학습_글은_보내지_않는다(tiny, tmp_path):
    pytest.importorskip("wandb")
    env = {**os.environ, "WANDB_MODE": "offline", "WANDB_DIR": str(tmp_path), "WANDB_SILENT": "true"}
    p = _train(tmp_path, tiny["dense"], "wandb.enabled=true", env=env)
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-3000:]
    runs = list((tmp_path / "wandb").glob("offline-run-*"))
    assert len(runs) == 1
    blob = b"".join(f.read_bytes() for f in runs[0].rglob("*") if f.is_file())
    assert b"eval/loss" in blob and b"train/loss" in blob                       # 학습 곡선은 남는다
    for text in ("가상물질 갑", "MSDS 3항 추출기", "3항 원문"):                    # 정답·안내문·원문은 없다 (D-47)
        assert text.encode() not in blob, text
    import yaml
    info = yaml.safe_load((tmp_path / "out" / "t" / "train_info.yaml").read_text(encoding="utf-8"))
    assert info["eval_loss_after"] is not None


# ── 11/04 메모리 점검 ──────────────────────────────────

def test_모델별_설정은_공통_설정을_읽고_다른_값만_덮는다():
    base = tq.load_config(HERE.parent / "configs" / "qlora.yaml", {})
    for name in ("qwen3_30b_a3b", "qwen36_35b_a3b", "qwen38_27b", "qwen35_122b_a10b"):
        cfg = tq.load_config(HERE.parent / "configs" / f"{name}.yaml", {"train.lr": 5e-5})
        assert "base" not in cfg and cfg["run_name"] != base["run_name"] and cfg["train"]["lr"] == 5e-5
        assert cfg["quantization"]["quant_type"] == "nf4" and cfg["train"]["epochs"] == base["train"]["epochs"]
    moe = tq.load_config(HERE.parent / "configs" / "qwen36_35b_a3b.yaml", {})
    assert moe["quantization"]["load_in_4bit"] is False and "in_proj_qkv" in moe["lora"]["target_modules"]
    assert moe["chat_template_kwargs"] == {"enable_thinking": False}
    big = tq.load_config(HERE.parent / "configs" / "qwen35_122b_a10b.yaml", {})
    assert big["device_map"] == "auto" and big["lora"]["target_modules"] == moe["lora"]["target_modules"]


@pytest.mark.parametrize("kind", ["dense", "moe"])
def test_정답_자리_logits만으로_구한_손실이_전체_손실과_같다(tiny, kind):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(tiny[kind])
    model = AutoModelForCausalLM.from_pretrained(tiny[kind], dtype=torch.float32).eval()
    r = tq.ChatRenderer(tok, str(tiny[kind]), {})
    ex = _examples(2)
    ex[1]["messages"][2]["content"] += "\n다른 물질 | 9-9-9 | 1 % | p2:L9"           # 길이가 달라 오른쪽이 채워진다
    xs = [tq.encode(e, r) for e in ex]
    full = tq.Collator(tok.pad_token_id)(xs)
    part = tq.Collator(tok.pad_token_id, completion_logits_only=True)(xs)
    assert part["logits_to_keep"] == part["input_ids"].shape[1] - min(x["prompt_tokens"] for x in xs) + 1
    with torch.no_grad():
        ref = model(**full).loss
        labels = part.pop("labels")
        out = model(**part)
        assert out.logits.shape[1] == part["logits_to_keep"] < full["input_ids"].shape[1]
        got = tq.completion_loss(out, labels)
        n = int((labels[:, 1:] != tq.IGNORE).sum())
        assert torch.allclose(got, ref, atol=1e-5)
        assert torch.allclose(tq.completion_loss(out, labels, num_items_in_batch=torch.tensor(2 * n)), ref / 2, atol=1e-5)


def test_큰_bf16_묶음은_fp32로_바꾸지_않는다(tiny):
    """4bit로 줄지 않은 MoE 전문가를 peft 준비 함수가 fp32로 바꾸면 두 배가 된다(30B-A3B 58GB → 116GB)."""
    import torch
    from transformers import AutoModelForCausalLM
    model = AutoModelForCausalLM.from_pretrained(tiny["moe"], dtype=torch.bfloat16)
    up, extra = tq.upcast_plan(model, {"quantization": {}})
    assert up is True and extra > 0                                         # 작은 묶음이면 바꾼다(peft 기본)
    assert tq.upcast_plan(model, {"quantization": {"upcast_rest": False}})[0] is False
    cfg = {"train": {"gradient_checkpointing": True}, "quantization": {"upcast_max_gb": extra / 2}}
    assert tq.upcast_plan(model, cfg) == (False, extra)
    model, info = tq.prepare_for_training(model, cfg, use_4bit=True)
    experts = [p for n, p in model.named_parameters() if "experts" in n]
    assert info["upcast_rest"] is False and experts and all(p.dtype == torch.bfloat16 for p in experts)
    assert not any(p.requires_grad for p in model.parameters())
    cfg["quantization"]["upcast_rest"] = True                               # 바꾸면 전문가도 fp32가 된다
    model, info = tq.prepare_for_training(AutoModelForCausalLM.from_pretrained(tiny["moe"], dtype=torch.bfloat16), cfg, True)
    assert info["upcast_rest"] is True and all(p.dtype == torch.float32 for n, p in model.named_parameters() if "experts" in n)


def test_층마다_구조가_다른_모델은_LoRA가_붙은_층을_센다():
    """Qwen3.5-MoE 계열(3.6-35B-A3B와 같은 구조): 4층 중 3층이 Gated DeltaNet. q/k/v/o만 적으면 1층에만 붙는다."""
    import torch
    from transformers import Qwen3_5MoeForCausalLM, Qwen3_5MoeTextConfig
    cfg = Qwen3_5MoeTextConfig(vocab_size=128, hidden_size=64, num_hidden_layers=4, num_attention_heads=4,
                               num_key_value_heads=2, head_dim=16, linear_key_head_dim=16, linear_value_head_dim=16,
                               linear_num_key_heads=2, linear_num_value_heads=4, moe_intermediate_size=32,
                               shared_expert_intermediate_size=32, num_experts=4, num_experts_per_tok=2,
                               layer_types=["linear_attention"] * 3 + ["full_attention"])
    lora = {"r": 4, "alpha": 8, "exclude_modules": ".*(visual|vision).*"}
    for targets, want in (([("q_proj"), "k_proj", "v_proj", "o_proj"], 1),
                          (tq.load_config(HERE.parent / "configs" / "qwen36_35b_a3b.yaml", {})["lora"]["target_modules"], 4)):
        m = tq.add_lora(Qwen3_5MoeForCausalLM(cfg).to(torch.float32), {"lora": {**lora, "target_modules": targets}})
        cov = tq.lora_coverage(m)
        assert cov["layers"] == 4 and cov["layers_with_lora"] == want, cov
    assert cov["by_name"] == {"in_proj_qkv": 3, "in_proj_z": 3, "k_proj": 1, "o_proj": 1, "out_proj": 3, "q_proj": 1, "v_proj": 1}


def test_메모리_점검은_가장_긴_예시로_한_걸음만_재고_저장하지_않는다(tiny, tmp_path):
    p = _train(tmp_path, tiny["moe"], "--check-memory")
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-3000:]
    import yaml
    run = tmp_path / "out" / "t"
    info = yaml.safe_load((run / "check_memory.yaml").read_text(encoding="utf-8"))
    assert not (run / "adapter").exists() and not (run / "train_info.yaml").exists()
    c = info["check"]
    assert c["example_id"].endswith("_s03") and c["tokens"] > c["completion_tokens"] > 0       # 길이가 같으면 앞의 것
    assert c["logits_to_keep"] == c["completion_tokens"] + 1 and c["loss"] > 0 and len(c["seconds_per_step"]) == 2
    assert c["peak_gb"] is None and info["model"]["lora"]["layers_with_lora"] == 2             # CPU라 GPU 메모리는 없다
    assert "최대 GPU 메모리" in p.stdout
