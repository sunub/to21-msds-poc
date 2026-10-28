"""extract/nuextract.py 시험. 응답 예는 직접 만든 가짜 값이다 (D-43)."""
import copy
import json

import pytest

from msds.common.schema import validate
from msds.extract import nuextract as nx
from msds.extract import section_specs as ss

NOS = range(1, 17)
LEAF_STR = {"verbatim-string", "string", "number", "integer"}
BANNED_KEYS = {"$ref", "anyOf", "$defs", "description"}


def leaves(t):
    """틀의 잎: 문자열이거나 문자열 목록(선택지). 나머지는 dict·list를 따라 내려간다."""
    if isinstance(t, dict):
        for v in t.values():
            yield from leaves(v)
    elif isinstance(t, list) and t and all(isinstance(x, str) for x in t):
        yield t
    elif isinstance(t, list):
        for v in t:
            yield from leaves(v)
    else:
        yield t


def keys(t):
    if isinstance(t, dict):
        for k, v in t.items():
            yield k
            yield from keys(v)
    elif isinstance(t, list):
        for v in t:
            yield from keys(v)


def empty_like(t):
    """틀 모양의 빈 응답: 문자열·선택지 자리는 null, 배열은 []."""
    if isinstance(t, dict):
        return {k: empty_like(v) for k, v in t.items()}
    if isinstance(t, list):
        return []
    return None


@pytest.mark.parametrize("no", NOS)
def test_template_is_plain_json_template(no):
    t = nx.template(ss.response_schema(no))
    json.dumps(t)
    assert not BANNED_KEYS & set(keys(t))
    for leaf in leaves(t):
        if isinstance(leaf, str):
            assert leaf in LEAF_STR, leaf
        else:
            assert all(isinstance(x, str) for x in leaf)


def test_template_section3():
    t = nx.template(ss.response_schema(3))
    assert list(t) == list(ss.response_schema(3)["properties"])
    assert isinstance(t["components"], list) and len(t["components"]) == 1
    row = t["components"][0]
    assert isinstance(row, dict)
    assert row["line"] == "verbatim-string"
    assert row["content"]["raw"] == "verbatim-string"
    assert row["content"]["value"] == "number"
    assert row["content"]["approx"] == ["true", "false"]
    assert row["content"]["lower_op"] == [">", ">="]
    assert t["composition"]["type"] == ["단일물질", "혼합물"]
    assert t["composition"]["lines"]["type"] == "verbatim-string"
    assert row["name"] == "string"


def test_template_section4_narratives():
    t = nx.template(ss.response_schema(4))
    n = t["narratives"][0]
    assert n["item_code"] == list(ss.load_specs()[4].narrative_codes)
    assert n["start"] == "verbatim-string" and n["end"] == "verbatim-string"


def test_template_keeps_property_order_and_drops_null_enum():
    schema = {"type": "object", "properties": {
        "b": {"anyOf": [{"type": "string", "enum": ["x", "y", None]}, {"type": "null"}]},
        "a": {"type": "integer"}}}
    assert list(nx.template(schema)) == ["b", "a"]
    assert nx.template(schema) == {"b": ["x", "y"], "a": "integer"}


def test_template_follows_ref_inside_array():
    schema = {"$defs": {"Q": {"type": "object", "properties": {"raw": {"type": "string"}, "n": {"type": "number"}}}},
              "type": "object",
              "properties": {"q": {"anyOf": [{"$ref": "#/$defs/Q"}, {"type": "null"}]},
                             "qs": {"type": "array", "items": {"$ref": "#/$defs/Q"}}}}
    t = nx.template(schema)
    assert t == {"q": {"raw": "verbatim-string", "n": "number"}, "qs": [{"raw": "verbatim-string", "n": "number"}]}


def test_template_rejects_multi_type_anyof():
    schema = {"type": "object", "properties": {"a": {"anyOf": [{"type": "string"}, {"type": "number"}]}}}
    with pytest.raises(ValueError):
        nx.template(schema)


# ── coerce ─────────────────────────────────────────────

