"""단계별 성적표 (역할 C): 최종 칸 점수 앞 단계에서 점수가 어디서 새는지 잰다.

score.py(칸 점수)와 score_extraction.py(행·S003 조각 합격 판정)는 그대로 두고, 그 사이 빈 곳을 잰다.
'모델 입력'은 섹션 파이프라인이 읽는 쪽 글(<입력 폴더>/<문서>/pNNN.txt, 줄 번호를 뗀 것)이다.
입력 폴더는 --pages-dir, 없으면 --pred 옆 run_info.yaml의 pages_dir, 그것도 없으면 data/pages/version17.

1. 표        data/gold/layout/table_goldset_data.json(개발 10쪽, 골드). 선 있는 표와 선 없는 배치로 나눈다.
             TEDS(입력): 모델 입력 글의 표 줄(' | ' 줄이 이어진 구간)과 비교. TEDS(파일): tables/*.md(없으면 0).
             행 보존: 행 내용이 쪽 글에 있는가. 경계 전달: 이웃한 칸 사이에 '|'가 들어갔는가.
             선 없는 배치는 PDF에 표 정보가 없어 TEDS 대신 행 보존·경계 전달로 본다
2. OCR CER   텍스트층이 정상인 쪽에서 텍스트층(data/pages/<문서>/pNNN.match.txt)을 정답 대용으로
             PaddleOCR 결과(ocr_all/)를 잰다. CER(순서 지킴), 묶음 CER(순서 무시), WER. OCR 엔진 실력의 참고값
3. 근거 글   골드 evidence.source_text(사람이 원문에서 옮겨 적은 글, 쪽 번호 있음)가 그 쪽(앞뒤 쪽 포함)
             글에 그대로 있는가. 3-1은 모델 입력 글, 3-2는 data/pages의 PaddleOCR 글과 대조한다.
             텍스트층이 깨진 쪽(S003, T21-043)은 이것이 OCR 정확도의 유일한 골드 측정이다
4. 원인 분류 (--pred가 있을 때) 채점기가 '빠뜨림·틀림'으로 남긴 필수 항목 오류마다 정답 값이
             모델 입력 글에 있는지 본다. 있으면 모델 단계, 없으면 입력 단계(전처리·OCR) 손실로 센다.
             정답 값이 코드·상태값뿐이면 '판정 불가'. 값 찾기는 휴리스틱이라(짧은 숫자는 우연히 있을 수 있다)
             비율의 방향을 보는 데 쓴다
5. 반복 안정도 (--pred와 --repeat가 있을 때) 같은 입력·설정으로 다시 돌린 결과(--repeat)와 --pred가
             칸별로 얼마나 같은가(행 순서 무시, 근거·순번 제외), 문서·항목 점수가 얼마나 흔들리는가.
             모델을 부르지 않고 결과 파일만 비교한다. 일치율이 낮은 칸이 모델이 헷갈리는 칸이다

평가 문서는 보고에만 쓴다. 이 결과를 보고 규칙·프롬프트를 고치지 않는다 (D-43).
표 TEDS는 정답이 개발 문서뿐이라 개발 문서에서만 나온다.

사용법 (backend/에서)
  python scripts/score_stages.py --purpose 개발
  python scripts/score_stages.py --purpose 개발 --pred ../runs/20261101_sections_qwen36_s10_v17_dev10_r1/outputs
  python scripts/score_stages.py --docs T21-S003 --worst 5    # 근거 글이 많이 틀린 예를 함께 적는다
  python scripts/score_stages.py --pred ../runs/<실행>_r1/outputs --repeat ../runs/<실행>_r2/outputs   # 반복 안정도
결과: runs/<날짜>_stages_<제목>/ (report.md, result.json, tables.csv, ocr_pages.csv, evidence_pages.csv, causes.csv,
      stability.csv, repeat_scores.csv)
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from _common import today
from msds.common import manifest, paths
from msds.evaluate import stage_metrics as sm
from msds.evaluate.score import score_pair
from msds.preprocess.ocr import page_text, read_ocr_json
from msds.preprocess.render import load_pages

TABLE_GOLD = paths.GOLD / "layout" / "table_goldset_data.json"
RULED = {"선있음"}      # 정답의 표 종류 중 칸 선이 그려진 표. 나머지(선없음·항목값·상자)는 위치로만 나눈 배치
DEFAULT_PAGES = paths.PAGES / "version17"
LINE_NO = re.compile(r"^L\d+\s?", re.M)
CAUSE_KINDS = ("누락", "불일치")    # 정답 값이 있는 오류. '오추출'은 정답 쪽 값이 없어 나누지 않는다
CAUSES = ("입력에 있음(모델 단계)", "입력에 없음(입력 단계)", "판정 불가")


def _pct(x: float | None) -> str:
    return "-" if x is None else f"{x * 100:.1f}%"


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _gold(doc_id: str) -> dict | None:
    p = paths.GOLD / f"{doc_id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def input_pages(doc_id: str, pages_dir: Path) -> dict[int, dict]:
    """모델 입력 쪽 글. {쪽: {text, state, source, tables}} (source는 meta의 text_source)."""
    d = pages_dir / doc_id
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    out = {}
    for p in meta["pages"]:
        f = d / (p.get("text_file") or f"p{p['page']:03d}.txt")
        text = LINE_NO.sub("", f.read_text(encoding="utf-8")) if f.exists() else ""
        out[p["page"]] = {"text": text, "state": p.get("state"), "source": p.get("text_source") or "텍스트층",
                          "tables": p.get("tables", [])}
    return out


# ── 1. 표 TEDS ──────────────────────────────────────────
def _match(gold_tables: list[dict], preds: dict[str, list[list[str]]]) -> list[dict]:
    """정답 표마다 쪽 안에서 TEDS가 가장 높은 예측 표를 하나씩 짝짓는다(한 번 쓴 예측 표는 다시 쓰지 않는다)."""
    trees = {k: sm.table_tree(rows) for k, rows in preds.items()}
    used: set[str] = set()
    out = []
    for t in gold_tables:
        g = sm.table_tree(t["rows"], t.get("spans"))
        best, name = max(((sm.teds(g, tr), k) for k, tr in trees.items() if k not in used), default=(0.0, None))
        if name is not None:
            used.add(name)
        out.append({"teds": best, "teds_s": sm.teds(g, trees[name], structure_only=True) if name is not None else 0.0,
                    "rows": len(preds[name]) if name is not None else 0, "name": name})
    return out


def score_tables(doc_ids: set[str], pages_dir: Path) -> list[dict]:
    """정답 표를 두 가지 예측과 비교한다.
    - 입력: 모델 입력 글의 표 줄(' | ' 줄이 이어진 구간). 모델이 실제로 받은 표
    - 파일: 전처리가 따로 저장한 tables/*.md. 표 파일을 만들지 않은 쪽은 0
    """
    gold = json.loads(TABLE_GOLD.read_text(encoding="utf-8"))
    out = []
    for p in gold["pages"]:
        if p["doc_id"] not in doc_ids:
            continue
        page = input_pages(p["doc_id"], pages_dir)[p["page"]]
        md = {t["file"]: sm.read_md_table((pages_dir / p["doc_id"] / t["file"]).read_text(encoding="utf-8"))
              for t in page["tables"]}
        lines = {f"줄표{i + 1}": rows for i, rows in enumerate(sm.line_tables(page["text"]))}
        flat = sm.normalize(page["text"])
        for k, (t, mi, mf) in enumerate(zip(p["tables"], _match(p["tables"], lines), _match(p["tables"], md))):
            rows = [r for r in t["rows"] if any(c.strip() for c in r)]
            bound = [b for b in (sm.boundary_kept(r, flat) for r in rows) if b is not None]
            out.append({
                "group": "선 있는 표" if t.get("kind") in RULED else "선 없는 표",
                "doc_id": p["doc_id"], "page": p["page"], "table": k + 1, "kind": t.get("kind"),
                "first_cell": (t["rows"][0][0] if t["rows"] else "")[:20], "gold_rows": len(t["rows"]),
                "in_rows": mi["rows"], "teds_in": mi["teds"], "teds_s_in": mi["teds_s"],
                "md_rows": mf["rows"], "teds_md": mf["teds"], "teds_s_md": mf["teds_s"], "md_file": mf["name"] or "",
                "rows_n": len(rows), "rows_kept": sum(sm.row_kept(r, flat) for r in rows),
                "bound_n": len(bound), "bound_kept": sum(bound),
            })
    return out


# ── 2. OCR CER (텍스트층 정답 대용) ────────────────────────
def score_ocr_pages(doc_ids: list[str]) -> list[dict]:
    out = []
    for d in doc_ids:
        if not (paths.page_dir(d) / "meta.json").exists():   # data/pages에 전처리 결과가 없는 문서
            continue
        for p in load_pages(d)["pages"]:
            f = paths.page_dir(d) / "ocr_all" / f"p{p['page']:03d}.ocr.json"
            if p["state"] != "정상" or p["source"] != "텍스트층" or not f.exists():
                continue
            ref = LINE_NO.sub("", p["match_text"])
            hyp = page_text(*read_ocr_json(f))
            out.append({"doc_id": d, "page": p["page"], "chars": len(sm.normalize(ref)),
                        "cer": sm.cer(ref, hyp), "bag_cer": sm.bag_cer(ref, hyp), "wer": sm.wer(ref, hyp)})
    return out


# ── 3. 근거 글 대조 ──────────────────────────────────────
def _ocr_text(doc_id: str, page: int) -> str | None:
    """data/pages의 PaddleOCR 글. 깨진 쪽은 pNNN.ocr.json, 텍스트층 쪽은 비교용 ocr_all/pNNN.ocr.json."""
    for f in (paths.page_dir(doc_id) / f"p{page:03d}.ocr.json",
              paths.page_dir(doc_id) / "ocr_all" / f"p{page:03d}.ocr.json"):
        if f.exists():
            return page_text(*read_ocr_json(f))
    return None


def _best(snippet: str, texts: list[str]) -> dict:
    """여러 쪽 글 중 근거 글과 가장 잘 맞는 쪽의 점수."""
    return min((sm.snippet_score(snippet, t) for t in texts), key=lambda s: s["errors"])


def _input_label(p: dict) -> str:
    return p["source"] if p["text"].strip() else "글 없음(이미지만)"


def _page_kind(p: dict) -> str:
    return "텍스트층 정상 쪽" if p["state"] == "정상" and p["source"] == "텍스트층" else "텍스트층 없음·깨짐 쪽"


def score_evidence(doc_ids: list[str], pages_dir: Path, worst: int) -> tuple[list[dict], list[dict]]:
    """쪽마다 근거 글을 두 글과 대조한다: 모델 입력 글(in_), data/pages의 PaddleOCR 글(ocr_)."""
    rows, bad = [], []
    for d in doc_ids:
        gold = _gold(d)
        if not gold:
            continue
        pages = input_pages(d, pages_dir)
        ocr: dict[int, str | None] = {}
        acc: dict[int, dict] = defaultdict(lambda: dict.fromkeys(
            ("n", "chars", "in_exact", "in_errors", "ocr_n", "ocr_exact", "ocr_errors"), 0))
        for page, text in sm.dedupe_evidence([e for m in gold["msds"] for e in m.get("evidence", [])]):
            if page not in pages:
                continue
            near = [n for n in (page, page - 1, page + 1) if n in pages]   # 근거 쪽 번호가 하나 어긋난 것은 봐준다
            for n in near:
                if n not in ocr:
                    ocr[n] = _ocr_text(d, n)
            a = acc[page]
            s = _best(text, [pages[n]["text"] for n in near])
            a["n"] += 1
            a["chars"] += s["chars"]
            a["in_exact"] += s["exact"]
            a["in_errors"] += s["errors"]
            if ocr[page] is not None:
                o = _best(text, [ocr[n] for n in near if ocr[n] is not None])
                a["ocr_n"] += 1
                a["ocr_exact"] += o["exact"]
                a["ocr_errors"] += o["errors"]
            if not s["exact"]:
                bad.append({"doc_id": d, "page": page, "input": _input_label(pages[page]),
                            "rate": s["errors"] / max(s["chars"], 1), "text": text})
        for page, a in sorted(acc.items()):
            rows.append({"doc_id": d, "page": page, "input": _input_label(pages[page]),
                         "kind": _page_kind(pages[page]), **a})
    bad.sort(key=lambda b: -b["rate"])
    return rows, bad[:worst] if worst else []


def summarize_evidence(rows: list[dict]) -> dict[str, dict]:
    """입력 출처별(3-1, 모델 입력 대조)과 쪽 종류별(3-2, PaddleOCR 대조) 요약."""
    def agg(rs, pre, n_key):
        rs = [r for r in rs if r[n_key]]
        n, ch = sum(r[n_key] for r in rs), sum(r["chars"] for r in rs)
        return {"docs": len({r["doc_id"] for r in rs}), "pages": len(rs), "snippets": n,
                "exact_rate": sum(r[pre + "exact"] for r in rs) / n if n else None,
                "cer": sum(r[pre + "errors"] for r in rs) / ch if ch else None}
    return {
        "input": {k: agg([r for r in rows if r["input"] == k], "in_", "n") for k in sorted({r["input"] for r in rows})},
        "ocr": {k: agg([r for r in rows if r["kind"] == k], "ocr_", "ocr_n") for k in sorted({r["kind"] for r in rows})},
    }


# ── 4. 틀린 칸 원인 분류 ──────────────────────────────────
def classify_errors(doc_ids: list[str], pred_dir: Path, pages_dir: Path) -> list[dict]:
    out = []
    for d in doc_ids:
        gold, pf = _gold(d), pred_dir / f"{d}.json"
        if not gold or not pf.exists():
            continue
        r = score_pair(gold, json.loads(pf.read_text(encoding="utf-8")))
        text = "\n".join(p["text"] for p in input_pages(d, pages_dir).values())
        for item, kind, content in r["details"]:
            if kind not in CAUSE_KINDS:
                continue
            vals = sm.detail_values(content)
            if not vals:
                cause = CAUSES[2]
            elif all(sm.value_found(v, text) for v in vals):
                cause = CAUSES[0]
            else:
                cause = CAUSES[1]
            out.append({"doc_id": d, "item": item, "kind": kind, "cause": cause,
                        "values": " / ".join(vals), "content": str(content)})
    return out


# ── 5. 반복 실행 안정도 ───────────────────────────────────
FIELD_LABELS = {
    "meta": "관리정보", "product": "1항 제품", "companies": "1항 회사", "hazard": "2항 유해성",
    "composition": "3항 구성", "components": "3항 성분", "exposure_limits": "8항 노출기준", "physchem": "9항 물성",
    "toxicity": "11항 독성", "cmr": "11항 CMR", "ecotox": "12항 생태", "transport": "14항 운송",
    "regulations": "15항 국내 규제", "dangerous_goods": "15항 위험물", "waste": "15항 폐기물",
    "intl_class": "15항 해외 분류", "narratives": "서술 문장", "extras": "분류 못 한 줄(extras)",
}


def score_repeats(doc_ids: list[str], runs: list[Path]) -> tuple[list[dict], list[dict], list[str]]:
    """runs[0]과 나머지 실행을 문서마다 비교한다. (칸 일치 행, 실행별 점수 행, 경고)."""
    agree, scores, warns = [], [], []
    for d in doc_ids:
        outs = [r / f"{d}.json" for r in runs]
        if not all(o.exists() for o in outs):
            continue
        docs = [json.loads(o.read_text(encoding="utf-8")) for o in outs]
        base = docs[0]["msds"]
        for k, other in enumerate(docs[1:], 1):
            if len(other["msds"]) != len(base):
                warns.append(f"{d}: MSDS 수가 다름 ({len(base)} vs {len(other['msds'])}, 실행 {k + 1}). 앞쪽 MSDS끼리만 비교")
            for i in range(min(len(base), len(other["msds"]))):
                for field, v in sm.field_agreement(base[i], other["msds"][i]).items():
                    agree.append({"doc_id": d, "run": k + 1, "msds": i, "field": field, **v})
        gold = _gold(d)
        if gold:
            rs = [score_pair(gold, x) for x in docs]
            scores.append({"doc_id": d, "weighted": [r["weighted"] for r in rs],
                           "items": {i["name"]: [r["items"][n]["score"] for r in rs]
                                     for n, i in enumerate(rs[0]["items"])}})
    return agree, scores, warns


def summarize_repeats(agree: list[dict], scores: list[dict]) -> dict:
    by: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for a in agree:
        by[a["field"]][0] += a["same"]
        by[a["field"]][1] += a["total"]
    same, tot = sum(v[0] for v in by.values()), sum(v[1] for v in by.values())
    ns, nt = same - by["extras"][0], tot - by["extras"][1]
    item_swing: dict[str, list[float]] = defaultdict(list)
    for s in scores:
        for name, vals in s["items"].items():
            item_swing[name].append(max(vals) - min(vals))
    return {
        "rows": {"same": same, "total": tot, "rate": same / tot if tot else None,
                 "rate_no_extras": ns / nt if nt else None},
        "fields": {f: {"same": v[0], "total": v[1], "rate": v[0] / v[1] if v[1] else None} for f, v in by.items()},
        "doc_swing": {s["doc_id"]: max(s["weighted"]) - min(s["weighted"]) for s in scores},
        "mean_weighted": [sum(s["weighted"][k] for s in scores) / len(scores) for k in range(len(scores[0]["weighted"]))]
        if scores else [],
        "item_swing": {n: {"mean": sum(v) / len(v), "max": max(v)} for n, v in item_swing.items()},
    }


def _repeat_lines(rep: dict, runs: list[Path], scores: list[dict], warns: list[str]) -> list[str]:
    r = rep["rows"]
    L = ["", "## 5. 반복 실행 안정도", "",
         "같은 입력·설정으로 다시 돌린 결과가 얼마나 같은가. 모델을 부르지 않고 결과 파일만 비교한다.", ""]
    L += [f"- 실행 {k + 1}: {p}" for k, p in enumerate(runs)]
    L += ["", f"- 행 일치율 **{_pct(r['rate'])}** ({r['same']}/{r['total']}행), 분류 못 한 줄(extras) 빼면 "
          f"**{_pct(r['rate_no_extras'])}**",
          "- 행 순서·순번·근거 기록은 보지 않는다. 행 안의 칸 하나만 달라도 다른 행으로 센다(엄격한 기준)",
          "- 점수 평균: " + " → ".join(f"{x:.1f}" for x in rep["mean_weighted"])
          + " (평균은 비슷해도 문서별로는 크게 흔들릴 수 있다. 아래 표)"]
    L += [f"- 주의: {w}" for w in warns]
    L += ["", "### 칸별 일치율 (낮은 순)", "", "| 칸 | 행 | 일치율 |", "|---|---|---|"]
    for f, v in sorted(rep["fields"].items(), key=lambda kv: (kv[1]["rate"] is None, kv[1]["rate"] or 0)):
        if v["total"]:
            L.append(f"| {FIELD_LABELS.get(f, f)} | {v['total']} | {_pct(v['rate'])} |")
    if scores:
        L += ["", "### 문서별 점수 (가중 종합)", "",
              "| 문서 | " + " | ".join(f"실행 {k + 1}" for k in range(len(runs))) + " | 차이 |",
              "|---|" + "---|" * (len(runs) + 1)]
        for s in sorted(scores, key=lambda s: -(max(s["weighted"]) - min(s["weighted"]))):
            L.append(f"| {s['doc_id']} | " + " | ".join(f"{x:.1f}" for x in s["weighted"])
                     + f" | {max(s['weighted']) - min(s['weighted']):.1f} |")
        L += ["", "### 항목 점수가 많이 흔들린 항목", "", "| 항목 | 문서 평균 흔들림 | 가장 큰 흔들림 |", "|---|---|---|"]
        for n, v in sorted(rep["item_swing"].items(), key=lambda kv: -kv[1]["mean"])[:10]:
            if v["max"] > 0:
                L.append(f"| {n} | {v['mean'] * 100:.1f}점 | {v['max'] * 100:.1f}점 |")
    return L


# ── 성적표 ──────────────────────────────────────────────
def _csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def _rate(rows: list[dict], ok: str, n: str) -> float | None:
    total = sum(r[n] for r in rows)
    return sum(r[ok] for r in rows) / total if total else None


def _table_summary(ts: list[dict]) -> dict:
    return {"n": len(ts), "teds_in": _mean([t["teds_in"] for t in ts]),
            "teds_s_in": _mean([t["teds_s_in"] for t in ts]),
            "md_found": sum(1 for t in ts if t["md_file"]), "teds_md": _mean([t["teds_md"] for t in ts]),
            "rows_n": sum(t["rows_n"] for t in ts), "row_kept": _rate(ts, "rows_kept", "rows_n"),
            "bound_n": sum(t["bound_n"] for t in ts), "boundary": _rate(ts, "bound_kept", "bound_n")}


def summarize(tables: list[dict], ocr: list[dict], ev_rows: list[dict], causes: list[dict] | None) -> dict:
    ocr_w = sum(r["chars"] for r in ocr)
    wavg = lambda k: sum(r[k] * r["chars"] for r in ocr) / ocr_w if ocr_w else None  # noqa: E731
    return {
        "tables": {g: _table_summary([t for t in tables if t["group"] == g]) for g in ("선 있는 표", "선 없는 표")},
        "ocr": {"pages": len(ocr), "chars": ocr_w, "cer": wavg("cer"), "bag_cer": wavg("bag_cer"),
                "wer": wavg("wer")},
        "evidence": summarize_evidence(ev_rows),
        "causes": dict(Counter(c["cause"] for c in causes)) if causes is not None else None,
    }


def _table_lines(tables: list[dict], t: dict) -> list[str]:
    if not tables:
        return ["- 표 정답이 있는 문서가 없다 (표 정답은 개발 문서 10쪽뿐)"]
    r, u = t["선 있는 표"], t["선 없는 표"]
    L = ["정답 표를 칸 선이 그려진 표(정답 종류 '선있음')와 위치로만 나눈 배치(선없음·항목값·상자)로 나눠 잰다.",
         "선 없는 배치는 PDF에 표 정보가 없어, 전처리가 표로 볼지부터 갈린다. 그래서 TEDS 대신 행 보존과 경계 전달로 본다.",
         "", "| 묶음 | 표 | 행 | TEDS(입력) | TEDS(파일) | 행 보존 | 경계 전달 |", "|---|---|---|---|---|---|---|"]
    for name, x in (("선 있는 표", r), ("선 없는 표", u)):
        L.append(f"| {name} | {x['n']} | {x['rows_n']} | {_pct(x['teds_in'])} | {_pct(x['teds_md'])} "
                 f"(파일 {x['md_found']}개) | {_pct(x['row_kept'])} | {_pct(x['boundary'])} ({x['bound_n']}행) |")
    L += ["", "- **TEDS(입력)**: 모델 입력 글에서 칸 구분(' | ') 줄이 이어진 구간을 표로 보고 짝지은 값. 모델이 받은 표 구조",
          "- TEDS(파일): 전처리가 따로 저장한 tables/*.md와 짝지은 값. 파일이 없는 표는 0이라 참고로만 본다",
          "- **행 보존**: 행의 칸 글자를 이은 것이 쪽 글 한 구간에 있는 비율(줄바꿈·띄어쓰기·'|' 무시, 글자 10%까지 봐줌). 내용이 들어갔는가",
          "- **경계 전달**: 글이 든 칸이 둘 이상인 행 중, 이웃한 칸 사이에 '|'가 들어간 행의 비율. 모델이 항목과 값의 경계를 받았는가",
          "- 줄 표에는 병합 칸 정보가 없어, 정답에 병합 칸이 있으면 글자가 다 맞아도 TEDS가 100%가 되지 않는다",
          "", "### 표별", "",
          "| 묶음 | 문서 | 쪽 | 표 | 종류 | 첫 칸 | 정답 행 | TEDS(입력) | TEDS(파일) | 행 보존 | 경계 전달 |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for x in sorted(tables, key=lambda x: x["group"] != "선 있는 표"):
        L.append(f"| {x['group']} | {x['doc_id']} | {x['page']} | {x['table']} | {x['kind']} | {x['first_cell']} | "
                 f"{x['gold_rows']} | {_pct(x['teds_in'])} | {_pct(x['teds_md'])} | {x['rows_kept']}/{x['rows_n']} | "
                 f"{x['bound_kept']}/{x['bound_n']} |")
    return L


def _evidence_table(rows: dict[str, dict], head: str) -> list[str]:
    L = [f"| {head} | 문서 | 쪽 | 근거 글 | 그대로 있음 | 근거 글 CER |", "|---|---|---|---|---|---|"]
    for k, s in rows.items():
        L.append(f"| {k} | {s['docs']} | {s['pages']} | {s['snippets']} | {_pct(s['exact_rate'])} | {_pct(s['cer'])} |")
    return L


def _cause_lines(causes: list[dict], pred: Path) -> list[str]:
    c = Counter(x["cause"] for x in causes)
    tot = sum(c.values())
    L = ["", "## 4. 틀린 칸 원인 (필수 항목의 빠뜨림·틀림)", "", f"- 결과: {pred}", ""]
    L += [f"- {k}: {c.get(k, 0)}건 ({_pct(c.get(k, 0) / tot if tot else None)})" for k in CAUSES]
    by_item: dict[str, Counter] = defaultdict(Counter)
    for x in causes:
        by_item[x["item"]][x["cause"]] += 1
    L += ["", "| 항목 | 모델 단계 | 입력 단계 | 판정 불가 |", "|---|---|---|---|"]
    for item, cc in sorted(by_item.items(), key=lambda kv: -sum(kv[1].values())):
        L.append(f"| {item} | {cc[CAUSES[0]]} | {cc[CAUSES[1]]} | {cc[CAUSES[2]]} |")
    return L + ["", "- 정답 값 찾기는 휴리스틱이다. 짧은 숫자는 우연히 있을 수 있어 '모델 단계'가 조금 많게 나올 수 있다",
                "- 정답이 원문 표기를 바꾼 값(날짜 형식, ㈜→(주) 등)은 '입력 단계'로 잘못 셀 수 있다. causes.csv로 확인한다"]


def write_report(out_dir: Path, title: str, purpose: str, docs: list[str], pages_dir: Path, tables: list[dict],
                 ocr: list[dict], ev_rows: list[dict], ev_bad: list[dict], causes: list[dict] | None,
                 pred: Path | None, repeats: tuple | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    _csv(out_dir / "tables.csv", tables)
    _csv(out_dir / "ocr_pages.csv", ocr)
    _csv(out_dir / "evidence_pages.csv", ev_rows)
    if causes:
        _csv(out_dir / "causes.csv", causes)
    s = summarize(tables, ocr, ev_rows, causes)
    if repeats:
        runs, agree, rscores, warns = repeats
        _csv(out_dir / "stability.csv", agree)
        _csv(out_dir / "repeat_scores.csv", [{"doc_id": x["doc_id"], **{f"run{k + 1}": w for k, w in enumerate(x["weighted"])}}
                                            for x in rscores])
        s["repeat"] = {"runs": [str(r) for r in runs], **summarize_repeats(agree, rscores)}
    meta = {"title": title, "purpose": purpose, "docs": docs, "pages_dir": str(pages_dir),
            "pred": str(pred) if pred else None}
    (out_dir / "result.json").write_text(json.dumps({**meta, **s}, ensure_ascii=False, indent=1), encoding="utf-8")

    o = s["ocr"]
    L = [f"# 단계별 성적표: {title}", "", f"- 문서 {len(docs)}건 ({purpose}): {', '.join(docs)}",
         f"- 모델 입력 폴더: {pages_dir}"]
    if purpose != "개발":
        L.append("- **평가 문서 포함: 보고용이다. 이 결과로 규칙·프롬프트를 고치지 않는다 (D-43).**")
    L += ["", "## 1. 표 구조 (선 있는 표·선 없는 배치)", ""] + _table_lines(tables, s["tables"])
    L += ["", "## 2. OCR 글자 오류율 (텍스트층 정답 대용)", "",
          f"- 정상 텍스트층 쪽 {o['pages']}쪽, 정답 글자 {o['chars']:,}자 (글자 수 가중 평균)",
          f"- CER(순서 지킴) **{_pct(o['cer'])}**, 묶음 CER(순서 무시) **{_pct(o['bag_cer'])}**, WER {_pct(o['wer'])}",
          "- 진짜 글자 오류율은 대개 두 CER 사이다. 차이가 크면 글자보다 읽기 순서 차이가 크다",
          "- WER은 띄어쓰기 차이까지 세서 한국어에서는 크게 나온다. 비교용으로만 본다",
          "- 텍스트층이 깨진 쪽은 정답 대용이 없어 여기서 잴 수 없다. 그 쪽은 3번에서 잰다"]
    L += ["", "## 3. 정답 근거 글 대조 (골드 evidence.source_text)", "",
          "근거 글은 사람이 원문에서 옮겨 적은 글이다. 표 칸(' | ')·줄임표는 나눠 따로 찾고, 그림문자 설명은 뺀다.",
          "", "### 3-1. 모델 입력 글에 그대로 있는가 (입력 출처별)", ""]
    L += _evidence_table(s["evidence"]["input"], "입력 출처")
    L += ["", "### 3-2. PaddleOCR 글에 그대로 있는가 (쪽 종류별)", ""]
    L += _evidence_table(s["evidence"]["ocr"], "쪽 종류")
    L += ["", "- 3-2의 텍스트층 정상 쪽 OCR은 비교용으로 따로 돌린 것(data/pages/<문서>/ocr_all/)이다",
          "- 근거 쪽 번호가 하나 어긋난 것은 앞뒤 쪽까지 찾아 봐준다",
          "- 사람이 표기를 다듬어 적은 근거 글(목록을 풀어 적음 등)은 틀림으로 센다. "
          "텍스트층 정상 쪽의 3-1 값이 이 방법의 천장이다"]
    if ev_bad:
        L += ["", "### 모델 입력에서 많이 틀린 근거 글", "", "| 문서 | 쪽 | 입력 출처 | 틀린 비율 | 근거 글 |",
              "|---|---|---|---|---|"]
        for b in ev_bad:
            L.append(f"| {b['doc_id']} | {b['page']} | {b['input']} | {_pct(b['rate'])} | "
                     f"{b['text'][:60].replace('|', '/')} |")
    if causes is not None:
        L += _cause_lines(causes, pred)
    if repeats:
        L += _repeat_lines(s["repeat"], repeats[0], repeats[2], repeats[3])
    out = out_dir / "report.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    return out


def resolve_pages_dir(arg: Path | None, pred: Path | None) -> Path:
    if arg:
        return arg.resolve()
    info = pred.parent / "run_info.yaml" if pred else None
    if info and info.exists():
        pd = (yaml.safe_load(info.read_text(encoding="utf-8")) or {}).get("pages_dir")
        if pd:
            return (paths.ROOT / pd).resolve()
    return DEFAULT_PAGES if DEFAULT_PAGES.is_dir() else paths.PAGES


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--purpose", default="개발", help="개발 / 평가 (manifest의 purpose)")
    ap.add_argument("--docs", nargs="*", help="특정 문서만")
    ap.add_argument("--pred", type=Path, help="원인 분류에 쓸 결과 폴더 (runs/.../outputs)")
    ap.add_argument("--repeat", type=Path, nargs="+", help="--pred와 같은 설정으로 다시 돌린 결과 폴더 (반복 안정도)")
    ap.add_argument("--pages-dir", type=Path, help="모델 입력 쪽 글 폴더 (기본: run_info.yaml 또는 data/pages/version17)")
    ap.add_argument("--title", default=None)
    ap.add_argument("--worst", type=int, default=10, help="많이 틀린 근거 글 몇 개를 적을지")
    a = ap.parse_args()

    pages_dir = resolve_pages_dir(a.pages_dir, a.pred)
    rows = manifest.select(purpose=None if a.docs else a.purpose, doc_ids=a.docs)
    docs = [r["doc_id"] for r in rows if (pages_dir / r["doc_id"] / "meta.json").exists()]
    if not docs:
        raise SystemExit(f"문서가 없습니다. --purpose 또는 --docs와 {pages_dir}를 확인하세요")
    purpose = "개발" if all(r["purpose"] == "개발" for r in rows if r["doc_id"] in docs) else "평가 포함"
    tables = score_tables(set(docs), pages_dir)
    ocr = score_ocr_pages(docs)
    ev_rows, ev_bad = score_evidence(docs, pages_dir, a.worst)
    causes = classify_errors(docs, a.pred, pages_dir) if a.pred else None
    if a.repeat and not a.pred:
        raise SystemExit("--repeat는 --pred와 함께 쓴다 (--pred가 기준 실행)")
    repeats = None
    if a.repeat:
        runs = [a.pred, *a.repeat]
        repeats = (runs, *score_repeats(docs, runs))
    title = a.title or ("개발" if purpose == "개발" else "평가")
    out = write_report(paths.RUNS / f"{today()}_stages_{title}", title, purpose, docs, pages_dir, tables, ocr,
                       ev_rows, ev_bad, causes, a.pred, repeats)
    print(out.read_text(encoding="utf-8"))
