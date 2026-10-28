"""성적표 여러 개를 한 표로 합친다 (역할 F, 보고 자료용).

scripts/score.py가 만든 runs/<날짜>_score_<제목>/result.json을 결과마다 하나씩 받아
'항목 × 결과' 표를 만든다. 예: 기준선 / GPT 실버 / Claude 실버를 나란히.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path


def load_result(run_dir: Path) -> dict:
    p = Path(run_dir) / "result.json"
    if not p.exists():
        raise FileNotFoundError(f"{p}가 없습니다. scripts/score.py로 먼저 채점하세요.")
    return json.loads(p.read_text(encoding="utf-8"))


def compare(results: list[tuple[str, dict]]) -> dict:
    """results = [(라벨, result.json 내용)] → {'labels', 'rows', 'summary'}"""
    if not results:
        raise ValueError("합칠 성적표가 없습니다.")
    labels = [lb for lb, _ in results]
    order: list[str] = []
    meta: dict[str, dict] = {}
    for _, r in results:
        for i in r["items"]:
            if i["name"] not in meta:
                order.append(i["name"])
                meta[i["name"]] = {"level": i["level"], "target": i["target"]}
    rows = []
    for name in order:
        row = {"level": meta[name]["level"], "name": name, "target": meta[name]["target"], "cells": {}}
        for lb, r in results:
            hit = next((i for i in r["items"] if i["name"] == name), None)
            row["cells"][lb] = None if hit is None else {"score": hit["score"], "pass": hit["pass"],
                                                         "ref": hit.get("ref", False)}
        rows.append(row)
    summary = {lb: {"docs": len(r["docs"]), "weighted": r["weighted"],
                    "must": f"{r.get('must_passed_count', 0)}/{r.get('must_total', 0)}",
                    "passed": r["passed"]} for lb, r in results}
    return {"labels": labels, "rows": rows, "summary": summary}


def write_compare(cmp: dict, out_dir: Path, title: str, ref_labels: list[str] | None = None) -> Path:
    """compare.md와 compare.csv를 쓰고 compare.md 경로를 돌려준다.

    ref_labels: 참고값으로 표시할 결과(예: 실버 — 정답이 실버에서 출발해 점수가 높게 나온다)
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    labels = cmp["labels"]
    ref_labels = set(ref_labels or [])
    head = [lb + (" (참고)" if lb in ref_labels else "") for lb in labels]

    with open(out_dir / "compare.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["중요도", "항목", "목표"] + head)
        for r in cmp["rows"]:
            w.writerow([r["level"], r["name"], f"{r['target'] * 100:.0f}%"] +
                       ["" if c is None else f"{c['score'] * 100:.1f}" for c in (r["cells"][lb] for lb in labels)])
        s = cmp["summary"]
        w.writerow(["", "문서 수", ""] + [s[lb]["docs"] for lb in labels])
        w.writerow(["", "가중 종합", "90"] + [f"{s[lb]['weighted']:.1f}" for lb in labels])
        w.writerow(["", "필수 통과", "17/17"] + [s[lb]["must"] for lb in labels])
        w.writerow(["", "판정", ""] + ["합격" if s[lb]["passed"] else "불합격" for lb in labels])

    def cell(c):
        if c is None:
            return "-"
        mark = "" if c["pass"] else " 미달"
        return f"{c['score'] * 100:.1f}{'*' if c['ref'] else ''}{mark}"

    lines = [f"# 결과 비교: {title}", "",
             "| 중요도 | 항목 | 목표 | " + " | ".join(head) + " |",
             "|---|---|---|" + "---|" * len(labels)]
    for r in cmp["rows"]:
        lines.append(f"| {r['level']} | {r['name']} | {r['target'] * 100:.0f}% | " +
                     " | ".join(cell(r["cells"][lb]) for lb in labels) + " |")
    s = cmp["summary"]
    lines += [f"| | **문서 수** | | " + " | ".join(str(s[lb]["docs"]) for lb in labels) + " |",
              f"| | **가중 종합** | 90 | " + " | ".join(f"**{s[lb]['weighted']:.1f}**" for lb in labels) + " |",
              f"| | **필수 통과** | 17/17 | " + " | ".join(s[lb]["must"] for lb in labels) + " |",
              f"| | **판정** | | " + " | ".join("합격" if s[lb]["passed"] else "불합격" for lb in labels) + " |",
              "",
              "- 점수는 % 단위. '미달'은 목표 미만, *는 정답에 미검수 칸이 섞인 항목(D-35)."]
    if ref_labels:
        lines.append(f"- (참고) 표시 결과({', '.join(sorted(ref_labels))})는 정답이 실버에서 출발해 점수가 높게 나온다. "
                     "모델 간 우열의 근거로 쓰지 않는다.")
    out = out_dir / "compare.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out
