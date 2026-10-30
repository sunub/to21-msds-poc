"""작업 화면 탭 ③ 원문 대조 (역할 B, 개발 전용, ADR-025).

실행 하나·문서 하나의 쪽 글자 줄(그림 위 자리 포함), 결과 값(근거 줄 번호와 함께), 실버의 같은 자리 값을 한 번에 만든다.
쪽 글자·그림은 요청 때 pages_dir에서 읽고 파일로 남기지 않는다 (D-47). 평가용 문서는 읽지 않는다 (D-43).

근거 줄 번호: 결과 JSON의 evidence에는 줄 번호가 없고 쪽(page)과 원문 조각(source_text)만 있다(expand.py).
그래서 같은 쪽에서 글이 같은 줄을 찾아 되돌린다. 같은 글의 줄이 여럿이면(예: 독성 표의 '- | 자료없음') 그 값의 항 구간 안
줄만 남기고, 그 글을 근거로 쓴 행이 나온 순서대로 k번째 행에 k번째 줄을 준다(행은 대개 원문 순서로 나온다).
실행이 다른 쪽 글자 폴더로 돌았으면 글이 달라 줄을 못 찾을 수 있다(warnings에 적는다).
실버 대응: 먼저 common.align의 키 경로(성분은 CAS, 독성은 성분·지표·종 …)로 행을 맞춘다. 번호가 어긋나도 같은 행끼리 견준다.
키 칸 하나만 달라도(예: 성분 MIX 대 CAS) 키 경로가 어긋나므로, 남은 행끼리는 같은 칸이 절반 이상(2칸 이상)인 행을 짝짓는다.
"""
import json
import re
import unicodedata
from collections import defaultdict, deque
from pathlib import Path

import yaml

import _common  # noqa: F401  src 경로 등록
import b_app_sets as bsets
from msds.common import manifest
from msds.common.align import item_path_map, keyed_flatten, to_keyed
from msds.common.jsonpath import flatten, is_cond, is_q, is_stmt, to_cell
from msds.extract.expand import _SOURCE_MAX
from msds.extract.inputs import load_document, read_page_lines

CELL_SEP = " | "
_PAGE_JSON = re.compile(r"^p(\d+)\.json$")
_SKIP_TOP = ("evidence", "validation")
_NARR_CODE = re.compile(r"^S(\d+)_")                       # 서술 항목 코드 S4_EYE → 4항 (명세서 5-3_서술항목)
_ROW = re.compile(r"^(\w+)\[(\d+)\]\.?(.*)$")               # toxicity[3].q
_SUB_ROW = re.compile(r"^(\w+)\.(\w+)\[(\d+)\]\.?(.*)$")    # hazard.classes[0].category
# TO21 최상위 키 → 그 값을 만드는 항. 서술형(narratives)은 item_code, extras는 행의 section_no로 정한다.
# 관리정보(meta)는 개정 정보가 16항 값을 우선하므로 16항으로 본다 (ADR-020).
SECTION_OF = {"product": 1, "companies": 1, "hazard": 2, "composition": 3, "components": 3, "exposure_limits": 8,
              "physchem": 9, "toxicity": 11, "cmr": 11, "ecotox": 12, "transport": 14, "regulations": 15,
              "dangerous_goods": 15, "waste": 15, "intl_class": 15, "meta": 16}


def _key(text: str) -> str:
    """칸 맞추기 키: NFKC 정규화 뒤 글자·숫자만."""
    return "".join(c for c in unicodedata.normalize("NFKC", text) if c.isalnum())


def _entries(doc_dir: Path) -> dict[int, dict[str, deque]]:
    """쪽 → {키: 그 키의 bbox들(쪽 파일 순서)}. pNNN.json이 없거나 entries가 없으면 빈 쪽."""
    out: dict[int, dict[str, deque]] = {}
    for p in doc_dir.glob("p*.json"):
        m = _PAGE_JSON.match(p.name)
        if not m:
            continue
        by_key: dict[str, deque] = defaultdict(deque)
        for e in json.loads(p.read_text(encoding="utf-8")).get("entries") or []:
            box, k = e.get("bbox"), _key(e.get("text") or "")
            if k and isinstance(box, list) and len(box) == 4:
                by_key[k].append(box)
        out[int(m.group(1))] = by_key
    return out


