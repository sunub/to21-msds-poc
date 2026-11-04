"""LoRA를 원본 모델에 합친 체크포인트를 만든다 (11/03 F). vLLM에 LoRA를 따로 붙이기 어렵거나, RNGD용으로 다시 빌드할 때 쓴다.

    python finetune/merge_adapter.py --adapter finetune/out/<run_name>/adapter --out finetune/out/<run_name>/merged

- 원본은 adapter_config.json의 base_model_name_or_path(학습 때 쓴 bf16 체크포인트)를 bf16으로 올린다. --base로 바꿀 수 있다.
- 35B급 모델은 bf16으로 약 70GB다. 기본은 CPU 메모리로 합친다(--device cuda면 GPU). 디스크도 그만큼 필요하다.
- 합친 체크포인트는 bf16이다. vLLM에서 FP8로 쓰려면 `vllm serve <merged> --quantization fp8`처럼 실행할 때 양자화한다.
- RNGD(furiosa-llm)에 올리려면 이 체크포인트로 퓨리오사 형식 빌드가 따로 필요하다(지원·소요 시간 확인 필요).
"""
import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--base", help="원본 모델(기본: adapter_config.json의 base_model_name_or_path)")
    ap.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    ap.add_argument("--trust-remote-code", action="store_true")
    a = ap.parse_args()

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    adapter = Path(a.adapter)
    base = a.base or json.loads((adapter / "adapter_config.json").read_text(encoding="utf-8"))["base_model_name_or_path"]
    kw = {"dtype": torch.bfloat16, "device_map": {"": a.device}, "trust_remote_code": a.trust_remote_code}
    try:
        model = AutoModelForCausalLM.from_pretrained(base, **kw)
    except ValueError:                                   # 멀티모달 체크포인트
        from transformers import AutoModelForImageTextToText
        model = AutoModelForImageTextToText.from_pretrained(base, **kw)
    merged = PeftModel.from_pretrained(model, adapter).merge_and_unload()
    out = Path(a.out)
    merged.save_pretrained(out, safe_serialization=True, max_shard_size="5GB")
    AutoTokenizer.from_pretrained(adapter).save_pretrained(out)
    try:                                                 # 멀티모달 모델은 이미지 처리 설정도 옮긴다
        from transformers import AutoProcessor
        AutoProcessor.from_pretrained(base, trust_remote_code=a.trust_remote_code).save_pretrained(out)
    except Exception:  # 글 전용 모델은 프로세서가 없다
        pass
    print(f"합친 체크포인트: {out} (원본 {base})")


if __name__ == "__main__":
    main()
