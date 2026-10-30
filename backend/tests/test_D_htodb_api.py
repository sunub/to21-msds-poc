"""지식DB 조회 API 통합 시험. 각자 적재한 로컬 PostgreSQL(deploy/htodb/README.md)에 붙는다. DB가 없으면 건너뛴다.

TO21 자료의 값은 시험 코드에 적지 않는다(D-47). 기대값은 실행 때 DB에서 직접 SQL로 읽어
'API가 원본 행을 그대로 돌려주는지'를 비교한다. 쓰기 확인은 항상 되돌리는 트랜잭션 안에서만 한다.
"""
from decimal import Decimal

import psycopg
import pytest
from psycopg.rows import dict_row

from msds.compliance.htodb import parsers
from msds.compliance.htodb.config import pg_kwargs
from msds.compliance.htodb.mapping import code_sites


def _db_up() -> bool:
    try:
        psycopg.connect(**pg_kwargs("reader"), connect_timeout=2).close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_up(), reason="지식DB(로컬 PostgreSQL) 없음: deploy/htodb/README.md")
T = "htodb"


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from msds.api.htodb_app import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def db():
    with psycopg.connect(**pg_kwargs("reader"), row_factory=dict_row) as conn:
        yield conn


def sql(db, query, params=()):
    return [{k: str(v) if isinstance(v, Decimal) else v for k, v in r.items()} for r in db.execute(query, params).fetchall()]


def one(db, query, params=()):
    rows = sql(db, query, params)
    if not rows:
        pytest.skip(f"조건에 맞는 행이 없음: {query}")
    return rows[0]


def data(resp, status=200):
    assert resp.status_code == status, resp.text
    return resp.json()["data"]


def same_rows(a, b):
    key = lambda r: repr(sorted(r.items()))
    return sorted(a, key=key) == sorted(b, key=key)


@pytest.fixture(scope="module")
def chem(db):
    """분류·독성·물성·규제·노출기준이 모두 있는 물질 하나."""
    return one(db, f"""SELECT * FROM {T}.tb_eng_chem_master_info c WHERE cas_no IS NOT NULL
        AND EXISTS (SELECT 1 FROM {T}.tb_ghs_chem_class_map x WHERE x.chem_id = c.chem_id)
        AND EXISTS (SELECT 1 FROM {T}.tb_eng_chem_toxicity_test_info x WHERE x.chem_id = c.chem_id)
        AND EXISTS (SELECT 1 FROM {T}.tb_eng_chem_phy_property_map x WHERE x.chem_id = c.chem_id)
        AND EXISTS (SELECT 1 FROM {T}.tb_eng_reg_notice_std x WHERE x.chem_id = c.chem_id)
        AND EXISTS (SELECT 1 FROM {T}.tb_eng_form_exposure_info x WHERE x.chem_id = c.chem_id)
        ORDER BY chem_id LIMIT 1""")


def test_health_versions(client, db):
    body = client.get("/health").json()
    kv = {r["knowledge_version"] for r in sql(db, f"SELECT knowledge_version FROM {T}.load_log")}
    mv = {r["map_version"] for r in sql(db, "SELECT map_version FROM htodb_map.load_log")}
    assert body["status"] == "ok" and {body["knowledge_version"]} == kv and {body["map_version"]} == mv


def test_chemical_rows_are_raw(client, db, chem):
    assert data(client.get(f"/chemicals/{chem['chem_id']}")) == chem
    padded = one(db, f"SELECT * FROM {T}.tb_eng_chem_master_info WHERE ec_no <> btrim(ec_no) LIMIT 1")
    assert data(client.get(f"/chemicals/{padded['chem_id']}"))["ec_no"] == padded["ec_no"]   # 끝 공백 그대로


