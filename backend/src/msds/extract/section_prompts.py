"""항목 하나를 부를 때 쓸 시스템 안내문과 사용자 메시지를 TO21 v0.6 명세서에서 실행할 때 만든다 (B, ADR-001·003).

안내문 = 공통 지시 + 이 항의 안내(GUIDES) + 명세서에서 꺼낸 [필드 정의] [규칙] [코드표] [동의어]
- 필드 정의에는 중간 형식 스키마(section_specs.response_schema)에 있는 칸만 넣는다. 코드가 채우는 칸
  (CODE_OWNED, comp_ref)은 모델에게 요구하지 않는다.
- 안내문은 파일로 저장하지 않는다. 명세서 내용이 들어 있어 저장소에 남기면 안 된다 (D-47).
  실행 기록에는 SECTION_PROMPT_VERSION과 prompt_hash만 남긴다.
- 평가용 문서(25번 포함)의 내용을 예시로 넣지 않는다. 명세서의 '예시(가상)' 값만 쓴다 (D-43).
- 행 형식 항(build_system(no, rows=True))은 공통 지시를 _COMMON_ROWS로 바꾸고 끝에 [응답 형식](rows_guide)을
  붙인다. 이 항의 안내·필드 정의·규칙·코드표·동의어는 JSON 안내문과 같은 것을 쓴다 (ADR-019).
- 2항은 쪽 이미지를 받는 태그면 사용자 메시지 끝에 쪽 이미지를 붙인다(build_user의 images). 모델이 그림문자를 읽는다 (ADR-019).
"""
from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

import openpyxl

from msds.common.paths import to21_file
from msds.extract.inputs import Line, render_lines
from msds.extract.prompt_builder import _BASE_RULES, _code_table, _field_rows, _referenced_rules, _rows, _rules
from msds.extract.rows import rows_guide
from msds.extract.section_specs import SectionSpec, load_specs, response_schema

SECTION_PROMPT_VERSION = "s5"   # 안내문 내용을 고치면 올린다. 실행 기록에 남는다. s3은 10/28에 되돌린 extras 규칙판이 썼다. s5: 행 형식 안내, 2항 그림문자(C2 코드표·이미지 안내) 추가. 14항도 행 형식(s5 실행 전이라 버전 유지). 그 밖의 JSON 안내문은 s4와 같다
IMAGE_MAX_SIDE = 1200           # 2항에 붙이는 쪽 이미지의 긴 변 픽셀 (ADR-019)
_IMAGE_NOTE = "[2항이 있는 쪽 이미지. 그림문자(마름모 안 그림)를 보고 pictograms에 GHS 코드를 적는다]"

_COMMON = """너는 한국어 물질안전보건자료(MSDS)의 {no}항 "{title}"만 읽어 정해진 JSON 형식으로 옮기는 추출기다. 해석하거나 추측하지 않는다.
- 원문에 적힌 행만 쓴다. 원문에 없는 행을 만들지 않는다. 값이 "자료없음", "해당없음"처럼 적힌 행도 원문에 있으면 행으로 쓰고, 그 글자를 숫자 묶음의 `raw`에 그대로 둔다.
- 값이 없는 칸은 쓰지 않는다. null이나 빈 배열([])을 쓰지 말고 칸 이름째 뺀다. 칸 설명에 "없으면 null"이라고 적혀 있어도 같다. 행의 `line`과 객체 칸의 `lines`는 늘 쓴다.
- 모든 행의 `line`(객체 칸은 `lines`의 칸 이름마다)에는 그 값이 적힌 줄 앞의 줄 번호를 보이는 그대로 적는다. 예: `p2:L23`. 숫자만 쓰지 않는다.
- 숫자 묶음은 `raw`에 원문 그대로 두고, 나머지 칸(value, lower_op, lower, upper_op, upper, unit, approx)은 규칙(R04, R06, R08)대로 나눈다.
- `value`와 `lower`·`upper`는 함께 쓰지 않는다. 단일값이면 `value`만 쓴다. 부등호나 범위로 적힌 값은 `lower_op`·`lower`·`upper_op`·`upper` 쪽만 쓴다. 예: `99.92` → value 99.92 / `≥ 95` → lower_op ">=", lower 95
- 다른 항의 내용이 섞여 보이면 무시한다. 스키마에 맞는 칸이 없는 이 항의 내용은 `extras`에 담는다(R24)."""

# 행 형식 항의 공통 지시. 칸을 나누는 규칙은 맨 끝의 [응답 형식](rows.rows_guide)에 있다.
_COMMON_ROWS = """너는 한국어 물질안전보건자료(MSDS)의 {no}항 "{title}"만 읽어 정해진 행 형식으로 옮기는 추출기다. 해석하거나 추측하지 않는다.
- 원문에 적힌 행만 쓴다. 원문에 없는 행을 만들지 않는다.
- 응답은 맨 끝의 [응답 형식]대로 쓴다. [필드 정의]의 경로 `표[].열`(객체 칸은 `표.열`)은 [응답 형식]의 그 표의 그 열이다.
- 다른 항의 내용이 섞여 보이면 무시한다. 맞는 열이 없는 이 항의 내용은 `extras` 표에 담는다(R24)."""