def page_lines(doc_id: str, pages_dir: Path) -> list[dict]:
    """쪽 글자 줄마다 그림 위 자리(bbox, 쪽 그림 픽셀 좌표)를 붙인다. 칸(' | ')마다 같은 쪽에서 키가 같고 아직 안 쓴
    entry 첫 번째를 찾아 그 사각형들을 합친다. 하나도 못 찾으면 None."""
    entries = _entries(pages_dir / doc_id)
    out = []
    for line in read_page_lines(doc_id, pages_dir):
        page = entries.get(line.page, {})
        boxes = []
        for cell in line.text.split(CELL_SEP):
            k = _key(cell)
            if k and page.get(k):
                boxes.append(page[k].popleft())
        bbox = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes),
                max(b[3] for b in boxes)] if boxes else None
        out.append({"id": line.id, "page": line.page, "no": line.no, "text": line.text, "bbox": bbox})
    return out


def section_spans(doc_id: str, pages_dir: Path) -> dict[int, dict]:
    """첫 MSDS 건의 항 구간 {항: {"start", "end"}}. 분할 파일이 없으면 제목으로 만든 임시 분할(inputs.load_document)."""
    part = load_document(doc_id, pages_dir).msds[0]
    return {no: {"start": s.start, "end": s.end} for no, s in part.sections.items() if s.method != "fallback"}


def _empty(v) -> bool:
    if isinstance(v, dict):
        return all(_empty(x) for x in v.values())
    return v is None or v == "" or v == []


def _text(v) -> str:
    """화면에 보일 짧은 글. 숫자 묶음은 원문 글자(raw), 문장은 '키: 값', 조건은 값이 있는 칸만."""
    if is_q(v):
        return to_cell(v.get("raw") if v.get("raw") is not None else v.get("value"))
    if is_stmt(v):
        body = v.get("value") if v.get("value") is not None else v.get("text")
        return f"{v['key']}: {body}" if v.get("key") else to_cell(body)
    if is_cond(v):
        return ", ".join(f"{k} {x}" for k, x in v.items() if x is not None)
    if isinstance(v, list):
        return ", ".join(to_cell(x) for x in v)
    return to_cell(v)


def _section(path: str, m: dict) -> int | None:
    """msds 항목 안 경로(toxicity[3].q, narratives[2] …)의 항 번호."""
    top = re.split(r"[.\[]", path, maxsplit=1)[0]
    if top in ("narratives", "extras"):
        row = _ROW.match(path)
        items = m.get(top) or []
        if not row or int(row.group(2)) >= len(items):
            return None
        if top == "extras":
            return items[int(row.group(2))].get("section_no")
        code = _NARR_CODE.match(items[int(row.group(2))].get("item_code") or "")
        return int(code.group(1)) if code else None
    return SECTION_OF.get(top)


def _place(path: str) -> tuple[str, int | None, str]:
    """(표, 행, 칸). 최상위 목록은 그 키가 표다. 객체 안 목록(hazard.classes)은 '객체.목록'이 표다."""
    m = _ROW.match(path)
    if m:
        return m.group(1), int(m.group(2)), m.group(3)
    m = _SUB_ROW.match(path)
    if m:
        return f"{m.group(1)}.{m.group(2)}", int(m.group(3)), m.group(4)
    top, _, rest = path.partition(".")
    return top, None, rest


def _row_root(field: str) -> str:
    """근거 경로가 가리키는 행: toxicity[0].statements[0] → toxicity[0], hazard.classes[1] → 그대로, meta.x → 그대로."""
    m = _ROW.match(field)
    if m:
        return f"{m.group(1)}[{m.group(2)}]"
    m = _SUB_ROW.match(field)
    return f"{m.group(1)}.{m.group(2)}[{m.group(3)}]" if m else field


def _evidence_lines(m: dict, lines: list[dict], spans: dict) -> dict[str, list[str]]:
    """evidence.field → 줄 번호들. 같은 쪽에서 글이 원문 조각의 첫 줄과 같은 줄을 찾는다."""
    if not lines:
        return {}
    pos = {l["id"]: i for i, l in enumerate(lines)}
    by_page: dict[int, list[dict]] = defaultdict(list)
    for l in lines:
        by_page[l["page"]].append(l)
    out: dict[str, list[str]] = defaultdict(list)
    users: dict[tuple, list[str]] = defaultdict(list)    # (쪽, 글, 항) → 그 글을 근거로 쓴 행(나온 순서)
    for e in m.get("evidence") or []:
        field = e.get("field") or ""
        first = (e.get("source_text") or "").split("\n")[0]
        found = [l["id"] for l in by_page.get(e.get("page"), []) if first and l["text"][:_SOURCE_MAX] == first]
        if not found:
            continue
        no = _section(field, m)
        span = spans.get(no)
        if len(found) > 1 and span and span["start"] in pos and span["end"] in pos:
            a, b = pos[span["start"]], pos[span["end"]]
            found = [lid for lid in found if a <= pos[lid] <= b] or found
        rows = users[(e.get("page"), first, no)]
        if _row_root(field) not in rows:
            rows.append(_row_root(field))
        lid = found[min(rows.index(_row_root(field)), len(found) - 1)]
        if lid not in out[field]:
            out[field].append(lid)
    return out