def test_chemical_keys(client, db, chem):
    cas = chem["cas_no"]
    messy = " " + cas.replace("-", "－") + " "
    assert [r["chem_id"] for r in data(client.get("/chemicals", params={"cas": messy}))["rows"]] == [chem["chem_id"]]
    prefix = cas[:-2]
    n = len(sql(db, f"SELECT 1 FROM {T}.tb_eng_chem_master_info WHERE cas_no = %s", (prefix,)))
    assert data(client.get("/chemicals", params={"cas": prefix}))["total"] == n           # 앞부분 일치로 찾지 않음
    un_row = one(db, f"SELECT un_no FROM {T}.tb_eng_chem_master_info WHERE un_no ~ '^UN[0-9]{{4}} +$' LIMIT 1")
    digits = un_row["un_no"].strip()[2:]
    n_un = len(sql(db, f"SELECT 1 FROM {T}.tb_eng_chem_master_info WHERE btrim(un_no) = %s", ("UN" + digits,)))
    a, b = data(client.get("/chemicals", params={"un": "UN" + digits})), data(client.get("/chemicals", params={"un": digits}))
    assert a == b and a["total"] == n_un > 0


def test_chemical_query_errors(client):
    assert client.get("/chemicals").status_code == 422
    assert client.get("/chemicals", params={"cas": "1-1-1", "ke": "x"}).status_code == 422
    assert data(client.get("/chemicals", params={"cas": ""}))["total"] == 0
    assert data(client.get("/chemicals", params={"un": ""}))["total"] == 0
    assert client.get("/chemicals/NO-SUCH-ID").status_code == 404
    assert client.get("/chemicals/NO-SUCH-ID/classifications").status_code == 404


PARTS = {  # 엔드포인트 → (테이블, 기준정보 사전 키 컬럼)
    "classifications": ("tb_ghs_chem_class_map", "class_result_code"),
    "toxicity": ("tb_eng_chem_toxicity_test_info", "div_code"),
    "physical-properties": ("tb_eng_chem_phy_property_map", "property_id"),
    "exposure-limits": ("tb_eng_form_exposure_info", None),
}


@pytest.mark.parametrize("part", PARTS)
def test_chemical_parts_equal_sql(client, db, chem, part):
    table, code_col = PARTS[part]
    d = data(client.get(f"/chemicals/{chem['chem_id']}/{part}"))
    expected = sql(db, f"SELECT * FROM {T}.{table} WHERE chem_id = %s", (chem["chem_id"],))
    assert expected and same_rows(d["rows"], expected)
    if code_col:
        assert set(d["codes"]) == {r[code_col] for r in expected}
    assert client.get(f"/chemicals/{chem['chem_id']}/no-such-part").status_code == 404


@pytest.mark.parametrize("part", ["toxicity", "physical-properties"])
def test_parsed_keeps_raw_rows(client, chem, part):
    raw = data(client.get(f"/chemicals/{chem['chem_id']}/{part}"))
    d = data(client.get(f"/chemicals/{chem['chem_id']}/{part}", params={"parsed": "true"}))
    assert "parsed" not in raw and d["rows"] == raw["rows"] and d["codes"] == raw["codes"]   # 원본은 그대로
    assert len(d["parsed"]) == len(d["rows"])
    assert all(x is None or set(x) == {"rule", "result"} for x in d["parsed"])
    assert client.get(f"/chemicals/{chem['chem_id']}/regulations", params={"parsed": "true"}).status_code == 422


PARSE_RULES = {  # 규칙 → (엔드포인트, 테이블, 규칙을 고르는 컬럼, 그 컬럼 값들)
    "acute": ("toxicity", "tb_eng_chem_toxicity_test_info", "div_code", sorted(parsers.ACUTE_DIVS)),
    "aquatic_acute": ("toxicity", "tb_eng_chem_toxicity_test_info", "div_code", sorted(parsers.AQUATIC_ACUTE_DIVS)),
    "aquatic_chronic_noec": ("toxicity", "tb_eng_chem_toxicity_test_info", "div_code", sorted(parsers.AQUATIC_CHRONIC_DIVS)),
    "rapid_degradability": ("toxicity", "tb_eng_chem_toxicity_test_info", "div_code", [parsers.RAPID_DIV]),
    **{name: ("physical-properties", "tb_eng_chem_phy_property_map", "property_id", [pid])
       for pid, name in parsers.PHYS_IDS.items()},
}


