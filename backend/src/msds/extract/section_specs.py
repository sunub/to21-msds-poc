"""법정 16개 항목별 호출이 채울 TO21 칸과 모델이 쓸 중간 형식 스키마 (B, ADR-001·002).

중간 형식은 TO21 v0.6 스키마(msds_item_schema)에서 실행할 때 만든다. 칸을 손으로 다시 적지 않으므로
TO21이 스키마를 고쳐도 따라간다. 명세서 내용이 들어가므로 파일로 저장하지 않는다 (D-47).

TO21 스키마에서 바꾸는 것
- 행(객체 배열의 항목)마다 근거 줄 line("p2:L23")을 더하고, 객체 칸에는 칸 이름 → 줄 번호인 lines를 더한다.
- Q는 QM(QM_FIELDS만)으로 바꾼다. status·dp·note는 코드가 정한다.
- comp_ref는 comp_name·comp_cas로 바꾼다. 이 호출은 3항의 성분 번호를 모르고, 펼치기가 3항과 맞춰 붙인다.
- narratives 행은 item_code·title_raw·start·end만 받는다. 문장(statements)은 코드가 줄을 나눠 만든다 (R14).
- CODE_OWNED의 칸은 받지 않는다.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from functools import lru_cache

import openpyxl

from msds.common.paths import to21_file
from msds.common.schema import load_schema, msds_item_schema

QM_FIELDS = ("raw", "value", "approx", "lower_op", "lower", "upper_op", "upper", "unit")
META_REVISION_FIELDS = ("first_issue_date", "revision_no", "revision_label", "last_revision_date")

# 키: "msds"는 msds 항목의 최상위 키, "*"는 모든 행(객체 배열의 항목), "STMT"는 $defs.STMT, 나머지는 TO21 msds 키
CODE_OWNED: dict[str, set[str]] = {
    "msds": {"evidence", "validation"},           # 근거는 줄 번호로 코드가 채우고, 검증은 검사 단계가 쓴다
    "*": {"seq"},                                 # 순번은 행 순서대로 코드가 붙인다
    "meta": {"page_start", "page_end"},           # 항목 분할의 쪽 범위(MsdsPart.pages)로 안다
    "hazard": {"pictograms"},                     # 그림문자 모델 몫 (10/31)
    "narratives": {"status", "statements"},       # 코드가 start~end 줄을 문장으로 나눈다 (R14)
    "extras": {"page", "section_no"},             # 쪽은 line에서, 항 번호는 호출에서 안다
    "STMT": {"text", "std_code", "match_score"},  # 원문 줄은 line에서 채우고, 문구DB 매칭은 하지 않는다
}

# 항 번호 → (법정 항목 이름, 채울 TO21 키). 명세서 1_항목정의의 'MSDS 항목' 열과 같다.
# meta_revision은 TO21 키가 아니라 16항 전용 객체다. 펼치기가 1항 meta의 빈 칸만 채운다.
_SECTIONS = {
    1: ("화학제품과 회사에 관한 정보", ("meta", "product", "companies")),
    2: ("유해성·위험성", ("hazard", "narratives")),
    3: ("구성성분의 명칭 및 함유량", ("composition", "components")),
    4: ("응급조치 요령", ("narratives",)),
    5: ("폭발·화재 시 대처방법", ("narratives",)),
    6: ("누출 사고 시 대처방법", ("narratives",)),
    7: ("취급 및 저장방법", ("narratives",)),
    8: ("노출방지 및 개인보호구", ("exposure_limits", "narratives")),
    9: ("물리화학적 특성", ("physchem",)),
    10: ("안정성 및 반응성", ("narratives",)),
    11: ("독성에 관한 정보", ("toxicity", "cmr", "narratives")),
    12: ("환경에 미치는 영향", ("ecotox", "narratives")),
    13: ("폐기 시 주의사항", ("narratives",)),
    14: ("운송에 필요한 정보", ("transport", "narratives")),
    15: ("법적 규제현황", ("regulations", "dangerous_goods", "waste", "intl_class", "narratives")),
    16: ("그 밖의 참고사항", ("narratives", "meta_revision")),
}

_LINE = {"type": "string", "description": "근거 줄 번호. 입력 줄 앞의 번호를 그대로 쓴다 (예: p2:L23)"}
_NULL_STR = {"anyOf": [{"type": "string"}, {"type": "null"}]}


@dataclass(frozen=True)
class SectionSpec:
    no: int                          # 1~16
    title: str                       # 법정 항목 이름
    targets: tuple[str, ...]         # 채울 TO21 msds 최상위 키
    narrative_codes: tuple[str, ...] # 명세서 5-3_서술항목에서 이 항의 item_code


def _narrative_codes() -> dict[int, list[str]]:
    """명세서 5-3_서술항목: 첫 열 = 항 번호, 둘째 열 = 코드."""
    wb = openpyxl.load_workbook(to21_file("spec"), read_only=True, data_only=True)
    codes: dict[int, list[str]] = {}
    for r in wb["5-3_서술항목"].iter_rows(values_only=True):
        no, code = ("" if c is None else str(c).strip() for c in r[:2])
        if no.isdigit() and code:
            codes.setdefault(int(no), []).append(code)
    wb.close()
    return codes


@lru_cache(maxsize=1)
def load_specs() -> dict[int, SectionSpec]:
    codes = _narrative_codes()
    specs = {}
    for no, (title, targets) in _SECTIONS.items():
        nc = tuple(codes.get(no, ()))
        specs[no] = SectionSpec(no, title, tuple(t for t in targets if t != "narratives" or nc), nc)
    return specs


# ── 중간 형식 스키마 ───────────────────────────────────

def _required(node: dict, props: dict) -> list[str]:
    return [r for r in node.get("required", []) if r in props]


def _props(node: dict, path: str, owned: set[str] = frozenset()) -> dict:
    """객체의 칸을 바꾼다: 코드 몫 칸을 빼고, comp_ref를 이름·CAS로 바꾸고, 안쪽을 _convert한다."""
    owned = CODE_OWNED.get(path, set()) | owned
    out = {}
    for k, v in node["properties"].items():
        if k in owned:
            continue
        if k == "comp_ref":
            out["comp_name"] = {**_NULL_STR, "description": "대상 성분 이름. 원문 그대로. 제품 전체 값이면 null"}
            out["comp_cas"] = {**_NULL_STR, "description": "대상 성분의 CAS 번호. 원문에 없으면 null"}
            continue
        out[k] = _convert(v, f"{path}.{k}")
    return out


def _row(item: dict, path: str) -> dict:
    """행(객체 배열의 항목) 하나: 근거 줄 line을 더한다."""
    props = _props(item, path, CODE_OWNED["*"])
    props["line"] = _LINE
    return {**item, "properties": props, "required": _required(item, props) + ["line"]}


def _convert(node, path: str):
    """TO21 스키마 조각을 중간 형식으로 바꾼다. path는 msds 키부터의 점 경로 (예: hazard.classes)."""
    if isinstance(node, list):
        return [_convert(v, path) for v in node]
    if not isinstance(node, dict):
        return node
    if node.get("$ref") == "#/$defs/Q":
        return {**node, "$ref": "#/$defs/QM"}
    if node.get("type") == "array" and "properties" in node.get("items", {}):
        return {**node, "items": _row(node["items"], path)}
    if node.get("type") == "object" and "properties" in node:
        props = _props(node, path)
        return {**node, "properties": props, "required": _required(node, props)}
    return {k: _convert(v, path) for k, v in node.items()}


def _has_own_line(node: dict) -> bool:
    items = node.get("items", {}) if node.get("type") == "array" else {}
    return "line" in items.get("properties", {}) or items.get("$ref") == "#/$defs/STMT"


def _object(node: dict, path: str) -> dict:
    """객체 칸(meta, product, hazard, composition, meta_revision): 칸 이름 → 줄 번호인 lines를 더한다."""
    props = _props(node, path)
    lines = {k: _NULL_STR for k, v in props.items() if not _has_own_line(v)}
    props["lines"] = {"type": "object", "additionalProperties": False,
                      "description": "칸 이름 → 근거 줄 번호 (예: p2:L23). 값이 없는 칸은 null",
                      "properties": lines}
    return {**node, "properties": props, "required": _required(node, props) + ["lines"]}


def _narratives(node: dict, codes: tuple[str, ...]) -> dict:
    item = node["items"]
    props = {k: v for k, v in item["properties"].items() if k not in CODE_OWNED["narratives"]}
    props["item_code"] = {"type": "string", "enum": list(codes),
                          "description": props["item_code"].get("description", "")}
    props["start"] = {"type": "string", "description": "이 서술 항목의 첫 줄 번호 (예: p3:L10)"}
    props["end"] = {"type": "string", "description": "이 서술 항목의 마지막 줄 번호 (예: p3:L14)"}
    return {**node, "items": {**item, "properties": props, "required": ["item_code", "start", "end"]}}


def _meta_revision(meta: dict) -> dict:
    return {"type": "object", "additionalProperties": False,
            "description": "16항에 적힌 개정 정보 (최초 작성일, 개정 횟수·이름, 최종 개정일)",
            "properties": {f: meta["properties"][f] for f in META_REVISION_FIELDS}}


def _defs() -> dict:
    d = load_schema()["$defs"]
    q = d["Q"]
    qm_props = {f: q["properties"][f] for f in QM_FIELDS}
    qm = {"type": "object", "additionalProperties": False, "description": q.get("description", ""),
          "properties": qm_props, "required": _required(q, qm_props)}
    return {"QM": qm, "COND": d["COND"], "STMT": _row(d["STMT"], "STMT")}


def _refs(node) -> set[str]:
    return set(re.findall(r'"#/\$defs/(\w+)"', json.dumps(node)))


def response_schema(no: int) -> dict:
    """no항 호출의 응답 형식: {<target>: ..., "extras": [...]}. ChatClient.call에 그대로 넘긴다."""
    spec = load_specs()[no]
    item = msds_item_schema()["properties"]
    props = {}
    for key in spec.targets:
        if key == "narratives":
            props[key] = _narratives(item[key], spec.narrative_codes)
        elif key == "meta_revision":
            props[key] = _object(_meta_revision(item["meta"]), key)
        elif item[key].get("type") == "object":
            props[key] = _object(item[key], key)
        else:
            props[key] = _convert(item[key], key)
    props["extras"] = _convert(item["extras"], "extras")

    defs, used, todo = _defs(), set(), _refs(props)
    while todo:
        name = todo.pop()
        used.add(name)
        todo |= _refs(defs[name]) - used
    return copy.deepcopy({"type": "object", "additionalProperties": False,
                          "$defs": {k: v for k, v in defs.items() if k in used},
                          "properties": props, "required": list(props)})
