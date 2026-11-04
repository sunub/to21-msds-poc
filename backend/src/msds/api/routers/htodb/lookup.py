"""추출 JSON 한 건 → 그 안의 코드마다 매핑 번역 결과와 HTODB 원본 행."""

from typing import Annotated

from fastapi import APIRouter, Body, HTTPException

from msds.api.routers.htodb.deps import conn, state, wrap
from msds.compliance.htodb import repo
from msds.compliance.htodb.mapping import Map13, code_sites, normalize_cas, normalize_un

router = APIRouter(tags=["lookup"])


def _resolve(c, m: Map13, site: dict) -> dict:
    kind, v = site["kind"], site["value"]
    if kind in ("cas", "ke", "un"):
        key = {"cas": normalize_cas, "ke": str, "un": normalize_un}[kind](v)
        found = repo.chemicals(c, **{kind: key})
        out = {"lookup_key": key, "chemicals": found}
        if (
            kind == "cas" and found["total"] == 1
        ):  # 세부정보는 CAS로 한 물질이 찾아질 때만(KE 쪽과 중복 방지)
            out["details"] = repo.chemical_details(c, found["rows"][0]["chem_id"])
        return out
    if kind == "h_code":
        return {"reference": repo.h_code(c, v)}
    if kind == "hazard_class":
        mapped = m.hazard(
            v["class_code"], v["category"], v.get("route_form"), v.get("effect")
        )
        return {
            "mapping": mapped,
            "reference": repo.class_codes(c, [x["class_result_code"] for x in mapped]),
        }
    if kind in ("pictogram", "signal_word"):
        return {"mapping": getattr(m, kind)(v)}
    if kind == "property":
        mapped = m.property(v)
        return {
            "mapping": mapped,
            "reference": repo.property_codes(c, [x["property_id"] for x in mapped]),
        }
    if kind == "endpoint":
        mapped = m.endpoint(v)
        return {
            "mapping": mapped,
            "reference": repo.div_codes(c, [d for x in mapped for d in x["div_codes"]]),
        }
    if kind == "regulation":
        mapped = m.regulation(v)
        return {
            "mapping": mapped,
            "reference": repo.regulate_items(
                c, [x["regulate_item_id"] for x in mapped]
            ),
        }
    raise AssertionError(kind)


@router.post("/lookup")
def lookup(doc: Annotated[dict, Body()]):
    """추출 JSON(TO21 스키마) 안의 코드마다 13_TO21DB매핑 번역 결과와 HTODB 원본 행을 돌려준다.
    mapping이 빈 목록이면 시트에 대응이 없다는 뜻이고, 그대로 비워 둔다(추측하지 않음)."""
    try:
        sites = code_sites(doc)
    except ValueError as e:
        raise HTTPException(422, f"추출 JSON 형식 오류: {e}") from e
    with conn() as c:
        return wrap([{**s, **_resolve(c, state["map"], s)} for s in sites])
