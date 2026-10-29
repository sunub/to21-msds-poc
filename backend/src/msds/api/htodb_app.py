"""TO21 지식DB(HTODB) 조회 API (읽기 전용). 원본 값을 그대로 돌려주고, 해석·판정은 하지 않는다.

실행: cd backend && .venv/bin/uvicorn --app-dir src msds.api.htodb_app:app --port 8010  (문서: /docs)
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Body, FastAPI, HTTPException, Query
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from msds.compliance.htodb import repo
from msds.compliance.htodb.config import pg_kwargs
from msds.compliance.htodb.mapping import Map13, code_sites, normalize_cas, normalize_un

state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 쓰기 권한 없는 계정 + 읽기 전용 세션(config.pg_kwargs), 두 겹으로 막는다.
    pool = ConnectionPool("", kwargs={**pg_kwargs("reader"), "row_factory": dict_row}, min_size=1, max_size=8, open=True)
    with pool.connection() as conn:
        state["versions"] = repo.versions(conn)
        state["map"] = Map13(conn.execute("SELECT * FROM htodb_map.sheet13 ORDER BY sheet_row").fetchall())
    state["pool"] = pool
    yield
    pool.close()


app = FastAPI(title="TO21 HTODB 조회 API", lifespan=lifespan)


def _wrap(data) -> dict:
    return {**state["versions"], "data": data}


def _conn():
    return state["pool"].connection()


@app.get("/health")
def health():
    with _conn() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok", **state["versions"]}


# ---- 물질 ----

@app.get("/chemicals")
def find_chemicals(cas: str | None = None, ke: str | None = None, un: str | None = None,
                   limit: Annotated[int, Query(ge=1, le=500)] = 50):
    given = [k for k, v in (("cas", cas), ("ke", ke), ("un", un)) if v is not None]
    if len(given) != 1:
        raise HTTPException(422, "cas, ke, un 중 하나만 주어야 함")
    with _conn() as conn:
        return _wrap(repo.chemicals(conn, cas=None if cas is None else normalize_cas(cas), ke=ke,
                                    un=None if un is None else normalize_un(un), limit=limit))


def _chem_or_404(conn, chem_id: str) -> dict:
    row = repo.chemical(conn, chem_id)
    if row is None:
        raise HTTPException(404, f"CHEM_ID {chem_id} 없음")
    return row


@app.get("/chemicals/{chem_id}")
def get_chemical(chem_id: str):
    with _conn() as conn:
        return _wrap(_chem_or_404(conn, chem_id))


PARTS = {
    "classifications": repo.classifications, "toxicity": repo.toxicity,
    "physical-properties": repo.physical_properties, "regulations": repo.regulations,
    "exposure-limits": repo.exposure_limits,
}


@app.get("/chemicals/{chem_id}/{part}")
def get_chemical_part(chem_id: str, part: str):
    if part not in PARTS:
        raise HTTPException(404, f"알 수 없는 항목: {part} (가능: {', '.join(PARTS)})")
    with _conn() as conn:
        _chem_or_404(conn, chem_id)
        return _wrap(PARTS[part](conn, chem_id))


# ---- 코드 기준정보 ----

@app.get("/codes/ghs-class/{code}")
def get_class_code(code: str):
    with _conn() as conn:
        return _wrap(repo.class_codes(conn, [code])[code])


@app.get("/codes/h/{code}")
def get_h_code(code: str):
    with _conn() as conn:
        return _wrap(repo.h_code(conn, code))


@app.get("/codes/div/{code}")
def get_div_code(code: str):
    with _conn() as conn:
        return _wrap(repo.div_codes(conn, [code])[code])


@app.get("/codes/property/{code}")
def get_property_code(code: str):
    with _conn() as conn:
        return _wrap(repo.property_codes(conn, [code])[code])


@app.get("/codes/regulate-item/{code}")
def get_regulate_item(code: str):
    with _conn() as conn:
        return _wrap(repo.regulate_items(conn, [code])[code])


# ---- 추출 코드 → HTODB 코드 (13_TO21DB매핑) ----

@app.get("/mapping/hazard")
def map_hazard(class_code: str, category: str | None = None, route_form: str | None = None, effect: str | None = None):
    return _wrap(state["map"].hazard(class_code, category, route_form, effect))


MAP_KINDS = {"pictogram": "pictogram", "signal-word": "signal_word", "property": "property",
             "endpoint": "endpoint", "regulation": "regulation"}


@app.get("/mapping/{kind}/{code}")
def map_code(kind: str, code: str):
    if kind not in MAP_KINDS:
        raise HTTPException(404, f"알 수 없는 종류: {kind} (가능: hazard, {', '.join(MAP_KINDS)})")
    return _wrap(getattr(state["map"], MAP_KINDS[kind])(code))


# ---- 추출 JSON 한 건 → 코드별 HTODB 원본 ----

def _resolve(conn, m: Map13, site: dict) -> dict:
    kind, v = site["kind"], site["value"]
    if kind in ("cas", "ke", "un"):
        key = {"cas": normalize_cas, "ke": str, "un": normalize_un}[kind](v)
        found = repo.chemicals(conn, **{kind: key})
        out = {"lookup_key": key, "chemicals": found}
        if kind == "cas" and found["total"] == 1:   # 세부정보는 CAS로 한 물질이 찾아질 때만(KE 쪽과 중복 방지)
            out["details"] = repo.chemical_details(conn, found["rows"][0]["chem_id"])
        return out
    if kind == "h_code":
        return {"reference": repo.h_code(conn, v)}
    if kind == "hazard_class":
        mapped = m.hazard(v["class_code"], v["category"], v.get("route_form"), v.get("effect"))
        return {"mapping": mapped, "reference": repo.class_codes(conn, [x["class_result_code"] for x in mapped])}
    if kind in ("pictogram", "signal_word"):
        return {"mapping": getattr(m, kind)(v)}
    if kind == "property":
        mapped = m.property(v)
        return {"mapping": mapped, "reference": repo.property_codes(conn, [x["property_id"] for x in mapped])}
    if kind == "endpoint":
        mapped = m.endpoint(v)
        return {"mapping": mapped, "reference": repo.div_codes(conn, [c for x in mapped for c in x["div_codes"]])}
    if kind == "regulation":
        mapped = m.regulation(v)
        return {"mapping": mapped, "reference": repo.regulate_items(conn, [x["regulate_item_id"] for x in mapped])}
    raise AssertionError(kind)


@app.post("/lookup")
def lookup(doc: Annotated[dict, Body()]):
    """추출 JSON(TO21 스키마) 안의 코드마다 13_TO21DB매핑 번역 결과와 HTODB 원본 행을 돌려준다.
    mapping이 빈 목록이면 시트에 대응이 없다는 뜻이고, 그대로 비워 둔다(추측하지 않음)."""
    try:
        sites = code_sites(doc)
    except ValueError as e:
        raise HTTPException(422, f"추출 JSON 형식 오류: {e}") from e
    with _conn() as conn:
        return _wrap([{**s, **_resolve(conn, state["map"], s)} for s in sites])