def _lines_for(path: str, ev: dict[str, list[str]]) -> list[str]:
    """값 경로와 같거나 가장 길게 앞부분이 맞는 evidence의 줄 (값 → 행 순으로 찾는다)."""
    best = max((f for f in ev if path == f or path.startswith(f + ".") or path.startswith(f + "[")),
               key=len, default=None)
    return list(ev[best]) if best else []


def flatten_values(doc_json: dict, lines: list[dict] | None = None, spans: dict | None = None) -> list[dict]:
    """TO21 JSON 첫 건을 값(칸) 단위로 펼친다. 칸은 common.jsonpath 정의(숫자 묶음·문장·조건·글자 목록은 한 칸)다.
    빈 칸·순번(seq)·evidence·validation은 뺀다. lines(page_lines)를 주면 근거 줄 번호를 붙이고, spans(section_spans)를
    주면 같은 글의 줄이 여럿일 때 그 값의 항 구간 안 줄로 좁힌다. key는 실버와 맞출 키 경로다."""
    items = doc_json.get("msds") or []
    if not items:
        return []
    m = items[0]
    ev = _evidence_lines(m, lines or [], spans or {})
    keyed = item_path_map(m)
    out = []
    for path, value in flatten(m):
        if path.startswith(_SKIP_TOP) or _empty(value):
            continue
        table, row, field = _place(path)
        if field == "seq" or field.endswith(".seq"):
            continue
        out.append({"path": f"msds[0].{path}", "key": to_keyed(path, keyed), "section": _section(path, m),
                    "table": table, "row": row, "field": field, "value": value, "text": _text(value),
                    "lines": _lines_for(path, ev)})
    return out


def _norm(v):
    """견주기: 글자는 공백 차이를 무시하고(A 검수표와 같은 기준, D-9), 빈 글자·빈 목록은 null과 같게 본다."""
    if isinstance(v, str):
        return re.sub(r"\s+", "", v) or None
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_norm(x) for x in v] or None
    return v


def _rows(values: list[dict]) -> dict[tuple, dict]:
    rows: dict[tuple, dict] = defaultdict(dict)
    for v in values:
        if v["row"] is not None:
            rows[(v["table"], v["row"])][v["field"]] = _norm(v["value"])
    return rows


def _match(pred_values: list[dict], gold_values: list[dict]) -> tuple[dict[str, dict], dict[tuple, int]]:
    """결과 값 path → 실버 값(flatten_values 항목), (표, 결과 행) → 실버 행.
    1) 키 경로가 같은 칸. 그 칸이 든 행끼리 짝이 된다. 2) 짝이 없는 행끼리 같은 표에서 같은 칸이 많은 순으로
    짝짓는다(같은 칸이 2칸 이상이고 결과 행 칸의 절반 이상). 짝 행의 같은 칸 이름을 실버 값으로 쓴다."""
    by_key = {g["key"]: g for g in gold_values}
    by_cell = {(g["table"], g["row"], g["field"]): g for g in gold_values}
    match, pairs = {}, {}
    for v in pred_values:
        g = by_key.get(v["key"])
        if g:
            match[v["path"]] = g
            if v["row"] is not None:
                pairs.setdefault((v["table"], v["row"]), g["row"])
    used = {(t, j) for (t, _), j in pairs.items()}
    pred_rows, gold_rows = _rows(pred_values), _rows(gold_values)
    cands = []
    for (t, i), pf in pred_rows.items():
        if (t, i) in pairs:
            continue
        for (t2, j), gf in gold_rows.items():
            if t2 == t and (t, j) not in used:
                score = sum(1 for f, x in pf.items() if x is not None and gf.get(f) == x)
                if score >= 2 and score * 2 >= len(pf):
                    cands.append((-score, i, j, t))
    for _, i, j, t in sorted(cands):
        if (t, i) not in pairs and (t, j) not in used:
            pairs[(t, i)] = j
            used.add((t, j))
    for v in pred_values:
        if v["path"] not in match and (v["table"], v["row"]) in pairs:
            g = by_cell.get((v["table"], pairs[(v["table"], v["row"])], v["field"]))
            if g:
                match[v["path"]] = g
    return match, pairs