def _expected_parsed(part, rows, chem_row):
    if part == "toxicity":
        mw = parsers.to_float(chem_row["molecular_weight"])
        return [parsers.parse_toxicity_row(r, mw) for r in rows]
    return [parsers.parse_property_row(r) for r in rows]


@pytest.mark.parametrize("rule", PARSE_RULES)
def test_parsed_matches_parsers_per_rule(client, db, rule):
    """규칙마다 그 규칙이 값을 뽑아내는 행을 가진 물질을 골라, API의 parsed가 행마다 parsers 결과와 같은지 본다."""
    part, table, col, keys = PARSE_RULES[rule]
    cands = sql(db, f"SELECT DISTINCT chem_id FROM {T}.{table} WHERE {col} = ANY(%s) ORDER BY chem_id LIMIT 50", (keys,))
    for c in cands:
        d = data(client.get(f"/chemicals/{c['chem_id']}/{part}", params={"parsed": "true"}))
        hit = [x for x in d["parsed"] if x and x["rule"] == rule and x["result"] is not None]
        if hit:
            break
    else:
        pytest.skip(f"{rule}: 값이 뽑히는 행을 가진 물질이 없음")
    chem_row = sql(db, f"SELECT * FROM {T}.tb_eng_chem_master_info WHERE chem_id = %s", (c["chem_id"],))[0]
    assert d["parsed"] == _expected_parsed(part, d["rows"], chem_row)                    # 행 순서까지 맞물림
    assert same_rows(d["rows"], sql(db, f"SELECT * FROM {T}.{table} WHERE chem_id = %s", (c["chem_id"],)))


def test_parsed_uses_molecular_weight(client, db):
    """흡입(증기) ppm 값은 물질의 분자량으로 mg/L 환산된다(parse_acute)."""
    row = one(db, f"""SELECT t.chem_id FROM {T}.tb_eng_chem_toxicity_test_info t
        JOIN {T}.tb_eng_chem_master_info c USING (chem_id)
        WHERE t.div_code IN ('GHS0204', 'GHS0205') AND coalesce(t.primary_value, '') = ''
          AND t.primary_value_text ~ '(LC50|ATE)\\s*[=<>]?\\s*[0-9.,]+\\s*ppm'
          AND c.molecular_weight ~ '^[0-9]+(\\.[0-9]+)?$' ORDER BY t.chem_id LIMIT 1""")
    d = data(client.get(f"/chemicals/{row['chem_id']}/toxicity", params={"parsed": "true"}))
    assert any(x and x["rule"] == "acute" and x["result"] and "ppm→mg/L" in x["result"]["basis"] for x in d["parsed"])


def test_regulations_equal_sql(client, db, chem):
    d = data(client.get(f"/chemicals/{chem['chem_id']}/regulations"))
    for key, table in (("rows", "tb_eng_regula_chem_map"), ("notice_std", "tb_eng_reg_notice_std"),
                       ("notice_content", "tb_eng_reg_notice_content")):
        assert same_rows(d[key], sql(db, f"SELECT * FROM {T}.{table} WHERE chem_id = %s", (chem["chem_id"],))), key
    used = {(r["regulate_id"], r["regulate_item_id"], r["notice_seq"]) for r in d["notice_std"] + d["notice_content"]}
    assert used and {(n["regulate_id"], n["regulate_item_id"], n["notice_seq"]) for n in d["notices"]} == used
    for item_id, info in d["codes"].items():
        assert info["regulate_item"] and all(r["regulate_item_id"] == item_id for r in info["regulate_item"])
        assert {l["regulate_id"] for l in info["regulate"]} == {r["regulate_id"] for r in info["regulate_item"]}


