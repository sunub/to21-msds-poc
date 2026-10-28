"""HTODB 원본 조회. 모든 쿼리는 읽기 전용 연결에서 원본 테이블을 그대로 읽는다.

값은 바꾸지 않는다. 예외는 JSON 직렬화 하나: numeric(Decimal)은 소수 자릿수를 지키려고 문자열로 돌려준다.
행끼리 조인해 붙이지 않고 '원본 행 목록 + 그 행이 쓰는 코드의 기준정보 사전'으로 나눠 돌려준다(원본 행 모양 보존).
"""
from __future__ import annotations

from decimal import Decimal

from psycopg import Connection

S = "htodb"


def _clean(rows: list[dict]) -> list[dict]:
    return [{k: (str(v) if isinstance(v, Decimal) else v) for k, v in r.items()} for r in rows]


def _all(conn: Connection, query: str, params=()) -> list[dict]:
    return _clean(conn.execute(query, params).fetchall())


def _by_key(rows: list[dict], key: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r[key], []).append(r)
    return out


def versions(conn: Connection) -> dict:
    kv = conn.execute(f"SELECT DISTINCT knowledge_version FROM {S}.load_log").fetchall()
    mv = conn.execute("SELECT map_version FROM htodb_map.load_log").fetchall()
    return {"knowledge_version": kv[0]["knowledge_version"] if len(kv) == 1 else None,
            "map_version": mv[0]["map_version"] if len(mv) == 1 else None}


# ---- 물질 ----

def chemicals(conn: Connection, *, cas: str | None = None, ke: str | None = None, un: str | None = None,
              limit: int = 50) -> dict:
    """키 비교는 13_TO21DB매핑 A묶음 규칙을 따른다. DB 값은 바꾸지 않고 비교식에서만 맞춘다."""
    if cas is not None:
        where, p = "cas_no = %s", cas
    elif ke is not None:
        where, p = "ke_no = %s", ke
    elif un is not None:
        where, p = "regexp_replace(btrim(un_no), '^UN', '') = %s", un
    else:
        raise ValueError("cas, ke, un 중 하나가 필요함")
    total = conn.execute(f"SELECT count(*) AS n FROM {S}.tb_eng_chem_master_info WHERE {where}", (p,)).fetchone()["n"]
    rows = _all(conn, f"SELECT * FROM {S}.tb_eng_chem_master_info WHERE {where} ORDER BY chem_id LIMIT %s", (p, limit))
    return {"total": total, "rows": rows}


def chemical(conn: Connection, chem_id: str) -> dict | None:
    rows = _all(conn, f"SELECT * FROM {S}.tb_eng_chem_master_info WHERE chem_id = %s", (chem_id,))
    return rows[0] if rows else None


def classifications(conn: Connection, chem_id: str) -> dict:
    rows = _all(conn, f"SELECT * FROM {S}.tb_ghs_chem_class_map WHERE chem_id = %s "
                      "ORDER BY class_source_db_code, class_result_code, hcode_seq", (chem_id,))
    return {"rows": rows, "codes": class_codes(conn, sorted({r["class_result_code"] for r in rows}))}


def toxicity(conn: Connection, chem_id: str) -> dict:
    rows = _all(conn, f"SELECT * FROM {S}.tb_eng_chem_toxicity_test_info WHERE chem_id = %s "
                      "ORDER BY experiment_div, div_code, toxic_seq", (chem_id,))
    return {"rows": rows, "codes": div_codes(conn, sorted({r["div_code"] for r in rows}))}


def physical_properties(conn: Connection, chem_id: str) -> dict:
    rows = _all(conn, f"SELECT * FROM {S}.tb_eng_chem_phy_property_map WHERE chem_id = %s "
                      "ORDER BY property_id, property_seq", (chem_id,))
    return {"rows": rows, "codes": property_codes(conn, sorted({r["property_id"] for r in rows}))}


def regulations(conn: Connection, chem_id: str) -> dict:
    """물질↔규제 항목(REGULA_CHEM_MAP)과 그 물질의 고시 수치(STD)·조문(CONTENT), 쓰인 고시·법·항목 사전."""
    rows = _all(conn, f"SELECT * FROM {S}.tb_eng_regula_chem_map WHERE chem_id = %s "
                      "ORDER BY regulate_id, regulate_item_id", (chem_id,))
    std = _all(conn, f"SELECT * FROM {S}.tb_eng_reg_notice_std WHERE chem_id = %s "
                     "ORDER BY regulate_item_id, notice_seq, std_seq", (chem_id,))
    content = _all(conn, f"SELECT * FROM {S}.tb_eng_reg_notice_content WHERE chem_id = %s "
                         "ORDER BY regulate_item_id, notice_seq, lang_code", (chem_id,))
    notices = sorted({(r["regulate_id"], r["regulate_item_id"], r["notice_seq"]) for r in std + content})
    notice_rows = []
    for key in notices:
        notice_rows += _all(conn, f"SELECT * FROM {S}.tb_eng_reg_notice_info "
                                  "WHERE regulate_id = %s AND regulate_item_id = %s AND notice_seq = %s", key)
    item_ids = sorted({r["regulate_item_id"] for r in rows + std + content})
    return {"rows": rows, "notice_std": std, "notice_content": content, "notices": notice_rows,
            "codes": regulate_items(conn, item_ids)}


