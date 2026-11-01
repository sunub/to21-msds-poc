"""작업 화면 탭 ③ 원문 대조 (역할 B, 개발 전용, ADR-025).

실행 하나·문서 하나의 쪽 글자 줄(그림 위 자리 포함), 결과 값(근거 줄 번호와 함께), 실버의 같은 자리 값을 한 번에 만든다.
쪽 글자·그림은 요청 때 pages_dir에서 읽고 파일로 남기지 않는다 (D-47). 평가용 문서는 읽지 않는다 (D-43).

근거 줄 번호: 결과 JSON의 evidence에는 줄 번호가 없고 쪽(page)과 원문 조각(source_text)만 있다(expand.py).
그래서 같은 쪽에서 글이 같은 줄을 찾아 되돌린다. 같은 글의 줄이 여럿이면(예: 독성 표의 '- | 자료없음') 그 값의 항 구간 안
줄만 남기고, 그 글을 근거로 쓴 행이 나온 순서대로 k번째 행에 k번째 줄을 준다(행은 대개 원문 순서로 나온다).
실행이 다른 쪽 글자 폴더로 돌았으면 글이 달라 줄을 못 찾을 수 있다(warnings에 적는다).
실버 값의 줄도 같은 방식으로 찾는다. 정답지에는 줄 번호가 없어 추정이므로 silver_lines.basis에 "text_match"를 밝힌다.
추정 줄은 silver_only[].lines에만 두고 line_index(줄 → 그 줄을 쓴 결과 값)에는 넣지 않는다.
실버 대응: 먼저 common.align의 키 경로(성분은 CAS, 독성은 성분·지표·종 …)로 행을 맞춘다. 번호가 어긋나도 같은 행끼리 견준다.
키 칸 하나만 달라도(예: 성분 MIX 대 CAS) 키 경로가 어긋나므로, 남은 행끼리는 같은 칸이 절반 이상(2칸 이상)인 행을 짝짓는다.
값의 채점 항목(items): 그 값이 TO21 채점기의 어느 항목 비교에 들어가는 칸인지다(ITEM_RULES). "이 값 때문에 깎였다"가
아니다. 채점은 행 단위로 견주므로(예: 독성 행은 성분·항목·지표·상태·값을 한 묶음으로) 같은 항목의 다른 칸이 틀려도 깎인다.
채점기 판이 바뀌면 test_B_b_app_doc의 섭동 시험(값 하나를 바꾸고 떨어진 항목과 items를 견줌)이 어긋남을 잡는다.
"""
import json
import re
import unicodedata
from collections import Counter, defaultdict, deque
from pathlib import Path

import yaml

import _common  # noqa: F401  src 경로 등록
import b_app_sets as bsets
from msds.common import manifest
from msds.common.align import item_path_map, keyed_flatten, to_keyed
from msds.common.jsonpath import flatten, get, is_cond, is_q, is_stmt, to_cell
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

# TO21 채점기 v0.6이 표 행을 나누는 코드: 필수 물성 9종, 급성 독성 3종, 국내 법 5종. 나머지 행은 기타·해외 항목이다.
_MUST_PC = {"APPEARANCE_STATE", "PH", "BOILING", "FLASH_POINT", "UEL", "LEL", "VAPOR_PRESSURE", "RELATIVE_DENSITY",
            "AUTOIGNITION"}
_ACUTE = {"TX_ORAL", "TX_DERMAL", "TX_INHAL"}
_DOM = {"OSH", "KREACH", "CCA", "DG", "WASTE"}


def _first_urgent(row: dict, field: str, i) -> bool:
    """회사마다 첫 긴급 연락처의 값만 견준다."""
    k = next((n for n, c in enumerate(row.get("contacts") or []) if c.get("type") == "긴급"), None)
    return field == f"contacts[{k}].value"


def _no_cas(row: dict, field: str, i) -> bool:
    """성분 짝 키는 CAS이고, CAS가 없을 때만 이름이다."""
    return not row.get("cas_no")