@pytest.mark.parametrize("no", NOS)
def test_coerce_empty_inputs_validate(no):
    s = ss.response_schema(no)
    assert validate(nx.coerce({}, s), s) == []
    assert validate(nx.coerce(empty_like(nx.template(s)), s), s) == []
    assert validate(nx.coerce(None, s), s) == []


def section3():
    return {
        "composition": {"type": "혼합물", "lines": {"type": "p1:L5"}},
        "components": [
            {"name": "가상물질 갑", "cas_no": "1234-56-6",
             "content": {"raw": "10 ~ 20", "value": "12.5", "approx": "TRUE", "lower_op": ">=", "lower": 10},
             "line": "p1:L9", "junk": "x"},
            {"name": "줄 없는 물질", "cas_no": None, "line": None},
        ],
        "no_hazardous_component": "TRUE",
        "extras": [],
        "unknown_top": 1,
    }


def test_coerce_section3():
    s = ss.response_schema(3)
    src = section3()
    before = copy.deepcopy(src)
    out = nx.coerce(src, s)
    assert src == before
    assert validate(out, s) == []
    assert "unknown_top" not in out
    assert [c["line"] for c in out["components"]] == ["p1:L9"]
    assert "junk" not in out["components"][0]
    content = out["components"][0]["content"]
    assert content["value"] == 12.5 and content["approx"] is True and content["lower"] == 10
    assert out["composition"]["type"] == "혼합물"


def test_coerce_scalars():
    s = {"type": "object", "properties": {
        "flag": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
        "num": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "int": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "txt": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "kind": {"anyOf": [{"type": "string", "enum": ["단일물질", "혼합물"]}, {"type": "null"}]}}}
    f = lambda **kw: nx.coerce(kw, s)
    assert f(flag="TRUE")["flag"] is True
    assert f(flag=" false ")["flag"] is False
    assert f(flag="maybe")["flag"] is None
    assert f(flag=True)["flag"] is True
    assert f(num="12.5")["num"] == 12.5
    assert f(num=" 7 ")["num"] == 7
    assert f(num="abc")["num"] is None
    assert f(num=True)["num"] is None
    assert f(int="3")["int"] == 3 and isinstance(f(int="3")["int"], int)
    assert f(int=3.0)["int"] == 3 and isinstance(f(int=3.0)["int"], int)
    assert f(int="3.5")["int"] is None
    assert f(txt=12)["txt"] == "12"
    assert f(txt=["a"])["txt"] is None
    assert f(kind="기타")["kind"] is None
    assert f(kind="혼합물")["kind"] == "혼합물"
    assert validate(f(flag="x", num="y", int="z", txt=None, kind="q"), s) == []


def test_coerce_components_not_list():
    s = ss.response_schema(3)
    out = nx.coerce({"components": "없음"}, s)
    assert out["components"] == []
    assert validate(out, s) == []


def test_coerce_nullable_object_collapses_to_null():
    s = ss.response_schema(9)
    ex = {"physchem": [{"prop_code": "FLASH_POINT", "q": {"raw": "60 ℃", "value": "60", "unit": "℃"},
                        "cond": {"method": None}, "line": "p4:L20"}], "extras": []}
    out = nx.coerce(ex, s)
    assert validate(out, s) == []
    row = out["physchem"][0]
    assert row["cond"] is None
    assert row["q"]["value"] == 60
    assert nx.coerce({"physchem": [{"prop_code": "FLASH_POINT", "q": None, "cond": None, "line": "p4:L20"}]}, s)[
        "physchem"][0]["q"] is None


def test_coerce_narrative_row_without_required_is_dropped():
    s = ss.response_schema(4)
    code = ss.load_specs()[4].narrative_codes[0]
    ex = {"narratives": [
        {"item_code": code, "title_raw": "가상 소제목", "start": "p3:L2", "end": "p3:L4"},
        {"item_code": code, "title_raw": "끝 없음", "start": "p3:L6", "end": None},
        {"item_code": "S4_없는코드", "title_raw": "x", "start": "p3:L7", "end": "p3:L8"}],
        "extras": []}
    out = nx.coerce(ex, s)
    assert [n["start"] for n in out["narratives"]] == ["p3:L2"]
    assert validate(out, s) == []
