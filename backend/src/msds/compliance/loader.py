"""추출 JSON 한 건에서 2차가 읽는 값만 꺼낸다 (2차 입력).

입력 칸 목록은 D 가이드 3.2 표를 따른다. 정합성검증 개발설계서 v0.2 는 저장소에 없어
확인하지 못했다 (docs/adr/0001). missing 에 넣는 칸은 최소 목록이며 설계서를 받으면 맞춘다.
검증기(V01~V23)가 보는 형식 검사는 여기서 하지 않는다.
"""
from typing import Any

from ..common.align import comp_map
from .ghs.models import GhsInputs

_COMPONENT_KEYS = ("seq", "name", "cas_no", "content", "content_note", "trade_secret")
_CLASS_KEYS = ("class_code", "category", "route_form")


def _empty(v: Any) -> bool:
    return v in (None, "", [], {})


def _with_cas(rows: list[dict] | None, cm: dict[str, str]) -> list[dict]:
    """11·12·15항 행에 comp_ref 가 가리키는 성분의 CAS(없으면 이름)를 cas_no 로 붙인다."""
    return [{**r, "cas_no": cm.get(str(r.get("comp_ref")))} for r in rows or []]


def load_inputs(doc: dict, msds_index: int = 0) -> dict:
    """추출 JSON(doc) 의 msds[msds_index] 에서 2차 입력을 만든다.

    칸이 없거나 null 이어도 KeyError 없이 빈 값으로 읽는다. 판정에 꼭 필요한데 비어 있는 칸은
    missing 에 경로 이름으로 담긴다.
    """
    m = (doc.get("msds") or [{}])[msds_index]  # msds 칸이 없으면 빈 MSDS 한 건으로 읽는다
    meta, hz = m.get("meta") or {}, m.get("hazard") or {}
    cm = comp_map(m)
    comps = [{k: c.get(k) for k in _COMPONENT_KEYS} for c in m.get("components") or []]

    # 같은 prop_code 가 여러 줄일 수 있다 (예: 조건이 다른 pH). 덮어쓰지 않고 줄을 모은다.
    physchem: dict[str, list[dict]] = {}
    for p in m.get("physchem") or []:
        physchem.setdefault(p.get("prop_code"), []).append(p)

    out = {
        "doc_id": (doc.get("doc") or {}).get("doc_id"),
        "msds_index": msds_index,
        "as_of_date": meta.get("last_revision_date") or meta.get("first_issue_date"),
        "composition": m.get("composition") or {},
        "components": comps,
        "hazard": {
            "classes": [{k: x.get(k) for k in _CLASS_KEYS} for x in hz.get("classes") or []],
            "h_codes": [h.get("code") for h in hz.get("h_statements") or []],
            "pictograms": [p.get("code") for p in hz.get("pictograms") or []],
            "signal_word": hz.get("signal_word"),
        },
        "physchem": physchem,
        "toxicity": _with_cas(m.get("toxicity"), cm),
        "ecotox": _with_cas(m.get("ecotox"), cm),
        "regulations": _with_cas(m.get("regulations"), cm),
        "dangerous_goods": m.get("dangerous_goods") or [],
    }
    need = {
        "as_of_date": out["as_of_date"],
        "composition.type": out["composition"].get("type"),
        "components": comps,
        "hazard.classes": out["hazard"]["classes"],
        "hazard.signal_word": out["hazard"]["signal_word"],
    }
    out["missing"] = [k for k, v in need.items() if _empty(v)]
    return out


def load_ghs_inputs(doc: dict, msds_index: int = 0) -> GhsInputs:
    """기존 2차 입력을 TO21 이름을 보존하는 타입 계약으로 검증해 돌려준다."""
    return GhsInputs.model_validate(load_inputs(doc, msds_index))
