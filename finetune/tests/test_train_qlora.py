"""QLoRA 학습 스크립트 시험 (CPU, 작은 가짜 모델). GPU·인터넷 없이 돈다. transformers·peft·torch가 없으면 건너뛴다.

    python -m pytest finetune/tests -q

- 정답 토큰에만 손실이 걸리고, 프롬프트는 추론 때(add_generation_prompt=True) 글과 같다.
- 밀집 모델(Qwen3)과 MoE 모델(Qwen3-MoE)에서 LoRA가 주의 투영에 붙고 몇 단계 학습해 LoRA 가중치를 저장한다.
"""
import json
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


@pytest.mark.parametrize("kind", ["dense", "moe"])
def test_CPU에서_몇_단계_학습하고_LoRA를_저장한다(tiny, tmp_path, kind):
    data = tmp_path / "data"
    data.mkdir()
    rows = _examples(6)
    (data / "train.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows[:4]), encoding="utf-8")
    (data / "val.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows[4:]), encoding="utf-8")
    (data / "data_info.yaml").write_text("examples: 6\n", encoding="utf-8")
    cmd = [sys.executable, str(HERE.parent / "train_qlora.py"), "--config", str(HERE.parent / "configs" / "qlora.yaml"),
           "--data", str(data), "--no-4bit", "--max-steps", "2",
           "--set", f"base_model={tiny[kind]}", f"output_dir={tmp_path / 'out'}", "run_name=t", "train.bf16=false",
           "train.grad_accum=1", "train.eval_steps=1", "max_seq_len=512", "attn_implementation=eager"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-3000:]
    run = tmp_path / "out" / "t"
    adapter = json.loads((run / "adapter" / "adapter_config.json").read_text(encoding="utf-8"))
    assert set(adapter["target_modules"]) == {"q_proj", "k_proj", "v_proj", "o_proj"}
    import yaml
    info = yaml.safe_load((run / "train_info.yaml").read_text(encoding="utf-8"))
    assert info["steps"] == 2 and info["eval_loss_before"] is not None and info["eval_loss_after"] is not None
    assert info["train_examples"]["how"] == {"template": 4} and info["data_info"] == {"examples": 6}
    if kind == "dense":                                                    # 합치기도 한 번 확인한다
        merged = tmp_path / "merged"
        p = subprocess.run([sys.executable, str(HERE.parent / "merge_adapter.py"), "--adapter", str(run / "adapter"),
                            "--out", str(merged)], capture_output=True, text=True, timeout=600)
        assert p.returncode == 0, p.stderr[-3000:]
        from transformers import AutoModelForCausalLM, AutoTokenizer
        m = AutoModelForCausalLM.from_pretrained(merged)
        assert not any("lora" in n for n, _ in m.named_parameters()) and AutoTokenizer.from_pretrained(merged).eos_token == "<|im_end|>"
