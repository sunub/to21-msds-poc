"""골드(또는 TO21 정답 예제)에 입력 로더·판별기를 돌려 판별 결과와 비어 있는 칸을 출력한다.

사용 (저장소 최상위에서):
    python backend/scripts/d_check.py                      # data/gold/T21-*.json
    python backend/scripts/d_check.py to21/v0.5/TO21_MSDS_추출예제_25_황산_v0.5.json

미검수 칸 목록의 위치와 형식은 아직 정해지지 않아서(docs/adr/0001), 아래 "비어 있음"에는
미검수 칸이 섞여 있을 수 있어 참고용이다. 별도 미검수 목록인 *.unreviewed.json 은 제외한다.
"""

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from msds.compliance.classifier import product_type  # noqa: E402
from msds.compliance.loader import load_inputs  # noqa: E402


def main(patterns: list[str]) -> int:
    files = sorted(
        f for p in patterns for f in glob.glob(p) if not f.endswith(".unreviewed.json")
    )
    if not files:
        print("읽을 파일이 없습니다:", patterns)
        return 1
    print("미검수 구분 없음 (참고용)")
    for f in files:
        doc = json.loads(Path(f).read_text(encoding="utf-8"))
        for i in range(len(doc.get("msds") or [])):
            x = load_inputs(doc, i)
            print(f, i, product_type(x), "비어 있음:", x["missing"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or [str(ROOT / "data" / "gold" / "T21-*.json")]))