def test_scale_and_newlines_kept(client, db):
    num = one(db, f"SELECT chem_id, std_value_primary FROM {T}.tb_eng_reg_notice_std "
                  "WHERE std_value_primary::text ~ '\\.[0-9]*0$' LIMIT 1")
    std = data(client.get(f"/chemicals/{num['chem_id']}/regulations"))["notice_std"]
    assert num["std_value_primary"] in [r["std_value_primary"] for r in std]               # 끝자리 0까지 문자열로
    nl = one(db, f"SELECT chem_id, apply_basis FROM {T}.tb_eng_reg_notice_content WHERE strpos(apply_basis, chr(10)) > 0 LIMIT 1")
    content = data(client.get(f"/chemicals/{nl['chem_id']}/regulations"))["notice_content"]
    assert nl["apply_basis"] in [r["apply_basis"] for r in content]                        # 줄바꿈 그대로


def test_code_dictionaries(client, db, chem):
    code = sql(db, f"SELECT class_result_code FROM {T}.tb_ghs_chem_class_map WHERE chem_id = %s LIMIT 1", (chem["chem_id"],))[0]["class_result_code"]
    d = data(client.get(f"/codes/ghs-class/{code}"))
    assert same_rows(d["class_master"], sql(db, f"SELECT * FROM {T}.tb_ghs_class_master_lang WHERE class_result_code = %s", (code,)))
    assert same_rows(d["hcode_phrase"], sql(db, f"SELECT * FROM {T}.tb_ghs_hcode_phrase WHERE class_result_code = %s", (code,)))
    assert same_rows(d["hcode_phrase_lang"], sql(db, f"SELECT * FROM {T}.tb_ghs_hcode_phrase_lang WHERE class_result_code = %s", (code,)))
    h = one(db, f"SELECT p.h_code FROM {T}.tb_ghs_hcode_phrase p JOIN {T}.tb_ghs_hcode_phrase_lang l "
                "USING (class_result_code, hcode_seq) LIMIT 1")["h_code"]
    dh = data(client.get(f"/codes/h/{h}"))
    assert same_rows(dh["hcode_phrase"], sql(db, f"SELECT * FROM {T}.tb_ghs_hcode_phrase WHERE h_code = %s", (h,)))
    assert dh["hcode_phrase_lang"] and dh["class_master"]
    for path, table, col in (("div", "tb_ghs_div_master", "div_code"), ("property", "tb_eng_physical_property_lang", "property_id"),
                             ("regulate-item", "tb_eng_regulate_item_lang", "regulate_item_id")):
        v = one(db, f"SELECT {col} FROM {T}.{table} LIMIT 1")[col]
        got = data(client.get(f"/codes/{path}/{v}"))
        rows = got["regulate_item"] if path == "regulate-item" else got
        assert same_rows(rows, sql(db, f"SELECT * FROM {T}.{table} WHERE {col} = %s", (v,))), path
    assert data(client.get("/codes/ghs-class/NO-SUCH")) == {"class_master": [], "hcode_phrase": [], "hcode_phrase_lang": []}


def test_mapping_endpoints_follow_sheet(client, db):
    from msds.api.htodb_app import state
    m = state["map"]
    r = m.hazard_rows[0]
    got = data(client.get("/mapping/hazard", params={k: v for k, v in zip(
        ("class_code", "category", "route_form", "effect"), (r["c1"], r["c2"], r["c3"] or None, r["c4"] or None)) if v}))
    assert [x["sheet_row"] for x in got] == [r["sheet_row"]]
    for kind, rows, attr in (("pictogram", m.pictogram_rows, "pictogram"), ("endpoint", m.endpoint_rows, "endpoint"),
                             ("regulation", m.regulation_rows, "regulation")):
        assert data(client.get(f"/mapping/{kind}/{rows[0]['c1']}")) == getattr(m, attr)(rows[0]["c1"])
    assert data(client.get("/mapping/regulation/NO-SUCH")) == []
    assert client.get("/mapping/no-such-kind/X").status_code == 404
    loaded = sql(db, "SELECT * FROM htodb_map.sheet13 ORDER BY sheet_row")
    assert [x["sheet_row"] for x in loaded] and len(m.hazard_rows) > 0


