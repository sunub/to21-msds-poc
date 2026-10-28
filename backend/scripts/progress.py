"""골드 검수 진도 (역할 F)

사용법 (git pull로 검수표를 받은 뒤)
  python scripts/progress.py                    # 개발용 10건
  python scripts/progress.py --purpose 평가     # 2주차 평가용
  python scripts/progress.py --md progress.md   # 디스코드에 붙일 표를 파일로도 저장

보는 것: 문서마다 우선순위별 검수 진도(끝난 줄/전체 줄), 누락 추가 줄 수, 1순위 교차 확인,
검수 시간(문서 정보 시트의 시작·끝), 골드 생성 여부와 미검수 칸 수. 검수표는 읽기만 한다.
"""
import argparse
import sys
from pathlib import Path

from _common import ROOT  # noqa: F401  (src 경로 등록)
from msds.common import manifest, paths
from msds.evaluate.progress import collect, to_markdown

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--purpose", choices=manifest.PURPOSES, default="개발")
    ap.add_argument("--md", help="표를 markdown 파일로도 저장")
    a = ap.parse_args()
    if not paths.MANIFEST.exists():
        print(f"주의: {paths.MANIFEST}가 없습니다. 검수표 폴더({paths.REVIEW})에 있는 문서만 보여 줍니다.")
    elif not any(r.get("purpose") == a.purpose for r in manifest.load()):
        sys.exit(f"manifest에서 purpose='{a.purpose}'인 문서가 0건입니다. "
                 f"data/manifest.csv의 purpose 값이 {manifest.PURPOSES} 중 하나인지 확인하세요.")
    text = to_markdown(collect(a.purpose))
    print(text)
    if a.md:
        Path(a.md).write_text(text, encoding="utf-8")
        print(f"저장: {a.md}")