def _rows_where(key: str, codes: set, inside: bool):
    return lambda row, field, i: (row.get(key) in codes) == inside


# 채점 항목(criteria 순서) → 그 항목이 비교하는 칸 규칙 [(표, 칸 이름들, 행 조건)]. 표와 칸은 _place의 표와 칸에서
# 행 번호([n])를 뗀 이름이다. 행 조건은 (행, 칸, 행 번호)를 받는다. 행을 고르거나 짝짓는 칸(회사 구분, 물성 코드, 법령,
# 성분 CAS 등)도 그 항목에 넣는다. 성분 CAS는 다른 표 행의 comp_ref가 가리키는 키이기도 하지만, 그 표 항목에는
# 그 행의 comp_ref 칸만 넣는다(항이 다른 값을 고르지 않도록).
ITEM_RULES: dict[str, list[tuple]] = {
    "MSDS 건수(다중 MSDS 분리)": [],
    "관리정보(제출번호·작성일·개정일·개정횟수)": [
        ("meta", {"msds_no", "first_issue_date", "last_revision_date", "revision_no"}, None)],
    "제품명·회사명·긴급연락처": [("product", {"name"}, None),
                          ("companies", {"role", "name", "site", "contacts.type"}, None),
                          ("companies", {"contacts.value"}, _first_urgent)],
    "신호어": [("hazard", {"signal_word"}, None)],
    "그림문자": [("hazard.pictograms", {"code"}, None)],
    "H 코드": [("hazard.h_statements", {"code"}, None)],
    "P 코드": [("hazard.p_statements", {"code"}, None)],
    "유해성 분류(코드+구분)": [("hazard.classes", {"class_code", "category"}, None)],
    "구성성분(CAS 기준 매칭)": [("components", {"cas_no"}, None), ("components", {"name"}, _no_cas)],
    "구성성분 필드(성분명·KE)": [("components", {"cas_no", "name", "ke_no"}, None)],
    "함유량(부등호·값·단위 6요소)": [("components", {"cas_no", "content"}, None), ("components", {"name"}, _no_cas)],
    "8항 노출기준(성분·출처·종류·값)": [("exposure_limits", {"comp_ref", "standard", "limit_type", "q"}, None)],
    "9항 필수 물성(특성·값)": [("physchem", {"comp_ref", "prop_code", "text_value", "q"},
                           _rows_where("prop_code", _MUST_PC, True))],
    "11항 급성독성(경구·경피·흡입)": [("toxicity", {"comp_ref", "endpoint", "descriptor", "status", "q"},
                                _rows_where("endpoint", _ACUTE, True))],
    "15항 국내 규제(성분·항목·해당여부)": [("regulations", {"law", "comp_ref", "item_code", "applicable"},
                                   _rows_where("law", _DOM, True))],
    "15항 국내 규제 기준농도": [("regulations", {"law", "comp_ref", "item_code", "threshold"},
                         lambda row, field, i: row.get("law") in _DOM and bool(row.get("threshold")))],
    "14항 운송(UN번호·등급·용기등급)": [("transport", {"un_no", "hazard_class", "packing_group"},
                                lambda row, field, i: i == 0)],
    "9항 기타 물성": [("physchem", {"comp_ref", "prop_code", "text_value", "q"}, _rows_where("prop_code", _MUST_PC, False))],
    "11항 기타 독성": [("toxicity", {"comp_ref", "endpoint", "descriptor", "status", "q"},
                    _rows_where("endpoint", _ACUTE, False))],
    "11항 CMR(성분·유해성·기관·등급)": [("cmr", {"comp_ref", "hazard", "agency", "class", "status"}, None)],
    "12항 생태(성분·항목·지표·값)": [("ecotox", {"comp_ref", "endpoint", "descriptor", "status", "q"}, None)],
    "15항 해외·기타 규제": [("regulations", {"law", "comp_ref", "item_code", "applicable"}, _rows_where("law", _DOM, False))],
    "서술형 문장(항목별 문자 유사도 평균)": [("narratives", {"item_code", "statements"}, None)],
}


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


