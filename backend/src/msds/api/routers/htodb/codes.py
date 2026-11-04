"""코드 기준정보: GHS 분류, H 문구, 독성 구분, 물성, 규제 항목 코드 한 건씩."""

from fastapi import APIRouter

from msds.api.routers.htodb.deps import conn, wrap
from msds.compliance.htodb import repo

router = APIRouter(prefix="/codes", tags=["codes"])


@router.get("/ghs-class/{code}")
def get_class_code(code: str):
    with conn() as c:
        return wrap(repo.class_codes(c, [code])[code])


@router.get("/h/{code}")
def get_h_code(code: str):
    with conn() as c:
        return wrap(repo.h_code(c, code))


@router.get("/div/{code}")
def get_div_code(code: str):
    with conn() as c:
        return wrap(repo.div_codes(c, [code])[code])


@router.get("/property/{code}")
def get_property_code(code: str):
    with conn() as c:
        return wrap(repo.property_codes(c, [code])[code])


@router.get("/regulate-item/{code}")
def get_regulate_item(code: str):
    with conn() as c:
        return wrap(repo.regulate_items(c, [code])[code])
