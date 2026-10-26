"""골드 검수 진도 (역할 F, D-35·D-36).

data/review/<문서>.xlsx를 읽어 문서마다 우선순위별 검수 진도, 1순위 교차 확인, 검수 결과 종류,
검수 시간, 골드 생성 여부를 정리한다. 엑셀은 읽기만 한다(검수표를 고치지 않는다).
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

from ..common import manifest, paths
from ..review.sheet_spec import RESULT_OPTIONS, SHEET_INFO, SHEET_MAIN

PRIORITIES = ("1", "2", "3")
EXTRA = "추가 줄"          # '누락 추가' 줄은 우선순위가 비어 있다


def _s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _parse_time(v):
    if isinstance(v, datetime):
        return v
    s = _s(v)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%m/%d %H:%M", "%H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def read_sheet(path: Path) -> dict:
    """검수표 한 개의 진도."""
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[SHEET_MAIN]
    it = ws.iter_rows(values_only=True)
    head = [_s(h) for h in next(it)]
    idx = {h: i for i, h in enumerate(head)}
    for need in ("우선순위", "검수 결과"):
        if need not in idx:
            raise ValueError(f"{path.name}: '{SHEET_MAIN}' 시트에 '{need}' 열이 없습니다 (sheet_spec.py와 다름)")
    tot, done = Counter(), Counter()
    results = Counter()
    cross_total = cross_done = 0
    for r in it:
        if not any(v not in (None, "") for v in r):
            continue
        pr = _s(r[idx["우선순위"]]) or EXTRA
        res = _s(r[idx["검수 결과"]])
        tot[pr] += 1
        if res:
            done[pr] += 1
            results[res if res in RESULT_OPTIONS else "기타"] += 1
        if pr == "1" and "교차 확인자" in idx:
            cross_total += 1
            cross_done += bool(_s(r[idx["교차 확인자"]]))
    info = {}
    if SHEET_INFO in wb.sheetnames:
        info = {_s(r[0]): r[1] for r in wb[SHEET_INFO].iter_rows(values_only=True) if r and r[0]}
    wb.close()
    start, end = _parse_time(info.get("검수 시작")), _parse_time(info.get("검수 끝"))
    minutes = int((end - start).total_seconds() // 60) if start and end and end > start else None
    return {"total": dict(tot), "done": dict(done), "results": dict(results),
            "cross": (cross_done, cross_total),
            "reviewer": _s(info.get("검수자")), "cross_checker": _s(info.get("교차 확인자")),
            "start": _s(info.get("검수 시작")), "end": _s(info.get("검수 끝")), "minutes": minutes}


def status(p: dict | None, gold: bool) -> str:
    if gold:
        return "골드 생성"
    if p is None:
        return "검수표 없음"
    t, d = p["total"], p["done"]
    if not sum(d.values()):
        return "미시작"
    if d.get("1", 0) < t.get("1", 0):
        return "1순위 진행"
    if all(d.get(k, 0) >= t.get(k, 0) for k in t):
        return "검수 완료"
    return "1순위 완료"


def collect(purpose: str | None = "개발", review_dir: Path | None = None) -> list[dict]:
    """manifest에서 고른 문서(기본: 개발용)와 검수표 폴더의 문서를 합쳐 진도 목록을 만든다."""
    review_dir = review_dir or paths.REVIEW
    try:
        rows = manifest.load()
    except FileNotFoundError:      # manifest가 아직 없는 브랜치: 검수표 폴더에 있는 문서만 본다
        rows = []
    chosen = [r for r in rows if purpose is None or r.get("purpose") == purpose]
    by_id = {r["doc_id"]: r for r in rows}
    ids = [r["doc_id"] for r in chosen]
    for f in sorted(review_dir.glob("T21-*.xlsx")):
        if f.stem not in ids:
            ids.append(f.stem)
    out = []
    for doc_id in ids:
        sheet = review_dir / f"{doc_id}.xlsx"
        p = read_sheet(sheet) if sheet.exists() else None
        gold = paths.gold_path(doc_id).exists()
        unrev = None
        up = paths.gold_unreviewed_path(doc_id)
        if up.exists():
            unrev = len(json.loads(up.read_text(encoding="utf-8")))
        m = by_id.get(doc_id, {})
        out.append({"doc_id": doc_id, "progress": p, "gold": gold, "unreviewed": unrev,
                    "reviewer": (p or {}).get("reviewer") or m.get("reviewer", ""),
                    "cross_checker": (p or {}).get("cross_checker") or m.get("cross_checker", ""),
                    "status": status(p, gold)})
    return out


def _frac(p: dict | None, key: str) -> str:
    if p is None or key not in p["total"]:
        return "-"
    return f"{p['done'].get(key, 0)}/{p['total'][key]}"


def to_markdown(items: list[dict], now: datetime | None = None) -> str:
    now = now or datetime.now()
    lines = [f"**골드 검수 진도** ({now:%m/%d %H:%M})", "",
             "| 문서 | 검수 | 교차 | 상태 | 1순위 | 2순위 | 3순위 | 추가 줄 | 1순위 교차 확인 | 걸린 시간 | 미검수(골드) |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for it in items:
        p = it["progress"]
        cross = "-" if p is None or not p["cross"][1] else f"{p['cross'][0]}/{p['cross'][1]}"
        mins = "-" if p is None or p["minutes"] is None else f"{p['minutes']}분"
        unrev = "-" if it["unreviewed"] is None else f"{it['unreviewed']}칸"
        lines.append(f"| {it['doc_id']} | {it['reviewer'] or '-'} | {it['cross_checker'] or '-'} | {it['status']} | "
                     f"{_frac(p, '1')} | {_frac(p, '2')} | {_frac(p, '3')} | {_frac(p, EXTRA)} | {cross} | {mins} | {unrev} |")
    agg = Counter()
    for it in items:
        if it["progress"]:
            agg.update(it["progress"]["results"])
    if agg:
        lines += ["", "검수 결과 종류(전체): " + ", ".join(f"{k} {agg[k]}" for k in (*RESULT_OPTIONS, "기타") if agg.get(k))]
    late = [it["doc_id"] for it in items if it["status"] in ("검수표 없음", "미시작", "1순위 진행")]
    if late:
        lines += ["", f"1순위가 끝나지 않은 문서: {', '.join(late)}"]
    return "\n".join(lines) + "\n"
