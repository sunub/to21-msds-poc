"""성적표 (역할 F, D-13)

사용법
  # 개발용 10건 (골드 기준)
  python scripts/score.py --pred runs/20261026_baseline_qwen38/outputs --title 기준선_개발 --purpose 개발
  python scripts/score.py --pred data/silver/gpt --title GPT실버_개발 --purpose 개발
  # 평가용 10건 (25번은 골드가 없어 '정답 없음'으로 빠진다. 여기에 --gold-example25를 붙이지 않는다)
  python scripts/score.py --pred runs/.../outputs --title 기준선_평가 --purpose 평가
  # 25번 (TO21 정답 예제 기준, 평가 평균과 따로 적는다. 기술명세 2.12)
  python scripts/score.py --pred runs/.../outputs --title 기준선_25 --docs T21-025 --gold-example25
  # 특정 문서만
  python scripts/score.py --pred data/silver/claude --title 시험 --docs T21-S016 T21-M013

정답은 data/gold/<문서>.json (25번은 --gold-example25를 붙이면 to21/의 TO21 정답 예제).
결과: runs/<날짜>_score_<제목>/ (report.md, items.csv, docs.csv, details.csv, result.json)
세 결과를 한 표로 합치려면 scripts/compare_scores.py
"""
import argparse
import json
import sys
from pathlib import Path

from _common import today
from msds.common import manifest, paths
from msds.evaluate.score import score_set, write_report

EVAL_EXCLUDED = {"T21-025"}   # 평가 평균에 넣지 않는 문서 (ADR-0005)


def eval_gaps(keep: set[str], no_pred: list[str], no_gold: list[str]) -> list[str]:
    """평가 평균에 들어가야 하는데 결과나 정답이 없는 문서. 있으면 평균의 문서 수가 달라져 채점하지 않는다."""
    return sorted((set(no_pred) | set(no_gold)) & (keep - EVAL_EXCLUDED))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True, help="결과 JSON 폴더 (T21-*.json)")
    ap.add_argument("--title", required=True)
    ap.add_argument("--purpose", choices=manifest.PURPOSES, help="manifest의 purpose로 문서를 고른다")
    ap.add_argument("--docs", nargs="+", help="문서 번호를 직접 고른다")
    ap.add_argument("--gold-example25", action="store_true", help="T21-025를 TO21 정답 예제로 채점")
    a = ap.parse_args()
    if a.purpose == "평가" and a.gold_example25:
        ap.error("--purpose 평가에는 --gold-example25를 붙이지 않습니다. 25번은 --docs T21-025로 따로 채점합니다 (ADR-0005)")

    keep = None
    if a.purpose:
        if not paths.MANIFEST.exists():
            sys.exit(f"{paths.MANIFEST}가 없어 --purpose로 문서를 고를 수 없습니다. "
                     f"manifest가 있는 브랜치에서 실행하거나 --docs로 문서 번호를 직접 적으세요.")
        keep = {r["doc_id"] for r in manifest.select(a.purpose)}
        if not keep:
            sys.exit(f"manifest에서 purpose='{a.purpose}'인 문서가 0건입니다. "
                     f"data/manifest.csv의 purpose 값이 {manifest.PURPOSES} 중 하나인지 확인하세요.")
    if a.docs:
        keep = set(a.docs) if keep is None else keep & set(a.docs)

    pairs, no_gold, no_pred = [], [], []
    found = set()
    for p in sorted(Path(a.pred).glob("T21-*.json")):
        if p.name.endswith((".review.json", ".unreviewed.json")):
            continue
        doc_id = p.stem
        if keep is not None and doc_id not in keep:
            continue
        found.add(doc_id)
        gold_p = paths.to21_file("example25") if (doc_id == "T21-025" and a.gold_example25) else paths.gold_path(doc_id)
        if not gold_p.exists():
            no_gold.append(doc_id)
            continue
        pairs.append((doc_id, json.loads(gold_p.read_text(encoding="utf-8")),
                      json.loads(p.read_text(encoding="utf-8"))))
    if keep is not None:
        no_pred = sorted(keep - found)
    if a.purpose == "평가":
        gaps = eval_gaps(keep, no_pred, no_gold)
        if gaps:
            sys.exit(f"평가 문서 {len(gaps)}건의 결과나 정답이 없어 채점하지 않습니다: {', '.join(gaps)}")

    for d in no_gold:
        print(f"[정답 없음] {d}")
    for d in no_pred:
        print(f"[결과 없음] {d} — {a.pred}에 {d}.json이 없습니다")
    if not pairs:
        sys.exit("채점할 문서가 없습니다.")

    result = score_set(pairs)
    out = write_report(result, paths.run_dir(f"{today()}_score_{a.title}"), a.title)
    print(f"{len(pairs)}건 채점: 가중 종합 {result['weighted']:.1f}점, "
          f"필수 {result['must_passed_count']}/{result['must_total']} 통과 → {'합격' if result['passed'] else '불합격'}")
    if no_gold or no_pred:
        print(f"주의: 정답 없음 {len(no_gold)}건, 결과 없음 {len(no_pred)}건은 빠졌습니다. 보고할 때 몇 건 기준인지 밝힌다.")
    print(out)
