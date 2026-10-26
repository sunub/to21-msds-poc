"""묶음별 프롬프트를 TO21 명세서에서 다시 만든다. 결과: src/msds/extract/prompts/b1.md ~ b5.md

사용법: python scripts/build_prompts.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from msds.extract.prompt_builder import build_all, PROMPT_VERSION  # noqa: E402

if __name__ == "__main__":
    for p in build_all():
        print(f"[{PROMPT_VERSION}] {p}")