# 이 항의 안내: 명세서에 없는, 행을 나누는 단위와 자주 틀리는 점
GUIDES = {
    1: """- 회사(companies)는 역할(제조자·수입자·공급자 등)마다 한 행이다.
- 전화·팩스·이메일은 contacts로 나누고, 긴급 연락처는 type="긴급"으로 둔다. 전화번호는 R12.
- MSDS 번호(msds_no)와 회사 내부 문서번호(doc_code)를 구분한다. 날짜는 R01.""",
    2: """- 유해성 분류(hazard.classes)는 분류마다 한 행이다. 구분(category)에서 '구분' 글자를 뺀다(R07).
- 노출 형태(가스 / 증기 / 분진·미스트)가 적혀 있으면 route_form에 원문대로 둔다.
- H·P코드는 R05, R21. P코드의 type은 첫 자리로 정한다.
- 그림문자(pictograms)는 붙은 쪽 이미지에서 마름모 안 그림을 보고 그림 하나에 한 행으로 GHS 코드(`code`)만 적는다. 이미지가 없으면 pictograms를 쓰지 않는다.""",
    3: """- 성분(components)은 성분표의 행마다 한 성분이다.
- CAS 번호와 KE 번호가 한 칸에 있어도 나눈다(R02, R03).
- 함유량(content)은 숫자 묶음으로 나눈다(R04, R06, R19).
- 영업비밀·대체자료 표기는 R13, 승인번호가 성분표 아래 한 번만 있으면 R23.""",
    8: """- 노출기준(exposure_limits)은 성분 × 기준 출처(국내·ACGIH 등) × 기준 종류(TWA·STEL 등)마다 한 행이다. TWA와 STEL을 한 행에 합치지 않는다.""",
    9: """- 물리화학적 특성(physchem)은 특성마다 한 행이다. 숫자 값은 q, 글자 값은 text_value에 두고, 괄호 속 측정 조건은 cond로 나눈다.
- 특성 이름의 표기가 달라도 [동의어]로 prop_code를 정한다(R25). 점도와 동점도는 R26.""",
    11: """- 독성(toxicity)은 성분 × 독성 항목(endpoint) × 지표(LD50·LC50 등) × 시험 동물마다 한 행이다.
- 발암성·생식세포변이원성·생식독성의 기관별 분류(cmr)는 기관마다 한 행이다.""",
    12: """- 생태독성(ecotox)은 성분 × 항목(endpoint) × 지표 × 생물종마다 한 행이다.""",
    14: """- 운송(transport)은 운송 방식(mode)마다 한 행이다. UN번호는 R09.""",
    15: """- 국내 규제(regulations)는 성분 × 법령(law) × 규제 항목(item_code)마다 한 행이다. 해당·비해당·자료없음도 원문에 적힌 대로 행으로 쓴다.
- 규제 항목 이름의 표기가 달라도 [동의어]로 item_code를 정한다(R25).
- 위험물안전관리법은 dangerous_goods, 폐기물관리법의 지정폐기물 여부는 waste, 해외 분류는 intl_class에 둔다.""",
    16: """- 최초 작성일·개정 횟수·최종 개정일이 있으면 `meta_revision`에 적는다. 날짜는 R01.""",
}
_COMP_GUIDE = ("- 성분이 따로 적힌 행은 `comp_name`·`comp_cas`에 원문의 성분 이름과 CAS 번호를 적는다. "
               "제품 전체 값이면 둘 다 쓰지 않는다.")
_NARRATIVE_GUIDE = ("- 서술 항목(narratives)은 항목 코드마다 한 행이다. `item_code`, 원문 제목(`title_raw`), "
                    "내용이 시작·끝나는 줄 번호(`start`, `end`)만 적는다. 문장을 다시 쓰지 않는다.")

# 필드 정의의 [참조]에 나온 코드표. C3은 이 항의 줄만 넣는다. C2(그림문자)는 2항 필드 정의만 가리킨다.
_CODE_TABLES = {"C1": "5-1_유해성분류", "C2": "5-2_그림문자", "C4": "5-4_물리화학", "C5": "5-5_독성생태",
                "C6": "5-6_법규제", "C7": "5-7_기타코드", "C8": "5-8_발암성기관"}
_DICTIONARY = {9: "physchem", 15: "regulations"}   # R25
_FIELD_PATH = re.compile(r"^- `([^`]+)`")


@lru_cache(maxsize=1)
def _workbook():
    return openpyxl.load_workbook(to21_file("spec"), data_only=True)


@lru_cache(maxsize=1)
def _dictionary() -> dict:
    return json.loads(to21_file("dictionary").read_text(encoding="utf-8"))


