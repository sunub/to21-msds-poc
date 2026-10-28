"""성적표 여러 개를 한 표로 합친다 (역할 F, 10/27 보고 자료용)

사용법 (라벨=성적표 폴더, 순서대로 열이 된다)
  python scripts/compare_scores.py --title 개발용10건 \
      기준선=runs/20261027_score_기준선_개발 \
      GPT실버=runs/20261027_score_GPT실버_개발 \
      Claude실버=runs/20261027_score_Claude실버_개발 \
      --ref GPT실버 Claude실버

결과: runs/<날짜>_compare_<제목>/compare.md, compare.csv
--ref로 고른 결과는 '(참고)'로 표시한다. 개발용 골드는 실버에서 출발해 실버 점수가 높게 나온다.
"""
import argparse
import sys
from pathlib import Path

from _common import today
from msds.common import paths
from msds.evaluate.compare import compare, load_result, write_compare

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", help="라벨=성적표폴더")
    ap.add_argument("--title", required=True)
    ap.add_argument("--ref", nargs="*", default=[], help="참고값으로 표시할 라벨 (보통 실버)")
    a = ap.parse_args()
    results = []
    for spec in a.runs:
        if "=" not in spec:
            sys.exit(f"'{spec}': 라벨=폴더 형식으로 적으세요. 예: 기준선=runs/20261027_score_기준선_개발")
        label, folder = spec.split("=", 1)
        results.append((label, load_result(Path(folder))))
    unknown = set(a.ref) - {lb for lb, _ in results}
    if unknown:
        sys.exit(f"--ref에 없는 라벨: {sorted(unknown)}")
    docsets = {lb: sorted(r["docs"]) for lb, r in results}
    if len({tuple(v) for v in docsets.values()}) > 1:
        print("주의: 결과마다 채점한 문서가 다릅니다. 표의 '문서 수' 줄을 확인하세요.")
        for lb, v in docsets.items():
            print(f"  {lb}: {', '.join(v)}")
    out = write_compare(compare(results), paths.run_dir(f"{today()}_compare_{a.title}"), a.title, a.ref)
    print(out)