def _silver(v: dict, g: dict | None) -> dict:
    return {"value": g["value"], "same": _norm(g["value"]) == _norm(v["value"])} if g else {"value": None, "same": False}


def align_silver(pred_values: list[dict], gold_json: dict) -> dict[str, dict]:
    """결과 값의 path마다 실버의 같은 자리 값 {"value", "same"}. 실버에 없으면 {"value": None, "same": False}."""
    match, _ = _match(pred_values, flatten_values(gold_json))
    return {v["path"]: _silver(v, match.get(v["path"])) for v in pred_values}


def allowed_doc(doc_id: str, doc_dir: Path | None = None) -> bool:
    """평가용과 용도를 확인할 수 없는 문서는 보여 주지 않는다 (D-43). manifest 밖 문서(신규 RAW-xx)는 doc_dir의
    meta.json에 같은 doc_id가 있을 때만 연다. 기준은 문서 묶음 목록(b_app_sets.doc_lock)과 같다."""
    return bsets.doc_lock(doc_id, doc_dir, manifest.load()) is None


def pages_view(doc_id: str, pages_dir: Path) -> dict:
    """실행 없이 쪽 글자만. doc_view와 같은 키에 결과·실버 값은 비운다. pNNN.json이 없는 판은 칸 좌표 없이 글자만 준다."""
    if not allowed_doc(doc_id, pages_dir / doc_id):
        raise PermissionError(f"보여 줄 수 없는 문서: {doc_id}")
    lines = page_lines(doc_id, pages_dir)
    return {"doc_id": doc_id, "pages": sorted({l["page"] for l in lines}), "lines": lines,
            "sections": section_spans(doc_id, pages_dir), "values": [], "silver_only": [], "line_index": {},
            "has_gold": False, "warnings": []}


def doc_view(run: Path, doc_id: str, pages_dir: Path, gold_dir: Path) -> dict:
    if not allowed_doc(doc_id, pages_dir / doc_id):
        raise PermissionError(f"보여 줄 수 없는 문서: {doc_id}")
    doc = json.loads((run / "outputs" / f"{doc_id}.json").read_text(encoding="utf-8"))
    lines = page_lines(doc_id, pages_dir)
    spans = section_spans(doc_id, pages_dir)
    values = flatten_values(doc, lines, spans)
    gold_path = gold_dir / f"{doc_id}.json"
    gold = json.loads(gold_path.read_text(encoding="utf-8")) if gold_path.exists() else None
    gold_values = flatten_values(gold) if gold else []
    match, pairs = _match(values, gold_values)
    for v in values:
        g = match.get(v["path"])
        v["silver"] = {**_silver(v, g), "text": g["text"] if g else None}
    # 실버에만 있는 칸. pair_row는 짝 행이 결과에 있으면 그 결과 행 번호(그 행이 칸 하나를 빠뜨렸다)
    matched = {g["path"] for g in match.values()}
    back = {(t, j): i for (t, i), j in pairs.items()}
    silver_only = [{**g, "pair_row": back.get((g["table"], g["row"]))} for g in gold_values if g["path"] not in matched]
    line_index: dict[str, list[str]] = {}
    for v in values:
        for lid in v["lines"]:
            line_index.setdefault(lid, []).append(v["path"])

    warnings = []
    info_path = run / "run_info.yaml"
    used = (yaml.safe_load(info_path.read_text(encoding="utf-8")) or {}).get("pages_dir") if info_path.exists() else None
    if used and Path(str(used)).name != pages_dir.name:
        warnings.append(f"이 실행은 쪽 글자 {used}로 돌았습니다. 지금 보이는 쪽 글자({pages_dir.name})와 줄 번호가 다를 수 있습니다.")
    count = len(doc.get("msds") or [])
    if count > 1:
        warnings.append(f"이 문서에는 MSDS가 {count}건 있습니다. 첫 건만 보입니다.")
    return {"doc_id": doc_id, "pages": sorted({l["page"] for l in lines}), "lines": lines,
            "sections": spans, "values": values, "silver_only": silver_only, "line_index": line_index,
            "has_gold": gold is not None, "warnings": warnings}