def _unwrap(schema: dict, node: dict) -> dict:
    """$ref, null 허용(anyOf), 배열을 벗겨 안쪽 스키마로."""
    while True:
        if "$ref" in node:
            node = schema["$defs"][node["$ref"].rsplit("/", 1)[1]]
        elif "anyOf" in node:
            node = next(b for b in node["anyOf"] if b.get("type") != "null")
        elif node.get("type") == "array":
            node = node["items"]
        else:
            return node


def _in_schema(schema: dict, path: str) -> bool:
    """명세서 필드 경로(예: companies[].contacts[].value)가 중간 형식 스키마에 있는가."""
    node = schema
    for key in path.replace("[]", "").split("."):
        node = _unwrap(schema, node).get("properties", {}).get(key)
        if node is None:
            return False
    return True


def _fields(wb, spec: SectionSpec, schema: dict) -> list[str]:
    rows = _field_rows(wb, [t for t in spec.targets if t != "meta_revision"], [])
    if "meta_revision" in spec.targets:   # 16항 개정 정보는 명세서 meta 칸의 정의를 쓴다
        rows += [r.replace("`meta.", "`meta_revision.", 1) for r in _field_rows(wb, ["meta"], [])]
    rows += _field_rows(wb, ["extras"], [])
    return [r for r in rows if _in_schema(schema, _FIELD_PATH.match(r).group(1))]


def _guide(spec: SectionSpec, schema: dict) -> str:
    parts = [GUIDES[spec.no]] if spec.no in GUIDES else []
    if any('"comp_name"' in json.dumps(schema["properties"][t]) for t in spec.targets):
        parts.append(_COMP_GUIDE)
    if spec.narrative_codes:
        parts.append(_NARRATIVE_GUIDE)
    return "\n".join(parts)


def _narrative_table(wb, codes: tuple[str, ...]) -> list[str]:
    rows = _rows(wb["5-3_서술항목"])
    return [f"### {rows[0][0]}", " | ".join(x for x in rows[3] if x),
            *(" | ".join(x for x in r if x) for r in rows[4:] if r[1] in codes)]


def build_system(no: int, rows: bool = False) -> str:
    """rows=True면 표를 한 줄 한 행으로 받는 안내문이다 (ADR-019)."""
    spec = load_specs()[no]
    schema = response_schema(no)
    wb = _workbook()
    common = (_COMMON_ROWS if rows else _COMMON).format(no=no, title=spec.title)
    guide = _guide(spec, schema)
    fields = _fields(wb, spec, schema)
    rule_codes = _BASE_RULES | _referenced_rules(fields) | set(re.findall(r"R\d{2}", common + guide))
    refs = re.findall(r"\[참조 ([^\]]*)\]", "\n".join(fields))
    tables = sorted(set(re.findall(r"\bC\d\b", " ".join(refs))))

    parts = [
        common,
        "",
        "## 이 항의 안내",
        guide,
        "",
        "## [필드 정의] (TO21 명세서 1_항목정의)",
        "형식: `경로` 이름 — 타입, 중요도. 형식·분해 규칙 [참조] 예(가상 값)",
        *fields,
        "",
        "## [규칙] (TO21 명세서 3_정규화규칙)",
        *_rules(wb, rule_codes),
    ]
    if any(c == "C3" or c in _CODE_TABLES for c in tables):
        parts += ["", "## [코드표]"]
        for c in tables:
            if c == "C3":
                parts += _narrative_table(wb, spec.narrative_codes)
            elif c in _CODE_TABLES:
                parts += _code_table(wb, _CODE_TABLES[c])
    if no in _DICTIONARY:
        key = _DICTIONARY[no]
        parts += ["", "## [동의어] 표기가 달라도 같은 코드로 본다 (공백·구두점·가운뎃점은 무시)", f"### {key}",
                  *(f"- {code}: " + " / ".join(names) for code, names in _dictionary()[key].items())]
    if rows:
        parts += ["", "## [응답 형식] 한 줄에 한 행", rows_guide(no)]
    return "\n".join(parts).strip() + "\n"


def build_user(no: int, lines: list[Line], retry_feedback: str | None = None,
               images: list[Path] = ()) -> list[dict]:
    """글 part 하나. images가 있으면 그 뒤에 안내 글 하나와 쪽 이미지(긴 변 IMAGE_MAX_SIDE 이하)를 차례로 붙인다."""
    text = f"[{no}항 원문]\n" + render_lines(lines)
    if retry_feedback:
        text += "\n\n[다시 확인할 점]\n" + retry_feedback
    parts = [{"type": "text", "text": text}]
    if images:
        from msds.extract.client import image_part   # client가 nuextract_examples를 거쳐 이 모듈을 import하므로 여기서 부른다

        parts += [{"type": "text", "text": _IMAGE_NOTE}, *(image_part(p, max_side=IMAGE_MAX_SIDE) for p in images)]
    return parts


def prompt_hash(no: int, rows: bool = False) -> str:
    """build_system(no, rows)의 sha256 앞 12자리. 실행 기록용."""
    return hashlib.sha256(build_system(no, rows).encode("utf-8")).hexdigest()[:12]