def value_items(path: str, m: dict) -> list[str]:
    """값 하나가 들어가는 채점 항목 이름(criteria 순서). path는 msds 건 안 경로(앞의 msds[n].은 떼고 본다),
    m은 그 값이 든 msds 건이다. 행 조건은 m에서 꺼낸 그 행으로 판단한다."""
    table, i, field = _place(re.sub(r"^msds\[\d+\]\.", "", path))
    row = get(m, table if i is None else f"{table}[{i}]")
    row = row if isinstance(row, dict) else {}
    name = re.sub(r"\[\d+\]", "", field)
    return [item for item, rules in ITEM_RULES.items()
            if any(t == table and any(name == f or name.startswith(f + ".") for f in fields)
                   and (cond is None or cond(row, field, i)) for t, fields, cond in rules)]


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
    주면 같은 글의 줄이 여럿일 때 그 값의 항 구간 안 줄로 좁힌다. key는 실버와 맞출 키 경로다.
    items는 그 값이 들어가는 채점 항목이다(value_items)."""
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
                    "lines": _lines_for(path, ev), "items": value_items(path, m)})
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


def field_counts(pred_json: dict, gold_json: dict) -> Counter:
    """칸 단위 문제 수. (채점 항목, 항, 종류) → 개수. 원문 대조 화면의 분류와 같다 (사용자 결정 10/31):
    결과 값의 정답 짝이 다르면 wrong, 짝이 없으면 made, 정답에만 있는 칸은 missing. 같은 칸은 세지 않는다.
    점수 프로그램은 같은 값을 행 단위로 missing 1 + made 1로 셀 수 있어 수가 다르다."""
    values, gold_values = flatten_values(pred_json), flatten_values(gold_json)
    match, _ = _match(values, gold_values)
    out = Counter()
    for v in values:
        g = match.get(v["path"])
        if g and _norm(g["value"]) == _norm(v["value"]):
            continue
        for item in v["items"]:
            out[(item, v["section"], "wrong" if g else "made")] += 1
    matched = {g["path"] for g in match.values()}
    for g in gold_values:
        if g["path"] not in matched:
            for item in g["items"]:
                out[(item, g["section"], "missing")] += 1
    return out


def run_field_counts(run: Path, gold_dir: Path, doc_ids) -> dict[str, Counter]:
    """실행의 문서마다 field_counts. 결과 파일이나 정답 파일이 없는 문서는 셀 수 없어 뺀다.
    쪽 글자와 그림은 읽지 않으므로 평가용 문서도 내용을 꺼내지 않고 수만 센다."""
    out = {}
    for doc_id in doc_ids:
        pred_path, gold_path = run / "outputs" / f"{doc_id}.json", Path(gold_dir) / f"{doc_id}.json"
        if pred_path.is_file() and gold_path.is_file():
            out[doc_id] = field_counts(json.loads(pred_path.read_text(encoding="utf-8")),
                                       json.loads(gold_path.read_text(encoding="utf-8")))
    return out


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
            "has_gold": False, "silver_lines": None, "warnings": []}


def doc_view(run: Path, doc_id: str, pages_dir: Path, gold_dir: Path) -> dict:
    if not allowed_doc(doc_id, pages_dir / doc_id):
        raise PermissionError(f"보여 줄 수 없는 문서: {doc_id}")
    doc = json.loads((run / "outputs" / f"{doc_id}.json").read_text(encoding="utf-8"))
    lines = page_lines(doc_id, pages_dir)
    spans = section_spans(doc_id, pages_dir)
    values = flatten_values(doc, lines, spans)
    gold_path = gold_dir / f"{doc_id}.json"
    gold = json.loads(gold_path.read_text(encoding="utf-8")) if gold_path.exists() else None
    gold_values = flatten_values(gold, lines, spans) if gold else []
    silver_lines = {"basis": "text_match", "found": sum(1 for g in gold_values if g["lines"]),
                    "total": len(gold_values)} if gold is not None else None
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
            "has_gold": gold is not None, "silver_lines": silver_lines, "warnings": warnings}