def _synthetic_doc(chem, m):
    """DB·시트에서 읽은 값으로 추출 JSON 한 건을 만든다(코드에 TO21 값을 적지 않으려고)."""
    h = m.hazard_rows[0]
    return {"msds": [{
        "components": [{"seq": 1, "cas_no": chem["cas_no"], "ke_no": chem["ke_no"]}],
        "hazard": {"classes": [{"class_code": h["c1"], "category": h["c2"], "route_form": h["c3"] or None, "effect": h["c4"] or None}],
                   "pictograms": [{"code": m.pictogram_rows[0]["c1"]}], "signal_word": m.signal_rows[0]["c5"]},
        "physchem": [{"prop_code": m.property_rows[0]["c1"].split("·")[0].strip(), "comp_ref": "MIX"}],
        "toxicity": [{"endpoint": m.endpoint_rows[0]["c1"], "comp_ref": "1"}],
        "regulations": [{"item_code": m.regulation_rows[0]["c1"], "comp_ref": "1"}, {"item_code": "NO-SUCH", "comp_ref": "1"}],
    }]}


def test_lookup(client, chem):
    from msds.api.htodb_app import state
    m = state["map"]
    doc = _synthetic_doc(chem, m)
    sites = data(client.post("/lookup", json=doc))
    assert [(s["path"], s["kind"]) for s in sites] == [(s["path"], s["kind"]) for s in code_sites(doc)]
    by = {s["path"]: s for s in sites}
    cas = by["msds[0].components[0].cas_no"]
    assert cas["chemicals"]["rows"][0]["chem_id"] == chem["chem_id"] and cas["details"]["classifications"]["rows"]
    if chem["ke_no"]:
        assert "details" not in by["msds[0].components[0].ke_no"]          # 세부정보는 CAS 쪽에만
    hz = by["msds[0].hazard.classes[0]"]
    assert hz["mapping"] == m.hazard(**doc["msds"][0]["hazard"]["classes"][0])
    assert set(hz["reference"]) == {x["class_result_code"] for x in hz["mapping"]}
    assert by["msds[0].hazard.pictograms[0].code"]["mapping"] and by["msds[0].hazard.signal_word"]["mapping"]
    assert by["msds[0].toxicity[0].endpoint"]["reference"] and by["msds[0].regulations[0].item_code"]["reference"]
    assert by["msds[0].regulations[1].item_code"]["mapping"] == []           # 시트에 없으면 빈 목록


def test_lookup_example(client, gold25):
    assert len(data(client.post("/lookup", json=gold25))) == len(code_sites(gold25))


def test_lookup_no_details_when_cas_ambiguous(client, chem, monkeypatch):
    from msds.compliance.htodb import repo
    monkeypatch.setattr(repo, "chemicals", lambda conn, **kw: {"total": 2, "rows": [{"chem_id": chem["chem_id"]}, {"chem_id": "X"}]})
    sites = data(client.post("/lookup", json={"msds": [{"components": [{"seq": 1, "cas_no": chem["cas_no"]}]}]}))
    assert sites[0]["chemicals"]["total"] == 2 and "details" not in sites[0]


@pytest.mark.parametrize("body", [{"doc": {}}, {"msds": [1]}, {"msds": [{"hazard": "x"}]},
                                  {"msds": [{"components": [{"cas_no": 123}]}]}, [1, 2]])
def test_lookup_rejects_malformed(client, body):
    assert client.post("/lookup", json=body).status_code == 422


def test_api_cannot_write(client):
    from msds.api.htodb_app import state
    with state["pool"].connection() as conn:
        who = conn.execute("SELECT current_user AS u, current_setting('transaction_read_only') AS ro, "
                           "(SELECT rolsuper FROM pg_roles WHERE rolname = current_user) AS su").fetchone()
        assert who == {"u": "kdb_reader", "ro": "on", "su": False}
        with pytest.raises((psycopg.errors.ReadOnlySqlTransaction, psycopg.errors.InsufficientPrivilege)):
            with conn.transaction(force_rollback=True):
                conn.execute(f"UPDATE {T}.tb_ghs_div_master SET div_name = div_name WHERE false")
