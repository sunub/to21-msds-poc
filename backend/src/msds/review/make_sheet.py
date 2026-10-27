"""검수표 만들기 — 역할 A가 채운다 (D-36).

입력: GPT 실버, Claude 실버, 각 실버의 검수 정보, 쪽 텍스트층, TO21 검증기 결과
출력: data/review/<문서번호>.xlsx  (형식은 sheet_spec.py)

이미 있는 도구 (그대로 쓴다)
- common.align.keyed_flatten(msds_item)   칸 단위로 펼치되 목록은 '무엇인지'로 짝지은 경로
- common.align.item_path_map / to_keyed   근거의 번호 경로 → 키 경로
- common.align.generic(path)              번호·키를 지운 경로 (칸 이름표 만들 때)
- common.priority.priority_of(path)       1·2·3순위
- common.jsonpath.to_cell(value)          엑셀 칸에 넣을 글자
- checks.source_match.match(...)          원문 대조 (C가 만든다)
- checks.validator.run_to21_validator(doc) TO21 검증기

완료 확인: pytest tests/test_A_review.py
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import openpyxl
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from msds.checks import source_match
from msds.checks.validator import run_to21_validator
from msds.common import manifest, paths
from msds.common.align import generic, item_path_map, keyed_flatten, to_keyed
from msds.common.jsonpath import to_cell
from msds.common.priority import priority_of
from msds.preprocess.render import load_pages

from .sheet_spec import (COLUMNS, EXCLUDED_TOP, INFO_FIELDS, MATCH_ORDER, RESULT_OPTIONS,  # noqa: F401
                         SHEET_INFO, SHEET_MAIN)

EMPTY = (None, [], {})
SRC_ORDER = {"불일치": 0, "대조불가": 1, "": 2, "일치": 2}
MODELS = {"gpt": "GPT", "claude": "Claude"}
HUMAN_FILL = PatternFill("solid", fgColor="FFF2CC")     # 사람이 쓰는 열 머리글
WIDTHS = {"경로": 30, "칸 이름": 45, "GPT 값": 30, "Claude 값": 30, "GPT 원문 조각": 45,
          "Claude 원문 조각": 45, "설명": 40, "검수 결과": 14, "수정값": 30, "수정 원문 조각": 40, "메모": 30}


def cell_of(v) -> str:
    """칸 글자. JSON으로 읽히는 글자("1", "true", '"a"')는 따옴표로 감싸 되읽어도 글자로 남게 한다."""
    if isinstance(v, str):
        if v == "" or v != v.strip():      # 빈 글자, 앞뒤 공백 있는 글자(읽을 때 잘린다)
            return json.dumps(v, ensure_ascii=False)
        try:
            json.loads(v)
        except ValueError:
            return v
        return json.dumps(v, ensure_ascii=False)
    return to_cell(v)


def flat_doc(doc: dict) -> dict:
    """{'msds[i].키경로': (i, 키경로, 값)}. evidence·validation은 뺀다."""
    out = {}
    for i, m in enumerate(doc.get("msds") or []):
        for p, v in keyed_flatten(m):
            if re.split(r"[.\[]", p, maxsplit=1)[0] in EXCLUDED_TOP:
                continue
            out[f"msds[{i}].{p}"] = (i, p, v)
    return out


def same(a, b) -> bool:
    if isinstance(a, str) and isinstance(b, str):      # 글 칸: 공백 차이만 무시 (D-9)
        return re.sub(r"\s+", "", a) == re.sub(r"\s+", "", b)
    return a == b                                       # 코드·숫자·숫자 묶음: 그대로


def prefix_index(doc: dict, items: list[dict]) -> dict:
    """근거(필드 + msds_index)·검증기(msds[i].필드)의 번호 경로 → 'msds[i].키경로' 색인."""
    maps = {i: item_path_map(m) for i, m in enumerate(doc.get("msds") or [])}
    out = {}
    for it in items:
        f, mi = it.get("field") or "", it.get("msds_index")
        mm = re.match(r"msds\[(\d+)\]\.(.*)", f)      # 검증기 형태
        if mm:
            mi, f = int(mm.group(1)), mm.group(2)
        if mi is None or mi not in maps:
            continue
        out.setdefault(f"msds[{mi}]." + to_keyed(f, maps[mi]), []).append(it)
    return out


def lookup(index: dict, path: str) -> list[dict]:
    """줄의 경로와 같거나 가장 길게 앞부분이 맞는 항목."""
    best = ""
    for k in index:
        if (path == k or path.startswith(k + ".") or path.startswith(k + "[")) and len(k) > len(best):
            best = k
    return index.get(best, []) if best else []


@lru_cache(maxsize=1)
def _spec_names() -> dict[str, str]:
    """TO21 명세서 1_항목정의: 'components[].content' → '3항 성분 · 함유량'."""
    wb = openpyxl.load_workbook(paths.to21_file("spec"), read_only=True, data_only=True)
    out = {}
    for r in wb["1_항목정의"].iter_rows(min_row=5, values_only=True):
        if len(r) > 4 and r[3] and str(r[3]).startswith("msds[]."):
            sec, big = re.match(r"\d+항", str(r[1] or "")), str(r[1] or "")
            head = f"{sec.group(0)} {r[2]}" if sec else (r[2] if "(" in big else big)   # 서술형(4·5·…항) → 서술
            name = f"{head} · {r[4]}"
            out[str(r[3])[7:]] = out[str(r[3])[7:].removesuffix("[]")] = name   # 글자 목록은 [] 없이도
    wb.close()
    return out


def label_of(kp: str) -> str:
    """칸 이름: 명세서 한글 이름 + 목록 키. 예: 15항 법적규제 위험물 · 해당 여부 (MIX / ...)"""
    g, names = generic(kp), _spec_names()
    name, cut = names.get(g), g
    while name is None and re.search(r"[.\[]", cut):      # Q·STMT 같은 묶음 칸은 앞부분 이름을 쓴다
        cut = re.sub(r"(\.[^.\[]*|\[\])$", "", cut)
        name = names.get(cut)
    name = f"{name} ({g})" if name and cut != g else (name or g)
    keys = [k for ks in re.findall(r"\[k=([^\]]*)\]", kp) for k in ks.split("|") if k]
    return f"{name} ({' / '.join(keys)})" if keys else name


def _evidence_cols(items: list[dict]) -> tuple[str, str, str, str]:
    texts = list(dict.fromkeys(it["source_text"] for it in items if it.get("source_text")))
    pages = list(dict.fromkeys(str(it["page"]) for it in items if it.get("page") is not None))
    rules = list(dict.fromkeys(r for it in items for r in it.get("rules") or []))
    notes = list(dict.fromkeys(it["note"] for it in items if it.get("note")))
    return " / ".join(texts), ", ".join(pages), ", ".join(rules), " / ".join(notes)


def _source_check(items: list[dict], page_texts: dict, page_states: dict) -> str:
    """두 모델 중 하나라도 불일치면 불일치, 하나라도 일치면 일치, 나머지는 대조불가. C의 함수가 없으면 빈 칸."""
    results = set()
    for it in items:
        try:
            results.add(source_match.match(it.get("source_text"), it.get("page"), page_texts, page_states)["result"])
        except NotImplementedError:
            return ""
    for r in ("불일치", "일치"):
        if r in results:
            return r
    return "대조불가" if items else ""


def build_rows(gpt_doc: dict, claude_doc: dict,
               gpt_review: list[dict], claude_review: list[dict],
               page_texts: dict[int, str], validator_results: dict[str, list[dict]],
               page_states: dict[int, str] | None = None) -> list[dict]:
    """검수표의 행 목록. 행은 COLUMNS를 키로 가진 dict (D-36)."""
    docs = {"gpt": gpt_doc, "claude": claude_doc}
    flat = {m: flat_doc(d) for m, d in docs.items()}
    ev = {m: prefix_index(docs[m], r) for m, r in (("gpt", gpt_review), ("claude", claude_review))}
    val = {m: prefix_index(docs[m], validator_results.get(m) or []) for m in docs}
    counts = {m: len(d.get("msds") or []) for m, d in docs.items()}
    G, C = flat["gpt"], flat["claude"]

    rows = []
    for path in list(G) + [p for p in C if p not in G]:     # 합집합
        i, kp, gv = G.get(path, (None, None, None))
        i2, kp2, cv = C.get(path, (None, None, None))
        if gv in EMPTY and cv in EMPTY:                     # 둘 다 비었으면 줄을 만들지 않는다
            continue
        kp, i = kp or kp2, i if i is not None else i2
        if path in G and path in C:
            match_state = "일치" if same(gv, cv) else "불일치"
        else:
            match_state = "GPT만" if path in G else "Claude만"

        row = dict.fromkeys(COLUMNS, "")
        row.update({"경로": path, "칸 이름": label_of(kp), "우선순위": priority_of(kp),
                    "GPT 값": cell_of(gv) if path in G else "", "Claude 값": cell_of(cv) if path in C else "",
                    "일치": match_state})
        found, rules, notes = [], [], []
        for m, tag in MODELS.items():
            items = lookup(ev[m], path)
            found += items
            text, page, r, n = _evidence_cols(items)
            row[f"{tag} 원문 조각"], row[f"{tag} 쪽"] = text, page
            rules += [x for x in r.split(", ") if x]
            notes += [f"{tag}: {n}"] if n else []
        row["적용 규칙"] = ", ".join(dict.fromkeys(rules))
        row["설명"] = " / ".join(notes)
        row["원문 대조"] = _source_check(found, page_texts, page_states or {})
        row["검증기"] = " / ".join(dict.fromkeys(
            f"{v.get('level')} {v.get('rule')} {v.get('message')} ({tag})"
            for m, tag in MODELS.items() for v in lookup(val[m], path)))
        if 0 < min(counts.values()) and counts["gpt"] != counts["claude"] and i >= min(counts.values()):  # 한쪽이 0건이면 일치 열이 이미 말해 줌
            row["메모"] = f"MSDS 건수 다름 (GPT {counts['gpt']}, Claude {counts['claude']}): 앞에서부터 맞춤"
        rows.append(row)

    rows.sort(key=lambda r: (r["우선순위"], MATCH_ORDER[r["일치"]], SRC_ORDER[r["원문 대조"]],
                             0 if "오류" in r["검증기"] else 1, r["경로"]))
    return rows


def write_sheet(rows: list[dict], info: dict, path: Path) -> None:
    """엑셀로 저장한다: '검수' 시트(COLUMNS, 드롭다운) + '문서 정보' 시트."""
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_MAIN
    ws.append(COLUMNS)
    for r in rows:   # 텍스트층에서 섞여 온 제어 문자는 엑셀에 넣을 수 없어 지운다
        ws.append([ILLEGAL_CHARACTERS_RE.sub("", v) if isinstance(v, str) else v
                   for v in (r.get(c, "") for c in COLUMNS)])
        for c in ws[ws.max_row]:
            if c.data_type == "f":           # '='로 시작하는 글자가 엑셀 수식이 되지 않게
                c.data_type = "s"
    ws.freeze_panes = "D2"
    for name, w in WIDTHS.items():          # 기본 폭(13)이면 글이 잘려 검수가 어렵다
        ws.column_dimensions[get_column_letter(COLUMNS.index(name) + 1)].width = w
    ws.auto_filter.ref = ws.dimensions
    for c in ws[1][COLUMNS.index("검수 결과"):]:            # 검수 결과 ~ 메모: 사람이 쓰는 열
        c.fill = HUMAN_FILL
    col = get_column_letter(COLUMNS.index("검수 결과") + 1)
    dv = DataValidation(type="list", formula1='"' + ",".join(RESULT_OPTIONS) + '"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"{col}2:{col}{len(rows) + 500}")                 # 누락 추가 줄 여유

    wi = wb.create_sheet(SHEET_INFO)
    for k in INFO_FIELDS:
        wi.append([k, info.get(k, "")])
    extra = [k for k in info if k not in INFO_FIELDS]
    if extra:                                # 칸에 붙지 않은 검증기 결과 등
        wi.append([])
        for k in extra:
            wi.append([k, ILLEGAL_CHARACTERS_RE.sub("", str(info[k]))])
    for c in (c for row in wi.iter_rows() for c in row if c.data_type == "f"):
        c.data_type = "s"
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def make_review_sheet(doc_id: str) -> Path:
    """한 문서의 검수표: 두 실버·검수 정보·쪽 텍스트를 읽고 build_rows → write_sheet."""
    def read(p: Path, empty):
        if not p.exists():
            print(f"[경고] {p} 없음: 빈 결과로 둡니다")
            return empty
        return json.loads(p.read_text(encoding="utf-8"))

    docs = {m: read(paths.silver_path(m, doc_id), {"msds": []}) for m in MODELS}
    reviews = {m: read(paths.silver_review_path(m, doc_id), []) for m in MODELS}
    pages = load_pages(doc_id)["pages"]
    vals = {m: run_to21_validator(d) if d.get("msds") else [] for m, d in docs.items()}
    rows = build_rows(docs["gpt"], docs["claude"], reviews["gpt"], reviews["claude"],
                      {p["page"]: p["text"] for p in pages},
                      vals,
                      {p["page"]: p["state"] for p in pages})
    row = manifest.get(doc_id)
    info = {"문서 번호": doc_id, "원본 파일": row["source_file"], "쪽수": len(pages),
            "검수자": row.get("reviewer", ""), "교차 확인자": row.get("cross_checker", "")}
    for m, tag in MODELS.items():              # 문서 단위(doc.*)·근거(evidence) 칸 등 줄이 없는 검증기 결과
        index = prefix_index(docs[m], vals[m])
        attached = {id(v) for r in rows for v in lookup(index, r["경로"])}
        lost = [v for v in vals[m] if id(v) not in attached]
        if lost:
            info[f"검증기 ({tag}, 칸 없음)"] = " / ".join(
                f"{v.get('level')} {v.get('rule')} {v.get('field')} {v.get('message')}" for v in lost)
    out = paths.review_sheet_path(doc_id)
    write_sheet(rows, info, out)
    return out
