"""물질 찾기와 물질별 원본 행(분류·독성·물성·규제·노출기준).

독성·물성은 parsed=true를 주면 원본 rows는 그대로 두고 판정 입력용 파싱 결과를 'parsed'로 덧붙인다.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from msds.api.routers.htodb.deps import conn, wrap
from msds.compliance.htodb import parsers, repo
from msds.compliance.htodb.mapping import normalize_cas, normalize_un

router = APIRouter(prefix="/chemicals", tags=["chemicals"])

PARTS = {
    "classifications": repo.classifications,
    "toxicity": repo.toxicity,
    "physical-properties": repo.physical_properties,
    "regulations": repo.regulations,
    "exposure-limits": repo.exposure_limits,
}
PARSED_PARTS = ("toxicity", "physical-properties")


def _chem_or_404(c, chem_id: str) -> dict:
    row = repo.chemical(c, chem_id)
    if row is None:
        raise HTTPException(404, f"CHEM_ID {chem_id} 없음")
    return row


def _parse_rows(part: str, chem: dict, out: dict) -> dict:
    """원본 rows는 그대로 두고, 같은 순서의 파싱 결과 목록을 'parsed'로 붙인다(parsers.py)."""
    if part == "toxicity":
        mw = parsers.to_float(chem.get("molecular_weight"))
        return {
            **out,
            "parsed": [parsers.parse_toxicity_row(r, mw) for r in out["rows"]],
        }
    return {**out, "parsed": [parsers.parse_property_row(r) for r in out["rows"]]}


@router.get("")
def find_chemicals(
    cas: str | None = None,
    ke: str | None = None,
    un: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
):
    given = [k for k, v in (("cas", cas), ("ke", ke), ("un", un)) if v is not None]
    if len(given) != 1:
        raise HTTPException(422, "cas, ke, un 중 하나만 주어야 함")
    with conn() as c:
        return wrap(
            repo.chemicals(
                c,
                cas=None if cas is None else normalize_cas(cas),
                ke=ke,
                un=None if un is None else normalize_un(un),
                limit=limit,
            )
        )


@router.get("/{chem_id}")
def get_chemical(chem_id: str):
    with conn() as c:
        return wrap(_chem_or_404(c, chem_id))


@router.get("/{chem_id}/{part}")
def get_chemical_part(chem_id: str, part: str, parsed: bool = False):
    if part not in PARTS:
        raise HTTPException(404, f"알 수 없는 항목: {part} (가능: {', '.join(PARTS)})")
    if parsed and part not in PARSED_PARTS:
        raise HTTPException(422, f"parsed는 {', '.join(PARSED_PARTS)}에만 쓸 수 있음")
    with conn() as c:
        chem = _chem_or_404(c, chem_id)
        out = PARTS[part](c, chem_id)
        return wrap(_parse_rows(part, chem, out) if parsed else out)
