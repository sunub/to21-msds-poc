"""성적표 (역할 F, D-13)

사용법
  python scripts/score.py --pred runs/20261026_baseline_qwen38/outputs --title 기준선
  python scripts/score.py --pred data/silver/gpt --title "GPT 실버(참고)"
  python scripts/score.py --pred runs/.../outputs --gold-example25    # 25번은 TO21 정답 예제로 채점

정답은 data/gold/<문서>.json (25번은 to21/v0.5의 정답 예제). 결과: runs/<날짜>_score_<제목>/
"""
import argparse
import json
from pathlib import Path

from _common import today
from msds.common import paths
from msds.evaluate.score import score_set, write_report

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True, help="결과 JSON 폴더")
    ap.add_argument("--title", required=True)
    ap.add_argument("--gold-example25", action="store_true", help="T21-025를 TO21 정답 예제로 채점")
    a = ap.parse_args()
    pairs = []
    for p in sorted(Path(a.pred).glob("T21-*.json")):
        if p.name.endswith(".review.json"):
            continue
        doc_id = p.stem
        if doc_id == "T21-025" and a.gold_example25:
            gold_p = paths.to21_file("example25")
        else:
            gold_p = paths.gold_path(doc_id)
        if not gold_p.exists():
            print(f"[정답 없음] {doc_id}")
            continue
        pairs.append((doc_id, json.loads(gold_p.read_text(encoding="utf-8")), json.loads(p.read_text(encoding="utf-8"))))
    result = score_set(pairs)
    out = write_report(result, paths.run_dir(f"{today()}_score_{a.title}"), a.title)
    print(out)
