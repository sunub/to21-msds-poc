"""extract/section_specs.py 시험. TO21 스키마·명세서는 읽기만 하고, 응답 예는 직접 만든 가짜 값이다 (D-43)."""
import json
import re

import pytest
from jsonschema import Draft202012Validator

from msds.common.schema import msds_item_schema, to_strict, validate
from msds.extract import section_specs as ss

NOS = range(1, 17)
TABLE = {
    1: ("meta", "product", "companies"),
    2: ("hazard", "narratives"),
    3: ("composition", "components"),
    4: ("narratives",),
    5: ("narratives",),
    6: ("narratives",),
    7: ("narratives",),
    8: ("exposure_limits", "narratives"),
    9: ("physchem",),
    10: ("narratives",),
    11: ("toxicity", "cmr", "narratives"),
    12: ("ecotox", "narratives"),
    13: ("narratives",),
    14: ("transport", "narratives"),
    15: ("regulations", "dangerous_goods", "waste", "intl_class", "narratives"),
    16: ("narratives", "meta_revision"),
}
OBJECT_TARGETS = {"meta", "product", "hazard", "composition", "meta_revision"}


def nodes(node, path=""):
    """스키마의 모든 dict 조각을 (경로, 조각)으로 돌려준다."""
    if isinstance(node, dict):
        yield path, node
        for k, v in node.items():
            yield from nodes(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from nodes(v, f"{path}/{i}")


def resolve(schema, node):
    ref = node.get("$ref")
    return schema["$defs"][ref.rsplit("/", 1)[1]] if ref else node


def row_items(schema):
    """객체를 담는 배열의 항목 (경로, 항목 스키마). $ref는 푼다."""
    for path, n in nodes(schema):
        if n.get("type") == "array" and isinstance(n.get("items"), dict):
            item = resolve(schema, n["items"])
            if "properties" in item:
                yield path, item


def complete(inst, node, schema):
    """손으로 쓴 예에서 빠진 칸 중 null 허용 칸은 null, 배열 칸은 []로 채운다.

    null을 허용하지 않는 칸(line, start, end 등)은 채우지 않는다. 빠지면 검증에서 걸린다.
    스키마에 없는 칸(comp_ref, seq 등)은 지우지 않고 그대로 둔다. 있으면 검증에서 걸린다.
    """
    node = resolve(schema, node)
    if "anyOf" in node:
        if inst is None:
            return None
        branch = next(b for b in node["anyOf"] if b.get("type") != "null")
        return complete(inst, branch, schema)
    if node.get("type") == "array":
        return [complete(x, node["items"], schema) for x in inst]
    if node.get("type") == "object" and "properties" in node:
        out = {k: v for k, v in inst.items() if k not in node["properties"]}
        for k, sub in node["properties"].items():
            if k in inst:
                out[k] = complete(inst[k], sub, schema)
                continue
            sub = resolve(schema, sub)
            if any(b.get("type") == "null" for b in sub.get("anyOf", [])):
                out[k] = None
            elif sub.get("type") == "array":
                out[k] = []
            elif sub.get("type") == "object" and "properties" in sub:
                out[k] = complete({}, sub, schema)
        return out
    return inst


def narr(no, start, end):
    return {"item_code": ss.load_specs()[no].narrative_codes[0], "title_raw": "가상 소제목",
            "start": start, "end": end}


def example(no):
    """항마다 행 1개짜리 가짜 응답. 값은 지어낸 것이다."""
    comp = {"comp_name": "가상물질 갑", "comp_cas": "1234-56-7"}
    return {
        1: {"meta": {"revision_no": 3, "last_revision_date": "2024-05-01",
                     "lines": {"revision_no": "p1:L2", "last_revision_date": "p1:L2"}},
            "product": {"name": "가상 세정액 A", "uses": ["세척제"], "lines": {"name": "p1:L5", "uses": "p1:L6"}},
            "companies": [{"role": "제조자", "name": "가상화학",
                           "contacts": [{"type": "긴급", "value": "000-0000-0000", "line": "p1:L9"}],
                           "line": "p1:L8"}],
            "extras": []},
        2: {"hazard": {"classified": True, "signal_word": "경고",
                       "classes": [{"group": "건강", "class_code": "HH_EYE_DMG", "category": "2", "line": "p1:L20"}],
                       "h_statements": [{"code": "H319", "system": "GHS", "text": "가상 유해 문구", "line": "p1:L23"}],
                       "lines": {"classified": "p1:L19", "signal_word": "p1:L22"}},
            "narratives": [narr(2, "p1:L30", "p1:L31")], "extras": []},
        3: {"composition": {"type": "혼합물", "lines": {"type": "p2:L3"}},
            "components": [{"name": "가상물질 갑", "cas_no": "1234-56-7",
                            "content": {"raw": "10 ~ 20", "lower_op": ">=", "lower": 10,
                                        "upper_op": "<=", "upper": 20, "unit": "%"},
                            "line": "p2:L5"}],
            "extras": []},
        4: {"narratives": [narr(4, "p3:L2", "p3:L4")],
            "extras": [{"title_raw": "가상 추가 항목", "reason": "필드없음",
                        "statements": [{"value": "가상 문장", "line": "p3:L9"}], "line": "p3:L8"}]},
        5: {"narratives": [narr(5, "p3:L20", "p3:L22")], "extras": []},
        6: {"narratives": [narr(6, "p3:L30", "p3:L30")], "extras": []},
        7: {"narratives": [narr(7, "p3:L40", "p3:L41")], "extras": []},
        8: {"exposure_limits": [{**comp, "standard": "국내", "limit_type": "TWA",
                                 "q": {"raw": "1 ppm", "value": 1, "unit": "ppm"}, "line": "p4:L3"}],
            "narratives": [narr(8, "p4:L10", "p4:L12")], "extras": []},
        9: {"physchem": [{"prop_code": "FLASH_POINT", "q": {"raw": "60 ℃", "value": 60, "unit": "℃"},
                          "cond": {"method": "밀폐식"}, "line": "p4:L20"}],
            "extras": []},
        10: {"narratives": [narr(10, "p5:L1", "p5:L2")], "extras": []},
        11: {"toxicity": [{**comp, "endpoint": "TX_ORAL", "descriptor": "LD50", "species": "랫드",
                           "q": {"raw": "> 2000 mg/kg", "lower_op": ">", "lower": 2000, "unit": "mg/kg"},
                           "line": "p5:L4"}],
             "cmr": [{**comp, "hazard": "발암성", "agency": "IARC", "class": "3", "line": "p5:L10"}],
             "narratives": [narr(11, "p5:L12", "p5:L12")], "extras": []},
        12: {"ecotox": [{**comp, "endpoint": "ECO_FISH", "descriptor": "LC50",
                         "q": {"raw": "100 mg/L", "value": 100, "unit": "mg/L"},
                         "duration_value": 96, "duration_unit": "hr", "line": "p5:L30"}],
             "narratives": [narr(12, "p5:L35", "p5:L36")], "extras": []},
        13: {"narratives": [narr(13, "p6:L1", "p6:L3")], "extras": []},
        14: {"transport": [{"mode": "공통", "regulated": False, "line": "p6:L5"}],
             "narratives": [narr(14, "p6:L8", "p6:L8")], "extras": []},
        15: {"regulations": [{**comp, "law": "OSH", "item_code": "OSH_MEASURE", "applicable": "해당",
                              "line": "p6:L10"}],
             "dangerous_goods": [{"class": "제4류", "item": "가상 품명", "water_soluble": "비수용성", "line": "p6:L12"}],
             "waste": [{"designated": "비해당", "line": "p6:L14"}],
             "intl_class": [{"system": "EU_CLP", "class_raw": "가상 분류", "h_code": "H319", "line": "p6:L16"}],
             "narratives": [narr(15, "p6:L18", "p6:L19")], "extras": []},
        16: {"narratives": [narr(16, "p7:L1", "p7:L2")],
             "meta_revision": {"revision_no": 3, "last_revision_date": "2024-05-01",
                               "lines": {"revision_no": "p7:L3", "last_revision_date": "p7:L4"}},
             "extras": []},
    }[no]


# ── 항목과 대상 칸 ─────────────────────────────────────

def test_targets_follow_table():
    specs = ss.load_specs()
    assert sorted(specs) == list(NOS)
    for no in NOS:
        s = specs[no]
        assert s.no == no and s.title
        assert s.targets == tuple(t for t in TABLE[no] if t != "narratives" or s.narrative_codes), no
    # 지금 명세서에서 서술 코드가 없는 항은 1·3·9항뿐이다
    assert [no for no in NOS if not specs[no].narrative_codes] == [1, 3, 9]


def test_load_specs_is_cached():
    assert ss.load_specs() is ss.load_specs()


def test_narrative_codes_come_from_spec():
    specs = ss.load_specs()
    enum = msds_item_schema()["properties"]["narratives"]["items"]["properties"]["item_code"]["anyOf"][0]["enum"]
    codes = [c for s in specs.values() for c in s.narrative_codes]
    assert len(codes) == len(set(codes))
    assert set(codes) == set(enum)
    for s in specs.values():
        assert all(c.startswith(f"S{s.no}_") for c in s.narrative_codes), s.no


def test_every_to21_key_has_one_section():
    """코드 몫(evidence, validation)과 모든 항 공통(narratives, extras)을 뺀 TO21 키는 정확히 한 항이 맡는다."""
    specs = ss.load_specs()
    keys = set(msds_item_schema()["properties"]) - {"evidence", "validation", "narratives", "extras"}
    for k in keys:
        assert len([no for no in NOS if k in specs[no].targets]) == 1, k


# ── 중간 형식 스키마 ───────────────────────────────────

@pytest.mark.parametrize("no", NOS)
def test_schema_valid_before_and_after_strict(no):
    s = ss.response_schema(no)
    Draft202012Validator.check_schema(s)
    Draft202012Validator.check_schema(to_strict(s))
    assert list(s["properties"]) == [*ss.load_specs()[no].targets, "extras"]
    assert s["required"] == list(s["properties"])


@pytest.mark.parametrize("no", NOS)
def test_defs_hold_only_used_definitions(no):
    s = ss.response_schema(no)
    used = set(re.findall(r'"#/\$defs/(\w+)"', json.dumps(s)))
    assert set(s["$defs"]) == used
    assert used <= {"QM", "COND", "STMT"}


@pytest.mark.parametrize("no", NOS)
def test_rows_have_line(no):
    s = ss.response_schema(no)
    rows = list(row_items(s))
    assert rows
    for path, item in rows:
        props = item["properties"]
        if path == "/properties/narratives":
            assert list(props) == ["item_code", "title_raw", "start", "end"]
        else:
            assert props["line"] == {"type": "string", "description": props["line"]["description"]}, path
            assert "line" in item["required"], path
            assert "seq" not in props, path


@pytest.mark.parametrize("no", NOS)
def test_object_targets_have_lines(no):
    s = ss.response_schema(no)
    for t in ss.load_specs()[no].targets:
        node = s["properties"][t]
        if t in OBJECT_TARGETS:
            lines = node["properties"]["lines"]
            assert "lines" in node["required"]
            # 행 배열(자기 line이 있는 칸)을 뺀 모든 칸에 줄 번호 자리가 있다
            own = {k for k, v in node["properties"].items()
                   if v.get("type") == "array" and "line" in resolve(s, v["items"]).get("properties", {})}
            assert set(lines["properties"]) == set(node["properties"]) - own - {"lines"}, t
        else:
            assert node["type"] == "array", t


def test_qm_replaces_q():
    s = ss.response_schema(3)
    qm = s["$defs"]["QM"]
    assert tuple(qm["properties"]) == ss.QM_FIELDS
    assert "status" not in qm["properties"]
    for f, sub in qm["properties"].items():
        assert {"type": "null"} in sub["anyOf"], f
    for no in NOS:
        text = json.dumps(ss.response_schema(no))
        assert '"#/$defs/Q"' not in text, no


def test_comp_ref_becomes_name_and_cas():
    for no in NOS:
        for path, n in nodes(ss.response_schema(no)):
            assert "comp_ref" not in n.get("properties", {}), (no, path)
    for no, key in [(8, "exposure_limits"), (11, "toxicity"), (11, "cmr"), (12, "ecotox"),
                    (15, "regulations"), (15, "dangerous_goods"), (15, "waste"), (15, "intl_class")]:
        props = ss.response_schema(no)["properties"][key]["items"]["properties"]
        assert {"comp_name", "comp_cas"} <= set(props), key
        for f in ("comp_name", "comp_cas"):
            assert {"type": "null"} in props[f]["anyOf"]


def test_hazard_has_no_pictograms():
    hz = ss.response_schema(2)["properties"]["hazard"]["properties"]
    assert "pictograms" not in hz
    assert "pictograms" not in hz["lines"]["properties"]


def test_code_owned_fields_are_not_asked():
    co = ss.CODE_OWNED
    assert {"evidence", "validation"} <= co["msds"]
    assert "seq" in co["*"]
    assert "pictograms" in co["hazard"]
    assert {"status", "statements"} <= co["narratives"]
    for no in NOS:
        s = ss.response_schema(no)
        assert not co["msds"] & set(s["properties"]), no
        for key, node in s["properties"].items():
            props = node.get("properties") or node.get("items", {}).get("properties", {})
            assert not co.get(key, set()) & set(props), (no, key)
        if "STMT" in s["$defs"]:
            assert not (co["STMT"] | co["*"]) & set(s["$defs"]["STMT"]["properties"]), no


def test_extras_rows_drop_seq_and_page():
    item = ss.response_schema(4)["properties"]["extras"]["items"]["properties"]
    assert "seq" not in item and "page" not in item and "line" in item


def test_narratives_use_section_codes():
    specs = ss.load_specs()
    for no in NOS:
        if "narratives" not in specs[no].targets:
            continue
        item = ss.response_schema(no)["properties"]["narratives"]["items"]
        assert item["properties"]["item_code"]["enum"] == list(specs[no].narrative_codes)
        for f in ("item_code", "start", "end"):
            assert item["properties"][f]["type"] == "string" and f in item["required"]


def test_meta_revision_copies_to21_meta():
    mr = ss.response_schema(16)["properties"]["meta_revision"]
    meta = msds_item_schema()["properties"]["meta"]["properties"]
    assert list(mr["properties"]) == [*ss.META_REVISION_FIELDS, "lines"]
    assert list(mr["properties"]["lines"]["properties"]) == list(ss.META_REVISION_FIELDS)
    for f in ss.META_REVISION_FIELDS:
        assert mr["properties"][f] == ss._drop_value_checks(meta[f])


def test_response_schema_returns_fresh_copy():
    a = ss.response_schema(1)
    a["properties"]["companies"]["items"]["properties"]["line"]["type"] = "integer"
    assert ss.response_schema(1)["properties"]["companies"]["items"]["properties"]["line"]["type"] == "string"


@pytest.mark.parametrize("no", NOS)
def test_hand_made_example_passes(no):
    s = ss.response_schema(no)
    strict = to_strict(s)
    ex = complete(example(no), strict, strict)
    assert validate(ex, strict) == []
    assert validate(ex, s) == []


def test_example_missing_line_fails():
    strict = to_strict(ss.response_schema(14))
    ex = example(14)
    del ex["transport"][0]["line"]
    assert validate(complete(ex, strict, strict), strict)


@pytest.mark.parametrize("key, value", [("comp_ref", "1"), ("seq", 1)])
def test_example_with_code_owned_field_fails(key, value):
    strict = to_strict(ss.response_schema(8))
    ex = example(8)
    ex["exposure_limits"][0][key] = value
    assert validate(complete(ex, strict, strict), strict)


VALUE_CHECKS = {"pattern", "format", "minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems"}


@pytest.mark.parametrize("no", NOS)
def test_no_value_checks(no):
    """to_strict가 빼고 보내는 값 조건은 서버가 지키게 할 수 없으므로 항별 검증에서도 요구하지 않는다."""
    s = ss.response_schema(no)
    found = [f"{p}/{k}" for p, n in nodes(s) if not p.endswith("/properties") for k in n if k in VALUE_CHECKS]
    assert found == []


def test_format_stays_in_description():
    """모델은 설명에서 형식을 계속 본다."""
    ec = ss.response_schema(3)["properties"]["components"]["items"]["properties"]["ec_no"]
    to21_ec = msds_item_schema()["properties"]["components"]["items"]["properties"]["ec_no"]
    assert ec["description"] == to21_ec["description"]


@pytest.mark.parametrize("no, edit", [
    (3, lambda ex: ex["components"][0].update(ec_no="")),
    (2, lambda ex: ex["hazard"].update(nfpa={"health": 5})),
])
def test_bad_format_does_not_fail_section(no, edit):
    """형식이 틀린 칸 하나 때문에 항 전체를 잃지 않는다."""
    s = ss.response_schema(no)
    ex = example(no)
    edit(ex)
    assert validate(complete(ex, s, s), s) == []


def test_to21_schema_still_checks_format():
    """형식 검사는 펼친 뒤 TO21 원래 스키마(validate_to21)가 맡는다."""
    ec = msds_item_schema()["properties"]["components"]["items"]["properties"]["ec_no"]
    assert not Draft202012Validator(ec).is_valid("")


def test_print_schema_sizes(capsys):
    """항마다 구조화 출력에 보내는 스키마(to_strict 뒤) 크기. 실패 조건이 아니라 사람이 보는 기록이다."""
    sizes = {no: len(json.dumps(to_strict(ss.response_schema(no)), ensure_ascii=False)) for no in NOS}
    with capsys.disabled():
        print("\n[항별 중간 형식 스키마 크기, 글자] " + ", ".join(f"{no}항 {n:,}" for no, n in sizes.items()))
