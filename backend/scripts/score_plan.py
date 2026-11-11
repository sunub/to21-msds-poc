"""기획서 기준 성적표 (TO21_MSDS_PoC_기획서 v1.0). 정의는 msds/evaluate/plan_score.py.

주 지표는 기획서 범위 안 칸 정확도와 사람이 고쳐야 할 칸 수다. TO21 채점기 점수는 참고(구 기준)로만 붙인다.
- 평균은 국문 문서로만 낸다 (기획서 표 1-3: 영문 양식 대응은 범위 밖). 영문 문서는 따로 보인다.
- T21-025는 평가 평균에 넣지 않는다 (D-3).
- 정확도 = 맞은 칸 / 골드에 값이 있는 칸. 합계는 칸을 모두 더해 낸다(사람이 확인할 칸 기준). 문서 평균도 함께 적는다.

사용법 (backend/에서)
  python scripts/score_plan.py --pred ../runs/<실행>/outputs --title s10_r1
  python scripts/score_plan.py --pred ../runs/<실행_r1>/outputs --repeat ../runs/<실행_r2>/outputs --title s10
  python scripts/score_plan.py --purpose 평가 --pred ../runs/<평가 실행>/outputs --title 평가

결과: runs/<날짜>_plan_<제목>/report.md, docs.csv, sections.csv, fields.csv, cells.csv(맞지 않은 칸), result.json
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from _common import today
from msds.common import manifest, paths
from msds.common.align import generic
from msds.evaluate import plan_score as ps
from msds.evaluate.score import score_pair

EXCLUDED = {"T21-025": "평가 평균에서 뺀다 (D-3)"}


def _read(p: Path) -> dict | None:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _pct(x: float | None) -> str:
    return "-" if x is None else f"{x * 100:.1f}%"


def _csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def _unreviewed(doc_id: str) -> set[str]:
    p = paths.gold_unreviewed_path(doc_id)
    return set(json.loads(p.read_text(encoding="utf-8"))) if p.exists() else set()


def score_docs(doc_rows: list[dict], pred_dir: Path, repeat_dir: Path | None) -> tuple[list[dict], list[dict]]:
    """문서별 결과와 모든 칸 결과. 정답이나 결과가 없는 문서는 건너뛴다."""
    docs, all_cells = [], []
    for r in doc_rows:
        d = r["doc_id"]
        gold, pred = _read(paths.GOLD / f"{d}.json"), _read(pred_dir / f"{d}.json")
        if gold is None or pred is None:
            continue
        res = ps.compare_doc(gold, pred, _unreviewed(d))
        cells = [{**c, "doc_id": d} for c in res["cells"]]
        all_cells += cells
        inside = [c for c in cells if c["scope"] == "범위"]
        t = ps.tally(inside)
        e = ps.tally([c for c in inside if c["engine"]])
        rev = ps.tally([c for c in cells if c["scope"] == "16항 참고"])
        row = {"doc_id": d, "language": r.get("language") or "", "purpose": r.get("purpose") or "",
               "accuracy": t["accuracy"], "gold_n": t["gold_n"], "correct": t["correct"], "wrong": t["wrong"],
               "missing": t["missing"], "extra": t["extra"], "to_fix": t["to_fix"], "unreviewed": t["unreviewed"],
               "engine_accuracy": e["accuracy"], "engine_gold_n": e["gold_n"], "engine_to_fix": e["to_fix"],
               "rev16_correct": rev["correct"], "rev16_gold_n": rev["gold_n"],
               "out_of_scope_cells": sum(1 for c in cells if c["scope"] == "범위 밖"),
               "msds_gold": res["msds_count"][0], "msds_pred": res["msds_count"][1],
               "to21_ref": round(score_pair(gold, pred)["weighted"], 1)}
        if repeat_dir is not None:
            other = _read(repeat_dir / f"{d}.json")
            agree = ps.cell_agreement(pred, other) if other else {"rate": None, "same": 0, "total": 0}
            row.update(repeat_rate=agree["rate"], repeat_same=agree["same"], repeat_total=agree["total"])
        docs.append(row)
    return docs, all_cells


def _sum(rows: list[dict], key_n: str, key_ok: str) -> float | None:
    n = sum(r[key_n] for r in rows)
    return sum(r[key_ok] for r in rows) / n if n else None


def _mean(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def group(cells: list[dict], keyfn) -> list[dict]:
    acc: dict = defaultdict(list)
    for c in cells:
        acc[keyfn(c)].append(c)
    out = []
    for k, lst in acc.items():
        t = ps.tally(lst)
        out.append({"key": k, **{x: t[x] for x in ("accuracy", "gold_n", "correct", "wrong", "missing", "extra",
                                                    "to_fix")}})
    return out


def write_report(out_dir: Path, title: str, pred: Path, repeat: Path | None, docs: list[dict],
                 cells: list[dict], skipped: list[str]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ko = [d for d in docs if d["language"] == "ko"]
    other = [d for d in docs if d["language"] != "ko"]
    ko_ids = {d["doc_id"] for d in ko}
    inside = [c for c in cells if c["doc_id"] in ko_ids and c["scope"] == "범위"]
    sections = sorted(group(inside, lambda c: c["section"]), key=lambda g: g["key"])
    fields = sorted(group(inside, lambda c: generic(c["path"])), key=lambda g: -g["to_fix"])
    summary = {
        "docs": len(ko), "accuracy": _sum(ko, "gold_n", "correct"), "accuracy_doc_mean": _mean([d["accuracy"] for d in ko]),
        "gold_n": sum(d["gold_n"] for d in ko), "to_fix": sum(d["to_fix"] for d in ko),
        "wrong": sum(d["wrong"] for d in ko), "missing": sum(d["missing"] for d in ko), "extra": sum(d["extra"] for d in ko),
        "engine_accuracy": _sum(ko, "engine_gold_n", "engine_correct") if ko and "engine_correct" in ko[0] else None,
        "rev16": _sum(ko, "rev16_gold_n", "rev16_correct"),
        "to21_ref_mean": _mean([d["to21_ref"] for d in ko]),
        "repeat": _sum(ko, "repeat_total", "repeat_same") if repeat else None,
    }
    # 엔진 칸 정확도는 칸을 더해 다시 낸다
    eng = ps.tally([c for c in inside if c["engine"]])
    summary["engine_accuracy"], summary["engine_to_fix"] = eng["accuracy"], eng["to_fix"]

    _csv(out_dir / "docs.csv", docs)
    _csv(out_dir / "sections.csv", sections)
    _csv(out_dir / "fields.csv", fields)
    _csv(out_dir / "cells.csv", [{k: (json.dumps(v, ensure_ascii=False) if k in ("gold", "pred") else v)
                                  for k, v in c.items()} for c in cells if c["result"] != "맞음"])
    (out_dir / "result.json").write_text(json.dumps(
        {"title": title, "pred": str(pred), "repeat": str(repeat) if repeat else None, "summary": summary,
         "docs": docs, "sections": sections, "skipped": skipped}, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")

    L = [f"# 기획서 기준 성적표: {title}", "",
         "기준: TO21_MSDS_PoC_기획서 v1.0. 범위는 1·2·3·8·9·11·12·14·15항과 1항 관리정보(D-1), "
         "칸은 검수자가 골드를 확정한 단위(기술명세 2.7). 골드와 같은지만 본다.", "",
         f"- 결과: {pred}" + (f"\n- 다시 돌린 결과: {repeat}" if repeat else ""),
         f"- 국문 문서 {len(ko)}건: {', '.join(d['doc_id'] for d in ko)}"]
    if skipped:
        L.append(f"- 뺀 문서: {', '.join(skipped)}")
    L += ["", "## 요약", "",
          f"- **범위 안 칸 정확도 {_pct(summary['accuracy'])}** ({summary['gold_n'] - summary['wrong'] - summary['missing']}"
          f"/{summary['gold_n']}칸, 문서 평균 {_pct(summary['accuracy_doc_mean'])})",
          f"- **사람이 고쳐야 할 칸 {summary['to_fix']}칸** (틀림 {summary['wrong']}, 빠뜨림 {summary['missing']}, "
          f"지어냄 {summary['extra']}), 문서당 {summary['to_fix'] / len(ko):.0f}칸" if ko else "- 문서 없음",
          f"- **엔진 입력 칸 정확도 {_pct(summary['engine_accuracy'])}** (2단계가 읽는 칸, 고칠 칸 {summary['engine_to_fix']})"]
    if repeat:
        L.append(f"- **재현성(칸 일치) {_pct(summary['repeat'])}** (같은 설정으로 다시 돌린 결과와 범위 안 칸 비교)")
    L += [f"- 16항 개정 정보(범위 밖, 참고): {_pct(summary['rev16'])}",
          f"- TO21 채점기(참고, 구 기준): 문서 평균 {summary['to21_ref_mean']:.1f}점" if summary["to21_ref_mean"] is not None else "",
          "", "## 문서별", "",
          "| 문서 | 칸 정확도 | 골드 칸 | 틀림 | 빠뜨림 | 지어냄 | 고칠 칸 | 엔진 칸 정확도 | 16항 참고 | 재현성 | TO21 참고 |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for d in sorted(docs, key=lambda x: (x["language"] != "ko", x["accuracy"] or 0)):
        mark = "" if d["language"] == "ko" else f" ({d['language']}, 평균 제외)"
        L.append(f"| {d['doc_id']}{mark} | {_pct(d['accuracy'])} | {d['gold_n']} | {d['wrong']} | {d['missing']} | "
                 f"{d['extra']} | {d['to_fix']} | {_pct(d['engine_accuracy'])} | {d['rev16_correct']}/{d['rev16_gold_n']} | "
                 f"{_pct(d.get('repeat_rate'))} | {d['to21_ref']} |")
    L += ["", "## 항별 (국문 문서, 범위 안)", "", "| 항 | 칸 정확도 | 골드 칸 | 틀림 | 빠뜨림 | 지어냄 | 고칠 칸 |",
          "|---|---|---|---|---|---|---|"]
    for s in sections:
        L.append(f"| {s['key']}항 | {_pct(s['accuracy'])} | {s['gold_n']} | {s['wrong']} | {s['missing']} | "
                 f"{s['extra']} | {s['to_fix']} |")
    L += ["", "## 고칠 칸이 많은 칸 묶음 (상위 20)", "", "| 칸 | 칸 정확도 | 골드 칸 | 틀림 | 빠뜨림 | 지어냄 |",
          "|---|---|---|---|---|---|"]
    for f in fields[:20]:
        L.append(f"| `{f['key']}` | {_pct(f['accuracy'])} | {f['gold_n']} | {f['wrong']} | {f['missing']} | {f['extra']} |")
    L += ["", "## 읽는 법", "",
          "- 목록 항목은 키(성분 CAS, 규제의 성분·법령·항목 등)로 짝짓는다. 키 칸이 틀리면 그 행의 칸은 빠뜨림과 지어냄으로 함께 잡힌다",
          "- 지어냄은 골드에 값이 없는데 결과에 값이 있는 칸이다. 정확도에는 들어가지 않고 고칠 칸에 들어간다",
          "- 미검수 칸은 정확도에 넣지 않는다 (기획서 7.1). 문서별 표의 unreviewed는 docs.csv에 있다",
          "- 틀린 칸 목록: cells.csv (골드 값과 결과 값)"]
    out = out_dir / "report.md"
    out.write_text("\n".join(x for x in L if x is not None) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pred", type=Path, required=True, help="결과 폴더 (runs/.../outputs)")
    ap.add_argument("--repeat", type=Path, help="같은 설정으로 다시 돌린 결과 폴더 (재현성)")
    ap.add_argument("--purpose", default="개발", help="개발 / 평가 (manifest의 purpose)")
    ap.add_argument("--docs", nargs="*", help="특정 문서만")
    ap.add_argument("--title", default=None)
    a = ap.parse_args()
    rows = manifest.select(purpose=None if a.docs else a.purpose, doc_ids=a.docs)
    skipped = [f"{r['doc_id']}({EXCLUDED[r['doc_id']]})" for r in rows if r["doc_id"] in EXCLUDED]
    rows = [r for r in rows if r["doc_id"] not in EXCLUDED]
    docs, cells = score_docs(rows, a.pred, a.repeat)
    if not docs:
        raise SystemExit(f"채점할 문서가 없습니다: {a.pred}와 data/gold를 확인하세요")
    title = a.title or a.purpose
    out = write_report(paths.RUNS / f"{today()}_plan_{title}", title, a.pred, a.repeat, docs, cells, skipped)
    print(out.read_text(encoding="utf-8"))
