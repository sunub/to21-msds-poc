"""입력 비교 실험 채점: '이미지만'(A)과 '이미지+글자'(B) 결과를 같은 정답으로 채점해 칸별로 비교한다.

계획: docs/superpowers/plans/2026-10-28-input-mode-ab.md

사용법
  python scripts/compare_input_modes.py --a runs/<날짜>_inputab_qwen38_img/outputs --b runs/<날짜>_inputab_qwen38_imgtxt/outputs

정답은 data/gold/<문서>.json. 정답이 없거나 한쪽 결과가 없는 문서는 건너뛴다.
결과: runs/<날짜>_inputab_report/report.md, cells.json
- 항목 표: TO21 채점기 항목마다 A·B 점수. 구분은 주(글자를 정확히 읽어야 하는 칸) / 대조군(글자가 돕지 않는 칸) / 기타
- 칸 표: 채점기의 필수 항목 상세(누락·오추출·불일치)를 칸마다 묶어 A만 틀림 / B만 틀림 / 둘 다 틀림으로 나눈다
평균 차이보다 칸 표를 먼저 본다. 문서가 두세 건이라 평균 차이는 우연일 수 있다.
"""
import argparse
import json
from pathlib import Path

from _common import today
from msds.checks.validator import load_to21_module
from msds.common import paths

MAIN = {"관리정보(제출번호·작성일·개정일·개정횟수)", "제품명·회사명·긴급연락처", "구성성분(CAS 기준 매칭)",
        "구성성분 필드(성분명·KE)", "함유량(부등호·값·단위 6요소)", "8항 노출기준(성분·출처·종류·값)",
        "9항 필수 물성(특성·값)", "11항 급성독성(경구·경피·흡입)", "14항 운송(UN번호·등급·용기등급)",
        "H 코드", "P 코드"}
CONTROL = {"그림문자", "신호어"}


def group_of(item: str) -> str:
    return "주" if item in MAIN else "대조군" if item in CONTROL else "기타"


def score_doc(scorer, gold: dict, pred: dict) -> tuple[list, list]:
    """TO21 채점기 한 번: (항목 점수 행, 필수 항목 상세 [(항목, 종류, 내용)])."""
    rows = scorer.score(gold, pred)
    return rows, list(scorer.score.details)


def cell_key(item: str, kind: str, text) -> tuple:
    """불일치는 정답 쪽만 키로 쓴다. 두 조건이 같은 칸을 다르게 틀려도 한 칸으로 센다."""
    text = str(text)
    if kind == "불일치":
        text = text.split(" / 추출=")[0]
    return (item, kind, text)


def compare_cells(details_a: list, details_b: list) -> dict[str, list]:
    a = {cell_key(*d) for d in details_a}
    b = {cell_key(*d) for d in details_b}
    return {"A만 틀림": sorted(a - b), "B만 틀림": sorted(b - a), "둘 다 틀림": sorted(a & b)}


def report(results: dict) -> str:
    out = ["# 입력 비교 실험 결과", "", "A = 이미지만, B = 이미지+글자", ""]
    for doc_id, r in results.items():
        out += [f"## {doc_id}", "", "| 구분 | 항목 | 지표 | A | B | 목표 |", "|---|---|---|---|---|---|"]
        b_rows = {row[1]: row for row in r["b_rows"]}
        for lv, name, metric, va, _, target in sorted(r["a_rows"], key=lambda x: ("주대조군기타".index(group_of(x[1])[0]), x[1])):
            out.append(f"| {group_of(name)} | {name} | {metric} | {va:.3f} | {b_rows[name][3]:.3f} | {target} |")
        out.append("")
        for side, cells in r["cells"].items():
            out += [f"### {side} ({len(cells)}칸)", ""]
            out += [f"- [{group_of(item)}] {item} · {kind} · {text}" for item, kind, text in cells] or ["- 없음"]
            out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True, help="이미지만 결과 폴더 (outputs)")
    ap.add_argument("--b", required=True, help="이미지+글자 결과 폴더 (outputs)")
    a = ap.parse_args()
    scorer = load_to21_module("scorer")
    results = {}
    for pa in sorted(Path(a.a).glob("T21-*.json")):
        doc_id, pb, gold_p = pa.stem, Path(a.b) / pa.name, paths.gold_path(pa.stem)
        if not (pb.exists() and gold_p.exists()):
            print(f"[건너뜀] {doc_id}: {'정답' if pb.exists() else 'B 결과'} 없음")
            continue
        gold = json.loads(gold_p.read_text(encoding="utf-8"))
        a_rows, det_a = score_doc(scorer, gold, json.loads(pa.read_text(encoding="utf-8")))
        b_rows, det_b = score_doc(scorer, gold, json.loads(pb.read_text(encoding="utf-8")))
        results[doc_id] = {"a_rows": a_rows, "b_rows": b_rows, "cells": compare_cells(det_a, det_b)}
    if not results:
        raise SystemExit("채점할 문서가 없습니다")
    out_dir = paths.run_dir(f"{today()}_inputab_report")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text(report(results), encoding="utf-8")
    (out_dir / "cells.json").write_text(json.dumps({k: v["cells"] for k, v in results.items()}, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    print(out_dir / "report.md")