def exposure_limits(conn: Connection, chem_id: str) -> dict:
    """8항 노출기준 출처 테이블(TO21 테이블설명 참고)."""
    return {"rows": _all(conn, f"SELECT * FROM {S}.tb_eng_form_exposure_info WHERE chem_id = %s "
                               "ORDER BY regulate_item_id, notice_seq, exposure_form, exposure_limit_code", (chem_id,))}


def chemical_details(conn: Connection, chem_id: str) -> dict:
    return {"classifications": classifications(conn, chem_id), "toxicity": toxicity(conn, chem_id),
            "physical_properties": physical_properties(conn, chem_id), "regulations": regulations(conn, chem_id),
            "exposure_limits": exposure_limits(conn, chem_id)}


# ---- 코드 기준정보 사전 ----

def class_codes(conn: Connection, codes: list[str]) -> dict:
    """CLASS_RESULT_CODE → 항목·구분 이름, H코드·신호어·그림문자, H문구."""
    master = _all(conn, f"SELECT * FROM {S}.tb_ghs_class_master_lang WHERE class_result_code = ANY(%s) "
                        "ORDER BY class_result_code", (codes,))
    phrase = _all(conn, f"SELECT * FROM {S}.tb_ghs_hcode_phrase WHERE class_result_code = ANY(%s) "
                        "ORDER BY class_result_code, hcode_seq", (codes,))
    lang = _all(conn, f"SELECT * FROM {S}.tb_ghs_hcode_phrase_lang WHERE class_result_code = ANY(%s) "
                      "ORDER BY class_result_code, hcode_seq", (codes,))
    m, p, l = _by_key(master, "class_result_code"), _by_key(phrase, "class_result_code"), _by_key(lang, "class_result_code")
    return {c: {"class_master": m.get(c, []), "hcode_phrase": p.get(c, []), "hcode_phrase_lang": l.get(c, [])} for c in codes}


def h_code(conn: Connection, code: str) -> dict:
    """H코드 하나가 여러 분류(CLASS_RESULT_CODE)에 쓰일 수 있어 목록으로 돌려준다."""
    phrase = _all(conn, f"SELECT * FROM {S}.tb_ghs_hcode_phrase WHERE h_code = %s ORDER BY class_result_code, hcode_seq", (code,))
    keys = [(r["class_result_code"], r["hcode_seq"]) for r in phrase]
    lang = []
    for c, seq in keys:
        lang += _all(conn, f"SELECT * FROM {S}.tb_ghs_hcode_phrase_lang WHERE class_result_code = %s AND hcode_seq = %s", (c, seq))
    master = _all(conn, f"SELECT * FROM {S}.tb_ghs_class_master_lang WHERE class_result_code = ANY(%s) "
                        "ORDER BY class_result_code", ([c for c, _ in keys],))
    return {"hcode_phrase": phrase, "hcode_phrase_lang": lang, "class_master": master}


def div_codes(conn: Connection, codes: list[str]) -> dict:
    rows = _by_key(_all(conn, f"SELECT * FROM {S}.tb_ghs_div_master WHERE div_code = ANY(%s)", (codes,)), "div_code")
    return {c: rows.get(c, []) for c in codes}


def property_codes(conn: Connection, codes: list[str]) -> dict:
    rows = _by_key(_all(conn, f"SELECT * FROM {S}.tb_eng_physical_property_lang WHERE property_id = ANY(%s)", (codes,)),
                   "property_id")
    return {c: rows.get(c, []) for c in codes}


def regulate_items(conn: Connection, item_ids: list[str]) -> dict:
    items = _by_key(_all(conn, f"SELECT * FROM {S}.tb_eng_regulate_item_lang WHERE regulate_item_id = ANY(%s)",
                         (item_ids,)), "regulate_item_id")
    law_ids = sorted({r["regulate_id"] for rows in items.values() for r in rows})
    laws = _by_key(_all(conn, f"SELECT * FROM {S}.tb_eng_regulate_lang WHERE regulate_id = ANY(%s)", (law_ids,)),
                   "regulate_id")
    return {i: {"regulate_item": items.get(i, []),
                "regulate": [l for r in items.get(i, []) for l in laws.get(r["regulate_id"], [])]} for i in item_ids}
