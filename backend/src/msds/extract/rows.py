"""표 항목의 행 형식 출력: 안내와 파서 (B, ADR-019).

표 항목(3·8·9·11·12·14·15항)은 JSON 대신 '한 줄 한 행' 글로 받는다. 칸 이름이 행마다 반복되지 않아 출력이
짧고, 문법 강제가 없어 공백 폭주가 없다. 모델은 표마다 `### 표 이름` 아래에 ` | `로 나눈 고정 열을 쓰고,
parse_rows가 지금의 중간 형식 dict(section_specs.response_schema)로 바꾼다. 펼치기는 그대로 쓴다.
- 열은 response_schema(no)의 행 칸 순서 그대로다. 스키마의 칸과 필수 칸은 바꾸지 않는다.
- 객체 칸(3항 composition)은 한 행짜리 표다. 줄(line) 열 하나를 값이 있는 칸마다 lines에 쓴다.
- 숫자 묶음(QM)은 열 하나다. 모델은 원문 표기대로 쓰고 parse_qm이 R04·R06·R08대로 나눈다.
- 목록 칸은 '; '로 나누고, 서술 문장(statements)은 그 행의 줄을 근거로 단다. 조건(cond)은 '칸=값; 칸=값'이다.
- 행마다 그 행의 스키마로 검증한다. 틀린 줄은 버리고 줄 단위 오류로 돌려준다. 실행기가 재추출 피드백에 넣는다.
- 열 수가 하나 어긋난 행은 빈 칸 하나가 빠졌거나 더 들어간 것으로 보고, 값 칸의 열이 하나로 정해질 때만 살린다 (ADR-021).
- 선택지(enum) 열은 표마다 열 이름 줄 아래에 스키마의 값 목록을 적는다. 파서는 공백을 지운 값과
  '해당없음' → '비해당'만 맞추고, 그 밖의 값은 검증 오류로 버린다 (rows-tune, ADR-020).
예시 행은 직접 만든 가짜 값이다 (D-43).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from msds.common.schema import validate
from msds.extract.section_specs import response_schema

ROWS_SECTIONS_DEFAULT = (3, 8, 9, 11, 12, 14, 15)   # 표 항목. models.yaml 태그의 rows_sections로 켠다

_LINE_COLS = ("line", "start", "end")
_LINE_ID = re.compile(r"p\d+:L\d+")
_HEADER = re.compile(r"^#+\s*(\S*)")
_SCALARS = ("string", "number", "integer", "boolean")
_EXCERPT = 40         # 오류에 적는 줄 앞부분 글자 수
_CHOICES_MAX = 12     # 선택지가 이보다 많고 칸 설명이 코드표를 가리키면 목록 대신 [코드표]를 가리킨다
_CODE_TABLE_REF = re.compile(r"\bC\d\b")             # 칸 설명의 코드표 표시. 예: '[필수] 특성 코드 — C4'
_CHOICE_LINE = re.compile(r"^- `[^`]+`: [^|]*$")     # 안내문의 선택지 줄. 모델이 따라 써도 행으로 읽지 않는다
_NO_VALUE = ("자료없음", "해당없음", "미기재")       # 값 없는 행의 상태 (expand._NO_VALUE와 같다)


# ── 숫자 묶음 ──────────────────────────────────────────

_NUM = r"[-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?"
_QM = re.compile(rf"^(?P<op>>=|=>|≥|<=|=<|≤|>|<)?\s*(?P<a>{_NUM})"
                 rf"(?:\s*[~～∼\-–]\s*(?P<bop><=|=<|≤|<)?\s*(?P<b>{_NUM}))?\s*(?P<rest>.*)$")
_APPROX = re.compile(r"^(?:약|approx\.?|ca\.|≈)\s*", re.I)
_WORD_OP = re.compile(r"이상|초과|이하|미만")
_OPS = {">=": ">=", "=>": ">=", "≥": ">=", "이상": ">=", ">": ">", "초과": ">",
        "<=": "<=", "=<": "<=", "≤": "<=", "이하": "<=", "<": "<", "미만": "<"}
_DEGREE = re.compile(r"[°˚]\s*([CFK])")
_UNIT_SYMBOLS = (("℃", "C"), ("℉", "F"), ("㎎", "mg"), ("㎏", "kg"), ("㎍", "ug"), ("㎛", "um"), ("㎖", "mL"),
                 ("ℓ", "L"), ("㎥", "m3"), ("㎤", "cm3"), ("㎡", "m2"), ("㎝", "cm"), ("㎜", "mm"), ("㎪", "kPa"),
                 ("㎩", "Pa"), ("μ", "u"), ("µ", "u"), ("³", "3"), ("²", "2"))   # R08


def _number(token: str) -> int | float:
    """'1,000' → 1000, '99.96' → 99.96, '1.2E-3' → 0.0012 (R06)."""
    t = token.replace(",", "")
    return int(t) if re.fullmatch(r"[-+]?\d+", t) else float(t)


def _unit(rest: str) -> str | None:
    """숫자 뒤 글에서 단위. 괄호부터는 조건이라 뺀다. 기호는 R08대로 바꾼다."""
    unit = _DEGREE.sub(r"\1", rest.split("(")[0].strip())
    for a, b in _UNIT_SYMBOLS:
        unit = unit.replace(a, b)
    return unit or None


def parse_qm(text: str) -> dict | None:
    """숫자 묶음 한 칸을 QM dict로. 모양: [부호]숫자[~숫자][ 단위] 또는 상태어. 값이 있는 칸만 담는다.
    부등호 글자(이상·초과·이하·미만·≥·≤)는 R04대로, '~' 범위의 양 끝은 포함(>=, <=)으로 본다.
    범위 둘째 숫자 앞에 '<'·'<='·'≤'가 붙으면('40-<50 %') 위 끝은 그 부등호다.
    숫자로 시작하지 않으면(해당없음 등) raw만 둔다. status는 fill_q가 정한다."""
    raw = (text or "").strip()
    if not raw:
        return None
    body, approx = raw, False
    if m := _APPROX.match(body):
        body, approx = body[m.end():], True
    if body.endswith("정도"):
        body, approx = body[:-2].rstrip(), True
    m = _QM.match(body)
    if not m:
        return {"raw": raw}
    q: dict = {"raw": raw}
    op, rest = _OPS.get(m["op"] or ""), m["rest"]
    if w := _WORD_OP.search(rest):
        op = op or _OPS[w.group(0)]
        rest = rest[:w.start()] + rest[w.end():]
    a = _number(m["a"])
    if m["b"]:     # 둘째 숫자 앞의 부등호('40-<50 %')가 위 끝을 정한다 (ADR-029)
        q.update(lower_op=">=", lower=a, upper_op=_OPS.get(m["bop"] or "", "<="), upper=_number(m["b"]))
    elif op in (">", ">="):
        q.update(lower_op=op, lower=a)
    elif op in ("<", "<="):
        q.update(upper_op=op, upper=a)
    else:
        q["value"] = a
    if approx:
        q["approx"] = True
    if unit := _unit(rest):
        q["unit"] = unit
    return q


# ── 표 ─────────────────────────────────────────────────

@dataclass(frozen=True)
class _Table:
    name: str
    columns: tuple[str, ...]
    kinds: dict[str, str]     # 열 → 글 한 칸을 읽는 방식 (_kind)
    schema: dict              # 한 행(객체 칸이면 그 객체)의 검증 스키마. $defs 포함
    is_object: bool


def _branch(node: dict) -> dict:
    """null 허용(anyOf)을 벗긴 안쪽 스키마."""
    return next(b for b in node["anyOf"] if b.get("type") != "null") if "anyOf" in node else node


def _resolve(node: dict, defs: dict) -> dict:
    b = _branch(node)
    return defs[b["$ref"].rsplit("/", 1)[1]] if "$ref" in b else b


def _choices(node: dict, defs: dict) -> list[str] | None:
    """선택지(enum) 칸이면 그 값 목록."""
    return _resolve(node, defs).get("enum")


def _kind(node: dict, defs: dict, path: str) -> str:
    """칸 하나를 글 한 칸으로 쓰는 방식: qm, pairs(칸=값 목록), stmts, list, 또는 스칼라 형 이름."""
    if _branch(node).get("$ref") == "#/$defs/QM":
        return "qm"
    b = _resolve(node, defs)
    t = b.get("type")
    if t == "object" and all(_branch(v).get("type") in _SCALARS for v in b.get("properties", {}).values()):
        return "pairs"
    if t == "array":
        items = b["items"]
        if items.get("$ref") == "#/$defs/STMT":
            return "stmts"
        if items.get("type") == "string":
            return "list"
    if t in _SCALARS:
        return t
    raise ValueError(f"행 형식으로 쓸 수 없는 칸: {path}")


def _tables(no: int) -> list[_Table]:
    schema = response_schema(no)
    defs = schema.get("$defs", {})
    out = []
    for name, node in schema["properties"].items():
        is_object = node.get("type") == "object"
        row = node if is_object else node["items"]
        cols = [k for k in row["properties"] if k != "lines"] + (["line"] if is_object else [])
        kinds = {c: "line" if c in _LINE_COLS else _kind(row["properties"][c], defs, f"{name}.{c}") for c in cols}
        out.append(_Table(name, tuple(cols), kinds, {"$defs": defs, **row}, is_object))
    return out


def row_tables(no: int) -> dict[str, list[str]]:
    """no항 응답 스키마의 표마다 열 이름 순서. 예: {"toxicity": ["comp_name", "comp_cas", "endpoint", ..., "status", "line"]}.
    열은 response_schema(no)의 행 properties 순서 그대로다. 숫자 묶음 칸(q 등)은 열 하나다.
    객체 칸(composition)은 lines 대신 line 열 하나를 끝에 둔 한 행짜리 표다.
    행 목록이 객체 안에 있는 항(1·2항)은 ValueError."""
    return {t.name: list(t.columns) for t in _tables(no)}


# ── 안내문 ─────────────────────────────────────────────

_GUIDE = """JSON을 쓰지 않는다. 아래 표마다 `### 표 이름` 줄을 쓰고, 그 아래에 열 이름 줄을 그대로 한 번 쓴 뒤 한 줄에 한 행씩 쓴다.
- 칸은 ` | `로 나눈다. 열의 순서와 수는 열 이름 줄과 같다. 값이 없는 칸은 비워 두되 ` | `는 남긴다.
- 값 안에 `|`가 있으면 `/`로 바꿔 쓴다.
- 줄 열(`line`, 서술 항목은 `start`·`end`)에는 입력 줄 앞의 줄 번호를 보이는 그대로 쓴다. 예: `p2:L23`
- 원문에 값 없이 `자료없음`·`해당없음`·`미기재`로 적힌 행도 빠뜨리지 말고 쓴다. 그 글자는 숫자 묶음 열이 있으면 거기에 쓰고, 상태 열(`status`)이 있으면 상태 열에도 원문의 것을 쓴다. 그 글자가 선택지에 있는 열이 아니면 다른 열(출처·비고 등)에는 쓰지 않는다.
- 숫자 묶음 열({qm})에는 부등호·숫자·단위를 한 칸에 원문 표기대로 쓴다. 나누기는 코드가 한다. 단위를 다른 열로 옮기지 않는다. 단위가 표 머리글에만 있으면 값 뒤에 붙인다. 예: `20 ~ 30 %`, `> 2000 mg/kg`, `약 1.2 g/cm3`, `-210 ℃`
- 선택지 열에는 목록의 값만 쓴다. 목록은 표마다 열 이름 줄 아래에 열마다 한 줄씩 있다(응답에는 쓰지 않는다). `[코드표]의 코드만`인 열은 [코드표]에 있는 코드만 쓴다. 맞는 값이 없으면 비워 둔다.
- 쓸 행이 없는 표는 `### 표 이름` 줄만 쓴다.
- 아래 예시 행의 값은 형식만 보이는 가짜다. 원문에 있는 값만 쓴다."""

# 표마다 예시 행 두 줄 (가짜 값, D-43). 쓰지 않은 열은 빈 칸이다. narratives의 item_code는 그 항의 코드로 채운다.
_EXAMPLES: dict[str, list[dict]] = {
    "composition": [{"type": "혼합물", "no_hazardous_component": "false", "line": "p2:L3"}],
    "components": [
        {"name": "가상물질 갑", "cas_no": "1234-56-6", "ke_no": "KE-12345", "content": "10 ~ 20 %", "line": "p2:L5"},
        {"name": "영업비밀 성분", "synonyms": "가상명 A; 가상명 B", "content": "1 ~ 5 %", "trade_secret": "true",
         "line": "p2:L6"}],
    "exposure_limits": [
        {"comp_name": "가상물질 갑", "comp_cas": "1234-56-6", "standard": "국내", "limit_type": "TWA", "q": "1 ppm",
         "kr_basis": "노출기준", "line": "p4:L3"},
        {"comp_name": "가상물질 갑", "comp_cas": "1234-56-6", "standard": "ACGIH", "limit_type": "STEL",
         "q": "자료없음", "line": "p4:L4"}],
    "physchem": [
        {"prop_code": "VAPOR_PRESSURE", "q": "2.3 kPa", "cond": "temp=20; temp_unit=C", "line": "p5:L4"},
        {"prop_code": "APPEARANCE_COLOR", "text_value": "무색", "line": "p5:L2"}],
    "toxicity": [
        {"comp_name": "가상물질 갑", "comp_cas": "1234-56-6", "endpoint": "TX_INHAL", "descriptor": "LC50",
         "q": "> 5 mg/L", "species": "랫드", "duration_value": "4", "duration_unit": "hr", "physical_form": "증기",
         "status": "값있음", "line": "p6:L3"},
        {"comp_name": "가상물질 갑", "comp_cas": "1234-56-6", "endpoint": "TX_SKIN", "q": "자료없음",
         "status": "자료없음", "line": "p6:L4"}],
    "cmr": [
        {"comp_name": "가상물질 갑", "comp_cas": "1234-56-6", "hazard": "발암성", "agency": "IARC",
         "class": "Group 3", "status": "값있음", "line": "p6:L10"},
        {"comp_name": "가상물질 갑", "comp_cas": "1234-56-6", "hazard": "발암성", "agency": "KR_OSH",
         "status": "해당없음", "line": "p6:L11"}],
    "ecotox": [
        {"comp_name": "가상물질 갑", "comp_cas": "1234-56-6", "endpoint": "ECO_FISH", "descriptor": "LC50",
         "q": "100 mg/L", "species": "가상 어류", "duration_value": "96", "duration_unit": "hr", "status": "값있음",
         "line": "p7:L3"},
        {"comp_name": "가상물질 갑", "comp_cas": "1234-56-6", "endpoint": "ECO_BIOACC", "descriptor": "BCF",
         "q": "자료없음", "status": "자료없음", "line": "p7:L8"}],
    "regulations": [
        {"law": "OSH", "item_code": "OSH_MEASURE", "item_raw": "작업환경측정대상물질", "comp_name": "가상물질 갑",
         "comp_cas": "1234-56-6", "applicable": "해당", "line": "p9:L3"},
        {"law": "KREACH", "item_code": "KREACH_EXIST", "item_raw": "기존화학물질", "comp_name": "가상물질 갑",
         "comp_cas": "1234-56-6", "applicable": "비해당", "line": "p9:L5"}],
    "dangerous_goods": [
        {"class": "제4류", "item": "제2석유류", "water_soluble": "비수용성", "grade": "III",
         "designated_qty": "1,000 L", "line": "p9:L8"},
        {"comp_name": "가상물질 을", "comp_cas": "2345-67-7", "class": "해당없음", "line": "p9:L9"}],
    "waste": [
        {"designated": "해당", "waste_type": "폐유기용제", "line": "p9:L11"},
        {"comp_name": "가상물질 을", "comp_cas": "2345-67-7", "designated": "자료없음", "line": "p9:L12"}],
    "intl_class": [
        {"comp_name": "가상물질 갑", "comp_cas": "1234-56-6", "system": "EU_CLP", "class_raw": "Flam. Liq. 3",
         "h_code": "H226", "status": "값있음", "line": "p9:L15"},
        {"comp_name": "가상물질 갑", "comp_cas": "1234-56-6", "system": "JP", "status": "자료없음", "line": "p9:L16"}],
    "transport": [
        {"mode": "해상", "regulated": "true", "un_no": "9999", "shipping_name": "가상 액체", "hazard_class": "8",
         "packing_group": "II", "marine_pollutant": "비해당", "ems_fire": "F-A", "ems_spill": "S-B",
         "line": "p10:L3"},
        {"mode": "공통", "regulated": "false", "packing_group": "해당없음", "marine_pollutant": "자료없음",
         "line": "p10:L6"}],
    "narratives": [
        {"title_raw": "가. 가상 제목", "start": "p3:L10", "end": "p3:L14"},
        {"title_raw": "나. 가상 제목", "start": "p3:L15", "end": "p3:L18"}],
    "extras": [
        {"title_raw": "가상 추가 항목", "reason": "필드없음", "q": "12 ㎛", "statements": "가상 설명", "line": "p5:L9"},
        {"title_raw": "가상 비고", "reason": "판단불가", "statements": "가상 문장 하나; 가상 문장 둘",
         "line": "p5:L10"}],
}


def _examples(t: _Table) -> list[dict]:
    rows = _EXAMPLES[t.name]
    if t.name == "narratives":
        rows = [{**r, "item_code": c} for r, c in zip(rows, t.schema["properties"]["item_code"]["enum"])]
    return rows


def _choice_lines(t: _Table) -> list[str]:
    """열 이름 줄 아래에 붙일 선택지 줄: 선택지 열마다 '- `열`: 값1 / 값2'. 값은 스키마에서 읽는다.
    선택지가 _CHOICES_MAX개를 넘고 칸 설명이 코드표를 가리키면 목록 대신 '[코드표]의 코드만'이다."""
    out = []
    for c in t.columns:
        node = t.schema["properties"].get(c, {})
        if values := _choices(node, t.schema["$defs"]):
            to_table = len(values) > _CHOICES_MAX and _CODE_TABLE_REF.search(node.get("description", ""))
            out.append(f"- `{c}`: " + ("[코드표]의 코드만" if to_table else " / ".join(values)))
    return out


def rows_guide(no: int) -> str:
    """안내문 끝에 붙일 [응답 형식]: 쓰는 규칙과, 표마다 '### 표 이름' 줄 + 열 이름 줄 + 선택지 줄 + 예시 행(가짜 값)."""
    tables = _tables(no)

    def cols(*kinds: str) -> str:
        return ", ".join(dict.fromkeys(f"`{c}`" for t in tables for c in t.columns if t.kinds[c] in kinds))

    def no_hae_dang_eopseum(t: _Table, c: str) -> bool:
        values = _choices(t.schema["properties"].get(c, {}), t.schema["$defs"]) or []
        return "비해당" in values and "해당없음" not in values

    out = [_GUIDE.format(qm=cols("qm"))]
    if multi := cols("list", "stmts"):
        out.append(f"- 값 여러 개를 담는 열({multi})은 값마다 `; `로 나눈다.")
    if flags := cols("boolean"):
        out.append(f"- 참/거짓 열({flags})에는 `true` 또는 `false`를 쓴다.")
    if nonap := ", ".join(dict.fromkeys(f"`{c}`" for t in tables for c in t.columns if no_hae_dang_eopseum(t, c))):
        out.append(f"- 원문이 `해당 없음`·`해당없음`이어도 선택지에 `비해당`만 있는 열({nonap})에는 `비해당`을 쓴다.")
    for t in tables:
        for c in t.columns:
            if t.kinds[c] == "pairs":
                fields = _resolve(t.schema["properties"][c], t.schema["$defs"])["properties"]
                out.append(f"- `{c}` 열에는 `칸=값`을 `; `로 이어 쓴다. 칸: {', '.join(fields)}. "
                           "측정 조건(온도·압력 등)만 쓰고, 값의 단위는 숫자 묶음 열에 값과 함께 쓴다.")
    if any(t.name == "narratives" for t in tables):
        out.append("- 서술 항목 코드(`narratives`의 `item_code`)에 속하는 소제목과 그 아래 문장은 `extras`에 쓰지 않는다. "
                   "그 항목의 `start`~`end`에 들어간다. `extras`에는 어느 표·열·코드에도 맞지 않는 제목이 붙은 값만 쓴다.")
    for t in tables:
        out += ["", f"### {t.name}", " | ".join(t.columns), *_choice_lines(t),
                *(" | ".join(r.get(c, "") for c in t.columns) for r in _examples(t))]
    return "\n".join(out)


# ── 파서 ───────────────────────────────────────────────

def _cells(s: str) -> list[str]:
    if s.startswith("|") and s.endswith("|"):    # 마크다운 표처럼 앞뒤에 |를 붙인 줄. 마지막 열은 줄 번호라 비지 않는다
        s = s[1:-1]
    return [c.strip() for c in s.split("|")]


def _where(table: str, s: str) -> str:
    """오류 앞머리: 표 이름, 그 줄의 줄 번호, 줄 앞부분."""
    excerpt = s if len(s) <= _EXCERPT else s[:_EXCERPT] + "…"
    return " ".join([table, *_LINE_ID.findall(s)[-1:], excerpt])


def _choice(text: str, values: list[str]) -> str:
    """선택지 열 값: 공백을 지운 값이 선택지에 있으면 그 값. '해당없음'은 선택지에 없고 '비해당'이 있으면 '비해당'.
    그 밖은 그대로 돌려줘 행 검증이 잡는다. 예: '해당 없음' → 14항 용기등급 '해당없음', 15항 해당 여부 '비해당'"""
    compact = {re.sub(r"\s+", "", v): v for v in values}
    key = re.sub(r"\s+", "", text)
    if key == "해당없음" and key not in compact and "비해당" in compact:
        return compact["비해당"]
    return compact.get(key, text)


def _value(text: str, kind: str, node: dict, defs: dict, line: str | None):
    """글 한 칸을 칸의 형으로. 빈 칸은 None(목록 칸은 []). 형에 안 맞으면 ValueError."""
    if kind in ("list", "stmts"):
        items = [x.strip() for x in text.split(";") if x.strip()]
        return [{"value": x, "line": line} for x in items] if kind == "stmts" else items
    if not text:
        return None
    if kind == "qm":
        return parse_qm(text)
    if kind == "pairs":
        fields = _resolve(node, defs)["properties"]
        out = {}
        for part in filter(None, (p.strip() for p in text.split(";"))):
            key, sep, val = (x.strip() for x in part.partition("="))
            if not sep or key not in fields:
                raise ValueError(f"'칸=값'이 아니거나 모르는 칸 '{part}' (칸: {', '.join(fields)})")
            out[key] = _value(val, _kind(fields[key], defs, key), fields[key], defs, line)
        return out or None
    if kind in ("number", "integer"):
        if not re.fullmatch(_NUM, text) or (kind == "integer" and not isinstance(_number(text), int)):
            raise ValueError(f"{'정수' if kind == 'integer' else '숫자'}가 아님 '{text}'")
        return _number(text)
    if kind == "boolean":
        if text.lower() not in ("true", "false"):
            raise ValueError(f"true 또는 false가 아님 '{text}'")
        return text.lower() == "true"
    if values := _choices(node, defs):
        return _choice(text, values)
    return text


def _build(t: _Table, cells: list[str]) -> tuple[dict | None, str | None]:
    """열 수가 맞는 칸 목록 → (행 dict, None) 또는 (None, 문제)."""
    values = dict(zip(t.columns, cells))
    for c in t.columns:
        if t.kinds[c] == "line":
            ids = _LINE_ID.findall(values[c])               # 줄 번호가 여럿이거나 글이 섞여도 첫 번째를 쓴다
            if not ids:
                return None, f"{c} 열이 줄 번호(p2:L23 모양)가 아님 '{values[c]}'" if values[c] else f"{c} 열이 비었음"
            values[c] = ids[0]
    line = values.get("line") or values.get("start")
    row = {}
    for c in t.columns:
        try:
            row[c] = _value(values[c], t.kinds[c], t.schema["properties"].get(c, {}), t.schema["$defs"], line)
        except ValueError as e:
            return None, f"{c} 열: {e}"
    qm = next((c for c in t.columns if t.kinds[c] == "qm"), None)   # 값 열. 11항 converted(환산값)는 둘째라 채우지 않는다
    if qm and row[qm] is None and row.get("status") in _NO_VALUE:  # JSON 경로처럼 값 없는 행의 raw에 상태 글자
        row[qm] = {"raw": row["status"]}
    if t.name == "components" and (q := row.get("content")):    # 함유량은 늘 백분율 (R19). 표 머리글에만 %가 있다
        if any(q.get(k) is not None for k in ("value", "lower", "upper")) and not q.get("unit"):
            q["unit"] = "%"
    if t.name == "physchem" and row.get("q") is None and row.get("text_value") in _NO_VALUE:
        row["q"], row["text_value"] = {"raw": row["text_value"]}, None   # 9항은 상태 열이 없어 값 없음을 q.raw로 옮긴다
    if t.is_object:
        del row["line"]
        row["lines"] = {k: line for k, v in row.items() if v is not None}
    problems = validate(row, t.schema)
    return (None, "; ".join(problems[:2])) if problems else (row, None)


def _realign(t: _Table, cells: list[str]) -> dict | None:
    """열 수가 하나 어긋난 행을 살린 행 dict. 살릴 수 없으면 None (ADR-021).
    모델이 긴 빈 칸 줄에서 빈 칸 하나를 빠뜨리거나 더 쓴 행을 살린다. 예: 19열 독성 표의 ` |  | TX_ORAL | … |  | 값있음 | p8:L8`(18칸)
    - 하나 적으면 모든 자리에 빈 칸을 하나 끼워 보고, 하나 많으면 빈 칸을 하나씩 빼 본다. 검증을 통과한 해석만 남긴다.
    - 값 두 칸 사이에 끼운 해석은 빈 칸 옆·줄 끝에 끼운 해석보다 선택지 열을 덜 채우면 뺀다.
      예: '값있음 | p8:L8' 사이에 끼우면 값있음이 status 대신 statements로 간다.
    - 남은 해석에서 값이 있는 칸의 열 배치가 모두 같을 때만 그 행을 쓴다. 다르면 어느 열인지 모호하다."""
    n = len(t.columns)
    if len(cells) == n + 1:
        tries = [(cells[:k] + cells[k + 1:], True) for k, c in enumerate(cells) if not c]
    elif len(cells) == n - 1:
        blank = [True, *(not c for c in cells), True]       # 줄 양 끝 바깥은 빈 칸으로 본다
        tries = [(cells[:k] + [""] + cells[k:], blank[k] or blank[k + 1]) for k in range(n)]
    else:
        return None
    choice_cols = [c for c in t.columns if _choices(t.schema["properties"].get(c, {}), t.schema["$defs"])]
    readings = []                                           # (값 칸의 열 배치, 채운 선택지 열 수, 빈 칸 옆인가, 행)
    for x, by_blank in tries:
        row, problem = _build(t, x)
        if problem is None:
            readings.append((tuple(i for i, c in enumerate(x) if c), sum(row[c] is not None for c in choice_cols),
                             by_blank, row))
    best = max((f for _, f, b, _ in readings if b), default=0)
    kept = [(p, row) for p, f, b, row in readings if b or f >= best]
    return kept[0][1] if len({p for p, _ in kept}) == 1 else None


def _row(t: _Table, cells: list[str]) -> tuple[dict | None, str | None]:
    """행 한 줄 → (행 dict, None) 또는 (None, 문제). 열 수가 하나 어긋나도 _realign이 살리면 문제 없이 돌려준다."""
    if len(cells) == len(t.columns):
        return _build(t, cells)
    row = _realign(t, cells)
    return (row, None) if row is not None else (None, f"열 {len(cells)}개, 기대 {len(t.columns)}개")


def parse_rows(text: str, no: int) -> tuple[dict, list[str]]:
    """모델 응답 글을 {표 이름: [행 dict, ...], ..., "extras": [...]}로. 둘째 값은 줄 단위 오류 목록.
    - '### 표 이름' 머리글로 표를 나눈다. 머리글이 하나라도 있으면 응답 스키마의 모든 표를 담는다
      (쓰지 않은 표는 [], 객체 칸은 {"lines": {}}). 머리글이 하나도 없으면 오류 하나와 빈 dict.
    - 열 이름 줄, 안내문의 선택지 줄('- `열`: 값 / 값'), 빈 줄, 코드 울타리(```), 마크다운 구분 줄(---|---)은
      건너뛴다. 첫 머리글 앞의 글은 버린다.
    - 행은 '|'로 쪼개고 앞뒤 공백을 뗀다. 열 수가 다르거나, 줄 열이 'p2:L23' 모양이 아니거나, 형이 안 맞거나,
      그 행 스키마 검증에 실패한 줄은 버리고 오류 "<표> p?:L? <줄 앞부분>: <문제>"를 남긴다.
      열 수가 하나 어긋난 줄은 _realign이 살리면 오류 없이 쓴다.
    - 빈 칸은 None(목록 칸은 []). 숫자 묶음은 parse_qm, 숫자 칸은 숫자, enum 칸은 _choice로 맞춘 글자.
    - 상태 열이 자료없음·해당없음·미기재이고 값 열(첫 숫자 묶음 열)이 비면 값 열을 {"raw": 상태}로 채운다."""
    tables = {t.name: t for t in _tables(no)}
    out: dict | None = None
    errors: list[str] = []
    current: _Table | None = None      # 지금 읽는 표. 모르는 표 이름 아래의 줄은 건너뛴다
    for s in (x.strip() for x in (text or "").splitlines()):
        if not s or s.startswith("```") or set(s) <= set("|-: "):
            continue
        if m := _HEADER.match(s):
            if out is None:
                out = {n: ({"lines": {}} if t.is_object else []) for n, t in tables.items()}
            current = tables.get(m[1])
            if current is None:
                errors.append(f"모르는 표 '{m[1]}': 쓸 수 있는 표는 {', '.join(tables)}")
            continue
        if current is None:
            continue
        cells = _cells(s)
        if cells == list(current.columns) or _CHOICE_LINE.match(s):
            continue
        row, problem = _row(current, cells)
        if problem is None and current.is_object and out[current.name] != {"lines": {}}:
            problem = f"{current.name}은 한 행만 쓴다"
        if problem:
            errors.append(f"{_where(current.name, s)}: {problem}")
        elif current.is_object:
            out[current.name] = row
        else:
            out[current.name].append(row)
    if out is None:
        return {}, ["표 머리글이 없음: 표마다 '### 표 이름' 줄 아래에 한 줄에 한 행씩 쓴다"]
    return out, errors
