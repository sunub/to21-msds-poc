"""표 항목의 행 형식 출력: 안내와 파서 (B, ADR-019).

표 항목(3·8·9·11·12·15항)은 JSON 대신 '한 줄 한 행' 글로 받는다. 칸 이름이 행마다 반복되지 않아 출력이
짧고, 문법 강제가 없어 공백 폭주가 없다. 모델은 표마다 `### 표 이름` 아래에 ` | `로 나눈 고정 열을 쓰고,
parse_rows가 지금의 중간 형식 dict(section_specs.response_schema)로 바꾼다. 펼치기는 그대로 쓴다.
- 열은 response_schema(no)의 행 칸 순서 그대로다. 스키마의 칸과 필수 칸은 바꾸지 않는다.
- 객체 칸(3항 composition)은 한 행짜리 표다. 줄(line) 열 하나를 값이 있는 칸마다 lines에 쓴다.
- 숫자 묶음(QM)은 열 하나다. 모델은 원문 표기대로 쓰고 parse_qm이 R04·R06·R08대로 나눈다.
- 목록 칸은 '; '로 나누고, 서술 문장(statements)은 그 행의 줄을 근거로 단다. 조건(cond)은 '칸=값; 칸=값'이다.
- 행마다 그 행의 스키마로 검증한다. 틀린 줄은 버리고 줄 단위 오류로 돌려준다. 실행기가 재추출 피드백에 넣는다.
예시 행은 직접 만든 가짜 값이다 (D-43).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from msds.common.schema import validate
from msds.extract.section_specs import response_schema

ROWS_SECTIONS_DEFAULT = (3, 8, 9, 11, 12, 15)   # 표 항목. models.yaml 태그의 rows_sections로 켠다

_LINE_COLS = ("line", "start", "end")
_LINE_ID = re.compile(r"p\d+:L\d+")
_HEADER = re.compile(r"^#+\s*(\S*)")
_SCALARS = ("string", "number", "integer", "boolean")
_EXCERPT = 40         # 오류에 적는 줄 앞부분 글자 수


# ── 숫자 묶음 ──────────────────────────────────────────

_NUM = r"[-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?"
_QM = re.compile(rf"^(?P<op>>=|=>|≥|<=|=<|≤|>|<)?\s*(?P<a>{_NUM})(?:\s*[~～∼\-–]\s*(?P<b>{_NUM}))?\s*(?P<rest>.*)$")
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
    if m["b"]:
        q.update(lower_op=">=", lower=a, upper_op="<=", upper=_number(m["b"]))
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
- 원문에 값 없이 "자료없음", "해당없음"처럼 적힌 행도 빠뜨리지 말고 쓴다. 그 글자는 숫자 묶음 열이 있으면 거기에 쓰고, 상태 열(`status`)이 있으면 상태 열에 `자료없음`·`해당없음`·`미기재` 중 원문의 것을 쓴다.
- 숫자 묶음 열({qm})에는 부등호·숫자·단위를 원문 표기대로 쓴다. 나누기는 코드가 한다. 단위가 표 머리글에만 있으면 값 뒤에 붙인다. 예: `20 ~ 30 %`, `> 2000 mg/kg`, `약 1.2 g/cm3`
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


def rows_guide(no: int) -> str:
    """안내문 끝에 붙일 [응답 형식]: 쓰는 규칙과, 표마다 '### 표 이름' 줄 + 열 이름 줄 + 예시 행(가짜 값)."""
    tables = _tables(no)

    def cols(*kinds: str) -> str:
        return ", ".join(dict.fromkeys(f"`{c}`" for t in tables for c in t.columns if t.kinds[c] in kinds))

    out = [_GUIDE.format(qm=cols("qm"))]
    if multi := cols("list", "stmts"):
        out.append(f"- 값 여러 개를 담는 열({multi})은 값마다 `; `로 나눈다.")
    if flags := cols("boolean"):
        out.append(f"- 참/거짓 열({flags})에는 `true` 또는 `false`를 쓴다.")
    for t in tables:
        for c in t.columns:
            if t.kinds[c] == "pairs":
                fields = _resolve(t.schema["properties"][c], t.schema["$defs"])["properties"]
                out.append(f"- `{c}` 열에는 `칸=값`을 `; `로 이어 쓴다. 칸: {', '.join(fields)}")
    for t in tables:
        out += ["", f"### {t.name}", " | ".join(t.columns),
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
    return text


def _row(t: _Table, cells: list[str]) -> tuple[dict | None, str | None]:
    """행 한 줄 → (행 dict, None) 또는 (None, 문제)."""
    if len(cells) != len(t.columns):
        return None, f"열 {len(cells)}개, 기대 {len(t.columns)}개"
    values = dict(zip(t.columns, cells))
    for c in t.columns:
        if t.kinds[c] == "line" and not _LINE_ID.fullmatch(values[c]):
            return None, f"{c} 열이 줄 번호(p2:L23 모양)가 아님 '{values[c]}'" if values[c] else f"{c} 열이 비었음"
    line = values.get("line") or values.get("start")
    row = {}
    for c in t.columns:
        try:
            row[c] = _value(values[c], t.kinds[c], t.schema["properties"].get(c, {}), t.schema["$defs"], line)
        except ValueError as e:
            return None, f"{c} 열: {e}"
    if t.is_object:
        del row["line"]
        row["lines"] = {k: line for k, v in row.items() if v is not None}
    problems = validate(row, t.schema)
    return (None, "; ".join(problems[:2])) if problems else (row, None)


def parse_rows(text: str, no: int) -> tuple[dict, list[str]]:
    """모델 응답 글을 {표 이름: [행 dict, ...], ..., "extras": [...]}로. 둘째 값은 줄 단위 오류 목록.
    - '### 표 이름' 머리글로 표를 나눈다. 머리글이 하나라도 있으면 응답 스키마의 모든 표를 담는다
      (쓰지 않은 표는 [], 객체 칸은 {"lines": {}}). 머리글이 하나도 없으면 오류 하나와 빈 dict.
    - 열 이름 줄, 빈 줄, 코드 울타리(```), 마크다운 구분 줄(---|---)은 건너뛴다. 첫 머리글 앞의 글은 버린다.
    - 행은 '|'로 쪼개고 앞뒤 공백을 뗀다. 열 수가 다르거나, 줄 열이 'p2:L23' 모양이 아니거나, 형이 안 맞거나,
      그 행 스키마 검증에 실패한 줄은 버리고 오류 "<표> p?:L? <줄 앞부분>: <문제>"를 남긴다.
    - 빈 칸은 None(목록 칸은 []). 숫자 묶음은 parse_qm, 숫자 칸은 숫자, enum 칸은 글자 그대로."""
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
        if cells == list(current.columns):
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
