"""학습한 LoRA를 vLLM이 찾는 층 이름으로 바꾼 사본을 만든다 (11/04 F).

    python finetune/adapter_for_vllm.py <adapter 폴더> --base <vLLM에 띄울 원본 모델>
    → 바꿀 것이 있으면 <adapter 폴더>_vllm/ 을 만들고, 마지막 줄에 vLLM에 줄 폴더를 찍는다.

왜 필요한가
- 학습은 이미지까지 받는 체크포인트(Qwen3.5·3.6·3.8 계열, …ForConditionalGeneration)도 글 전용 클래스(…ForCausalLM)로
  올린다. 그래서 LoRA 층 이름이 `model.layers.N...`이다.
- vLLM은 같은 체크포인트를 이미지까지 받는 구조로 띄우고, LoRA 이름을 HF 이름(`model.language_model.layers.N...`)으로 찾는다.
- 이름이 다르면 vLLM은 오류 없이 "LoRA를 불러왔다"고 하지만 어느 층에도 붙지 않는다.
  11/04 122B에서 학습 전후 출력과 확률이 소수점까지 같았고, 이름을 바꾸니 달라졌다.
원본 모델의 config.json에 vision_config가 있거나 구조 이름이 ForConditionalGeneration이면 바꾼다. 글 전용 모델(Qwen3-30B-A3B 등)은 그대로 둔다.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

OLD, NEW = "base_model.model.model.layers.", "base_model.model.model.language_model.layers."


def base_config(base: str) -> dict:
    """원본 모델의 config.json. 로컬 폴더면 그 안의 것, 아니면 HF 허브(캐시)에서 받는다."""
    p = Path(base)
    if p.is_dir():
        return json.loads((p / "config.json").read_text(encoding="utf-8"))
    from huggingface_hub import hf_hub_download
    return json.loads(Path(hf_hub_download(base, "config.json")).read_text(encoding="utf-8"))


def is_multimodal(cfg: dict) -> bool:
    return "vision_config" in cfg or any(a.endswith("ForConditionalGeneration") for a in cfg.get("architectures") or [])


def convert(adapter: Path, cfg: dict, out: Path | None = None) -> tuple[Path, int]:
    """(vLLM에 줄 폴더, 바꾼 이름 수). 바꿀 것이 없으면 원래 폴더와 0."""
    from safetensors.torch import load_file, save_file
    adapter = Path(adapter)
    sd = load_file(str(adapter / "adapter_model.safetensors"))
    if not is_multimodal(cfg) or not any(k.startswith(OLD) for k in sd):
        return adapter, 0
    out = Path(out) if out else adapter.with_name(adapter.name + "_vllm")
    shutil.copytree(adapter, out, dirs_exist_ok=True)
    new = {(NEW + k[len(OLD):]) if k.startswith(OLD) else k: v for k, v in sd.items()}
    if len(new) != len(sd):
        raise SystemExit("이름을 바꾸다 겹치는 항목이 생겼습니다")
    save_file(new, str(out / "adapter_model.safetensors"), metadata={"format": "pt"})
    return out, sum(k.startswith(OLD) for k in sd)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("adapter", type=Path)
    ap.add_argument("--base", help="vLLM에 띄울 원본 모델(기본: adapter_config.json의 base_model_name_or_path)")
    ap.add_argument("--out", type=Path, help="사본 폴더(기본: <adapter>_vllm)")
    a = ap.parse_args()
    base = a.base or json.loads((a.adapter / "adapter_config.json").read_text(encoding="utf-8"))["base_model_name_or_path"]
    out, n = convert(a.adapter, base_config(base), a.out)
    print(f"LoRA 이름 {n}개를 vLLM 이름으로 바꿨습니다" if n else "바꿀 이름이 없습니다(글 전용 모델이거나 이미 바뀜)")
    print(out)


if __name__ == "__main__":
    main()
