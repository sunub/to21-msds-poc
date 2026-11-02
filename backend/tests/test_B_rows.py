"""extract/rows.py 시험. 행 글은 직접 만든 가짜 MSDS 값이다 (D-43). 모델 서버를 부르지 않는다."""
import re

import pytest

from msds.common.schema import validate
from msds.extract import rows as rw
from msds.extract.section_specs import response_schema

COMP = {"comp_name": "가상물질 갑", "comp_cas": "1234-56-6"}


def row(no: int, table: str, **values) -> str:
    """열 이름 → 값으로 행 한 줄을 만든다. 빠진 열은 빈 칸."""
    return " | ".join(str(values.get(c, "")) for c in rw.row_tables(no)[table])


def table(no: int, name: str, *lines: str) -> str:
    """'### 표 이름', 열 이름 줄, 행 줄."""
    return "\n".join([f"### {name}", " | ".join(rw.row_tables(no)[name]), *lines])


def tox_text() -> str:
    """11항: 독성 3행, 발암성 2행(해당없음 행 포함)."""
    return "\n".join([
        table(11, "toxicity",
              row(11, "toxicity", **COMP, endpoint="TX_ORAL", descriptor="LD50", q="> 2000 mg/kg", species="랫드",
                  status="값있음", line="p5:L3"),
              row(11, "toxicity", **COMP, endpoint="TX_INHAL", descriptor="LC50", q="5.2 mg/L", species="랫드",
                  duration_value="4", duration_unit="hr", physical_form="증기", status="값있음", line="p5:L4"),
              row(11, "toxicity", **COMP, endpoint="TX_SKIN", q="자료없음", statements="가상 설명 하나; 가상 설명 둘",
                  status="자료없음", line="p5:L5")),
        table(11, "cmr",
              row(11, "cmr", **COMP, hazard="발암성", agency="IARC", **{"class": "Group 3"}, status="값있음",
                  line="p5:L9"),
              row(11, "cmr", **COMP, hazard="발암성", agency="KR_OSH", status="해당없음", line="p5:L10")),
    ])


# ── row_tables ─────────────────────────────────────────

@pytest.mark.parametrize("no", rw.ROWS_SECTIONS_DEFAULT)
def test_row_tables_follow_schema_order(no):
    props = response_schema(no)["properties"]
    tables = rw.row_tables(no)
    assert list(tables) == list(props)
    for name, cols in tables.items():
        node = props[name]
        if node["type"] == "array":
            assert cols == list(node["items"]["properties"])
        else:   # 객체 칸은 한 행짜리 표: lines 대신 line 열 하나
            assert cols == [k for k in node["properties"] if k != "lines"] + ["line"]
        assert cols[-1] in ("line", "end")    # 마지막 열은 늘 줄 번호


def test_row_tables_examples():
    t11 = rw.row_tables(11)
    assert list(t11) == ["toxicity", "cmr", "narratives", "extras"]
    assert t11["toxicity"][:5] == ["comp_name", "comp_cas", "endpoint", "descriptor", "q"]
    assert t11["toxicity"][-2:] == ["status", "line"]
    assert len(t11["toxicity"]) == 19
    assert t11["narratives"] == ["item_code", "title_raw", "start", "end"]
    assert rw.row_tables(3)["composition"] == ["type", "no_hazardous_component", "line"]
    assert rw.ROWS_SECTIONS_DEFAULT == (3, 8, 9, 11, 12, 14, 15)


def transport_text() -> str:
    """14항: 규제 해당 행과 비위험물 행 (가짜 값)."""
    return table(14, "transport",
                 row(14, "transport", mode="해상", regulated="true", un_no="9999", shipping_name="가상 액체",
                     hazard_class="8", packing_group="II", marine_pollutant="비해당", ems_fire="F-A",
                     ems_spill="S-B", line="p6:L3"),
                 row(14, "transport", mode="공통", regulated="false", packing_group="해당없음",
                     marine_pollutant="자료없음", line="p6:L5"))


def test_transport_rows_guide():
    g = rw.rows_guide(14)
    assert "### transport" in g
    assert " | ".join(rw.row_tables(14)["transport"]) in g
    assert any(ln.startswith("- 참/거짓 열(") and "`regulated`" in ln for ln in g.splitlines())


def test_transport_parse_rows():
    parsed, errors = rw.parse_rows(transport_text(), 14)
    assert errors == []
    assert validate(parsed, response_schema(14)) == []
    on, off = parsed["transport"]
    assert on["regulated"] is True and on["un_no"] == "9999" and on["packing_group"] == "II"
    assert off["regulated"] is False and off["packing_group"] == "해당없음"


def test_transport_bad_packing_group_only_that_line():
    bad = row(14, "transport", mode="육상", regulated="true", un_no="9998", packing_group="IV", line="p6:L4")
    parsed, errors = rw.parse_rows(transport_text() + "\n" + bad, 14)
    assert len(parsed["transport"]) == 2
    assert len(errors) == 1 and "p6:L4" in errors[0]


def test_row_tables_rejects_nested_rows():
    """2항 hazard처럼 객체 안에 행 목록이 있는 항은 행 형식으로 쓸 수 없다."""
    with pytest.raises(ValueError, match="hazard"):
        rw.row_tables(2)


# ── parse_qm ───────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    ("658 mg/L", {"raw": "658 mg/L", "value": 658, "unit": "mg/L"}),
    ("20 ~ 30 %", {"raw": "20 ~ 30 %", "lower_op": ">=", "lower": 20, "upper_op": "<=", "upper": 30, "unit": "%"}),
    (">= 99.96 %", {"raw": ">= 99.96 %", "lower_op": ">=", "lower": 99.96, "unit": "%"}),
    ("약 1.2 g/cm3", {"raw": "약 1.2 g/cm3", "value": 1.2, "approx": True, "unit": "g/cm3"}),
    ("해당없음", {"raw": "해당없음"}),
    ("", None),
])
def test_parse_qm_examples(text, expected):
    assert rw.parse_qm(text) == expected


@pytest.mark.parametrize("text, expected", [    # R04 부등호·범위, R06 숫자, R08 단위 기호
    ("<1 %", {"upper_op": "<", "upper": 1, "unit": "%"}),
    ("10% 이상", {"lower_op": ">=", "lower": 10, "unit": "%"}),
    ("1 미만", {"upper_op": "<", "upper": 1}),
    ("5 초과", {"lower_op": ">", "lower": 5}),
    ("≤ 0.5 ppm", {"upper_op": "<=", "upper": 0.5, "unit": "ppm"}),
    ("> 2000 mg/kg", {"lower_op": ">", "lower": 2000, "unit": "mg/kg"}),
    ("약 23 ℃", {"value": 23, "approx": True, "unit": "C"}),
    ("1,000 mg/㎥", {"value": 1000, "unit": "mg/m3"}),
    ("1.2E-3", {"value": 0.0012}),
    ("-20 ℃", {"value": -20, "unit": "C"}),
    ("10-20 %", {"lower_op": ">=", "lower": 10, "upper_op": "<=", "upper": 20, "unit": "%"}),
    ("60 ℃ (밀폐식)", {"value": 60, "unit": "C"}),
    ("약간 있음", {}),
    ("자료없음", {}),
])
def test_parse_qm_rules(text, expected):
    assert rw.parse_qm(text) == {"raw": text, **expected}


@pytest.mark.parametrize("text, expected", [    # 범위 둘째 숫자 앞의 부등호 (ADR-029)
    ("40-<50 %", {"lower_op": ">=", "lower": 40, "upper_op": "<", "upper": 50, "unit": "%"}),
    ("1 - < 5%", {"lower_op": ">=", "lower": 1, "upper_op": "<", "upper": 5, "unit": "%"}),
    ("10~<20 %", {"lower_op": ">=", "lower": 10, "upper_op": "<", "upper": 20, "unit": "%"}),
    ("10 ~ <= 20 %", {"lower_op": ">=", "lower": 10, "upper_op": "<=", "upper": 20, "unit": "%"}),
    ("0.1-≤1 %", {"lower_op": ">=", "lower": 0.1, "upper_op": "<=", "upper": 1, "unit": "%"}),
    ("25 – < 30", {"lower_op": ">=", "lower": 25, "upper_op": "<", "upper": 30}),
])
def test_parse_qm_range_lt(text, expected):
    assert rw.parse_qm(text) == {"raw": text, **expected}


@pytest.mark.parametrize("text, expected", [    # 지금 꼴은 그대로
    ("10~20 %", {"lower_op": ">=", "lower": 10, "upper_op": "<=", "upper": 20, "unit": "%"}),
    ("-5 ℃", {"value": -5, "unit": "C"}),
    ("< 5 %", {"upper_op": "<", "upper": 5, "unit": "%"}),
    ("1 - 5 %", {"lower_op": ">=", "lower": 1, "upper_op": "<=", "upper": 5, "unit": "%"}),
])
def test_parse_qm_range_lt_keeps_existing_forms(text, expected):
    assert rw.parse_qm(text) == {"raw": text, **expected}


def test_parse_qm_blank_and_types():
    assert rw.parse_qm("   ") is None
    assert rw.parse_qm(" 658 mg/L ")["raw"] == "658 mg/L"
    assert isinstance(rw.parse_qm("658 mg/L")["value"], int)
    assert isinstance(rw.parse_qm("2.0")["value"], float)     # 소수 자릿수(dp)는 fill_q가 raw로 정한다


@pytest.mark.parametrize("text, expected", [    # 칸 이름 쌍 'lower_op:>=,lower:1,unit:%' (ADR-029)
    ("lower_op:>=,lower:1,unit:%", {"lower_op": ">=", "lower": 1, "unit": "%"}),
    ("value:2.3; unit:kPa", {"value": 2.3, "unit": "kPa"}),
    ("lower_op: 이상, lower: 0.1, unit: wt%", {"lower_op": ">=", "lower": 0.1, "unit": "wt%"}),
    ("upper_op:미만;upper:5;unit:%", {"upper_op": "<", "upper": 5, "unit": "%"}),
    ("value:1,000,unit:mg/㎥", {"value": 1000, "unit": "mg/m3"}),          # 숫자의 쉼표는 나누지 않는다
    ("value:2,unit:Kpa,approx:true", {"value": 2, "unit": "kPa", "approx": True}),
    ("value:3,lower_op:>=,lower:1,upper_op:<=,upper:5,unit:%",              # 범위가 있으면 value는 버린다
     {"lower_op": ">=", "lower": 1, "upper_op": "<=", "upper": 5, "unit": "%"}),
    ("value:7,upper_op:<,upper:9", {"upper_op": "<", "upper": 9}),
])
def test_parse_qm_qm_pairs(text, expected):
    assert rw.parse_qm(text) == {"raw": text, **expected}


@pytest.mark.parametrize("text", [
    "foo:1,unit:%",                 # 모르는 이름
    "lower:abc,unit:%",             # 숫자가 아님
    "lower_op:<,lower:1",           # 하한 칸에 상한 부등호
    "upper_op:이상,upper:1",        # 상한 칸에 하한 부등호
    "approx:maybe,value:1",         # 참/거짓이 아님
    "lower_op:>=, 1",               # 쌍이 아닌 조각
    "TWA:30ppm",
])
def test_parse_qm_qm_pairs_unknown_or_bad_keep_raw_only(text):
    assert rw.parse_qm(text) == {"raw": text}


@pytest.mark.parametrize("text, expected", [    # 쌍이 아닌 지금 꼴은 그대로
    ("1 % 이상", {"lower_op": ">=", "lower": 1, "unit": "%"}),
    ("0.1 wt% 이상", {"lower_op": ">=", "lower": 0.1, "unit": "wt%"}),
    ("20 ~ 30 %", {"lower_op": ">=", "lower": 20, "upper_op": "<=", "upper": 30, "unit": "%"}),
])
def test_parse_qm_qm_pairs_keeps_other_forms(text, expected):
    assert rw.parse_qm(text) == {"raw": text, **expected}


def test_parse_rows_qm_pairs_threshold():
    text = table(15, "regulations",
                 row(15, "regulations", law="OSH", item_code="OSH_MEASURE", item_raw="작업환경측정물질", **COMP,
                     applicable="해당", threshold="lower_op:>=,lower:1,unit:%", line="p9:L3"))
    parsed, errors = rw.parse_rows(text, 15)
    assert errors == []
    th = parsed["regulations"][0]["threshold"]
    assert th == {"raw": "lower_op:>=,lower:1,unit:%", "lower_op": ">=", "lower": 1, "unit": "%"}
    assert th["lower"] == 1
    assert validate(parsed, response_schema(15)) == []


# ── parse_rows ─────────────────────────────────────────

def test_parse_rows_toxicity_and_cmr():
    parsed, errors = rw.parse_rows(tox_text(), 11)
    assert errors == []
    assert validate(parsed, response_schema(11)) == []
    assert list(parsed) == ["toxicity", "cmr", "narratives", "extras"]
    assert parsed["narratives"] == [] and parsed["extras"] == []
    tox, cmr = parsed["toxicity"], parsed["cmr"]
    assert len(tox) == 3 and len(cmr) == 2
    assert tox[0]["q"] == {"raw": "> 2000 mg/kg", "lower_op": ">", "lower": 2000, "unit": "mg/kg"}
    assert tox[0]["species"] == "랫드" and tox[0]["sex"] is None and tox[0]["statements"] == []
    assert tox[1]["duration_value"] == 4 and tox[1]["duration_unit"] == "hr" and tox[1]["physical_form"] == "증기"
    assert tox[2]["q"] == {"raw": "자료없음"} and tox[2]["status"] == "자료없음"
    assert tox[2]["statements"] == [{"value": "가상 설명 하나", "line": "p5:L5"},
                                    {"value": "가상 설명 둘", "line": "p5:L5"}]
    assert cmr[1] == {"comp_name": "가상물질 갑", "comp_cas": "1234-56-6", "hazard": "발암성", "agency": "KR_OSH",
                      "class": None, "status": "해당없음", "note": None, "line": "p5:L10"}


def test_parse_rows_wrong_column_count_drops_only_that_line():
    lines = tox_text().splitlines()
    bad = row(11, "toxicity", **COMP, endpoint="TX_EYE", status="자료없음", line="p5:L6").replace(" | ", " / ", 1)
    parsed, errors = rw.parse_rows("\n".join(lines[:3] + [bad] + lines[3:]), 11)
    assert len(errors) == 1
    assert errors[0].startswith("toxicity p5:L6 가상물질 갑 / 1234-56-6")
    assert errors[0].endswith(": 열 18개, 기대 19개")
    assert len(parsed["toxicity"]) == 3 and len(parsed["cmr"]) == 2
    assert validate(parsed, response_schema(11)) == []


def test_parse_rows_stored_shape_in_number_cell_is_error():
    """숫자 묶음 칸에 저장 모양({upper_op:...})을 쓰면 값이 사라지므로 그 줄을 오류로 돌려 재추출한다."""
    lines = tox_text().splitlines()
    bad = row(11, "toxicity", **COMP, endpoint="TX_INHAL", descriptor="LC50",
              q="{upper_op:'>',upper:15000,unit:'ppm'}", line="p5:L6")
    parsed, errors = rw.parse_rows("\n".join(lines[:3] + [bad] + lines[3:]), 11)
    assert len(errors) == 1 and errors[0].startswith("toxicity p5:L6")
    assert "원문 표기" in errors[0]
    assert len(parsed["toxicity"]) == 3


@pytest.mark.parametrize("bad", ["", "22", "L23", "p2 L23", "p2:L"])
def test_parse_rows_bad_line_id_is_error(bad):
    text = table(11, "cmr",
                 row(11, "cmr", **COMP, hazard="발암성", agency="IARC", status="해당없음", line=bad),
                 row(11, "cmr", **COMP, hazard="발암성", agency="KR_OSH", status="해당없음", line="p5:L10"))
    parsed, errors = rw.parse_rows(text, 11)
    assert len(errors) == 1 and "line 열" in errors[0]
    assert [r["line"] for r in parsed["cmr"]] == ["p5:L10"]


@pytest.mark.parametrize("raw", ["p2:L2;p2:L3;p2:L4;p2:L5", "p2:L2 ~ p2:L5", "p2:L2, p2:L3", "p2:L2 (표)"])
def test_parse_rows_line_first_id_components(raw):
    text = table(3, "components", row(3, "components", name="가상물질 갑", cas_no="1234-56-6",
                                      content="10 ~ 20 %", line=raw))
    parsed, errors = rw.parse_rows(text, 3)
    assert errors == []
    assert [c["line"] for c in parsed["components"]] == ["p2:L2"]


def test_parse_rows_line_first_id_without_page_is_error():
    text = table(3, "components", row(3, "components", name="가상물질 갑", content="10 %", line="L2;L3"))
    parsed, errors = rw.parse_rows(text, 3)
    assert parsed["components"] == [] and len(errors) == 1 and "줄 번호" in errors[0]


def test_parse_rows_line_first_id_narrative_start_end():
    text = table(11, "narratives", row(11, "narratives", item_code="S11_ROUTE", title_raw="가. 가상 제목",
                                        start="p3:L4;p3:L5", end="p3:L9"))
    parsed, errors = rw.parse_rows(text, 11)
    assert errors == []
    assert parsed["narratives"][0]["start"] == "p3:L4" and parsed["narratives"][0]["end"] == "p3:L9"


def test_parse_rows_line_first_id_composition_object():
    text = table(3, "composition", row(3, "composition", type="혼합물", line="p2:L3;p2:L4"))
    parsed, errors = rw.parse_rows(text, 3)
    assert errors == [] and parsed["composition"]["lines"]["type"] == "p2:L3"


def test_parse_rows_narrative_start_end_are_line_ids():
    text = table(11, "narratives", row(11, "narratives", item_code="S11_ROUTE", title_raw="가. 가상 제목",
                                        start="p5:L20", end="p5:L22"),
                 row(11, "narratives", item_code="S11_ROUTE", start="p5:L23", end="끝"))
    parsed, errors = rw.parse_rows(text, 11)
    assert parsed["narratives"] == [{"item_code": "S11_ROUTE", "title_raw": "가. 가상 제목",
                                     "start": "p5:L20", "end": "p5:L22"}]
    assert len(errors) == 1 and "end 열" in errors[0]


@pytest.mark.parametrize("text", ["", "   \n\n", "표가 없습니다.", "가상물질 갑 | p5:L3"])
def test_parse_rows_no_header_is_one_error(text):
    parsed, errors = rw.parse_rows(text, 11)
    assert parsed == {} and len(errors) == 1


def test_parse_rows_slash_in_value_kept():
    text = table(11, "toxicity", row(11, "toxicity", **COMP, endpoint="TX_ORAL", descriptor="LD50", q="> 2000 mg/kg",
                                     species="랫드/마우스", status="값있음", line="p5:L3"))
    parsed, errors = rw.parse_rows(text, 11)
    assert errors == [] and parsed["toxicity"][0]["species"] == "랫드/마우스"


def test_parse_rows_markdown_style():
    """코드 울타리, 마크다운 구분 줄, 앞뒤에 |를 붙인 줄도 읽는다. 행이 없는 표는 머리글만 있어도 된다."""
    cols = rw.row_tables(11)["cmr"]
    r = row(11, "cmr", **COMP, hazard="발암성", agency="IARC", status="해당없음", line="p5:L10")
    text = "\n".join(["```", "### toxicity", "", "### cmr", f"| {' | '.join(cols)} |", "|" + "---|" * len(cols),
                      f"| {r} |", "```"])
    parsed, errors = rw.parse_rows(text, 11)
    assert errors == []
    assert parsed["toxicity"] == [] and [x["agency"] for x in parsed["cmr"]] == ["IARC"]


def test_parse_rows_first_cell_empty():
    """첫 칸이 빈 행(제품 전체 값)도 읽는다."""
    text = table(11, "toxicity", row(11, "toxicity", endpoint="TX_ORAL", descriptor="ATE", q="3,500 mg/kg",
                                     status="값있음", line="p5:L3"))
    parsed, errors = rw.parse_rows(text, 11)
    assert errors == []
    assert parsed["toxicity"][0]["comp_name"] is None and parsed["toxicity"][0]["q"]["value"] == 3500


def test_parse_rows_unknown_table_is_error():
    text = "### 독성\n가상물질 갑 | p5:L3\n" + table(11, "cmr", row(11, "cmr", **COMP, hazard="발암성", agency="IARC",
                                                                       status="해당없음", line="p5:L10"))
    parsed, errors = rw.parse_rows(text, 11)
    assert len(errors) == 1 and "독성" in errors[0] and "toxicity" in errors[0]
    assert parsed["toxicity"] == [] and len(parsed["cmr"]) == 1


def test_parse_rows_bad_enum_or_number_drops_row():
    text = table(11, "toxicity",
                 row(11, "toxicity", **COMP, endpoint="TX_ORL", line="p5:L3"),
                 row(11, "toxicity", **COMP, endpoint="TX_ORAL", duration_value="4h", line="p5:L4"),
                 row(11, "toxicity", **COMP, endpoint="TX_ORAL", line="p5:L5"))
    parsed, errors = rw.parse_rows(text, 11)
    assert len(errors) == 2
    assert "p5:L3" in errors[0] and "endpoint" in errors[0]
    assert "p5:L4" in errors[1] and "duration_value" in errors[1]
    assert [r["line"] for r in parsed["toxicity"]] == ["p5:L5"]
    assert validate(parsed, response_schema(11)) == []


def test_parse_rows_section3_object_bool_list():
    text = "\n".join([
        table(3, "composition", row(3, "composition", type="혼합물", no_hazardous_component="false", line="p2:L3")),
        table(3, "components",
              row(3, "components", name="가상물질 갑", synonyms="가상명 A; 가상명 B", cas_no="1234-56-6",
                  content="10 ~ 20 %", line="p2:L5"),
              row(3, "components", name="영업비밀 성분", content="1 ~ 5 %", trade_secret="true", line="p2:L6")),
    ])
    parsed, errors = rw.parse_rows(text, 3)
    assert errors == []
    assert validate(parsed, response_schema(3)) == []
    assert parsed["composition"] == {"type": "혼합물", "no_hazardous_component": False,
                                     "lines": {"type": "p2:L3", "no_hazardous_component": "p2:L3"}}
    c = parsed["components"]
    assert c[0]["synonyms"] == ["가상명 A", "가상명 B"] and c[0]["trade_secret"] is None
    assert c[0]["content"] == {"raw": "10 ~ 20 %", "lower_op": ">=", "lower": 10, "upper_op": "<=", "upper": 20,
                               "unit": "%"}
    assert c[1]["trade_secret"] is True and c[1]["synonyms"] == []
    assert parsed["extras"] == []


def test_parse_rows_composition_missing_or_twice():
    parsed, errors = rw.parse_rows(table(3, "components"), 3)
    assert errors == [] and parsed["composition"] == {"lines": {}} and parsed["components"] == []
    assert validate(parsed, response_schema(3)) == []

    text = table(3, "composition", row(3, "composition", type="혼합물", line="p2:L3"),
                 row(3, "composition", type="단일물질", line="p2:L4"))
    parsed, errors = rw.parse_rows(text, 3)
    assert parsed["composition"]["type"] == "혼합물"
    assert len(errors) == 1 and "p2:L4" in errors[0]


def test_parse_rows_bool_must_be_true_false():
    text = table(3, "components", row(3, "components", name="가상물질 갑", trade_secret="예", line="p2:L5"))
    parsed, errors = rw.parse_rows(text, 3)
    assert parsed["components"] == [] and len(errors) == 1 and "trade_secret" in errors[0]


def test_parse_rows_cond_pairs():
    text = table(9, "physchem",
                 row(9, "physchem", prop_code="VAPOR_PRESSURE", q="2.3 kPa", cond="temp=20; temp_unit=C",
                     line="p5:L4"),
                 row(9, "physchem", prop_code="FLASH_POINT", q="60 ℃", cond="method=밀폐식", line="p5:L1"),
                 row(9, "physchem", prop_code="FLASH_POINT", q="60 ℃", cond="온도 20", line="p5:L2"))
    parsed, errors = rw.parse_rows(text, 9)
    assert [r["cond"] for r in parsed["physchem"]] == [{"temp": 20, "temp_unit": "C"}, {"method": "밀폐식"}]
    assert parsed["physchem"][1]["q"] == {"raw": "60 ℃", "value": 60, "unit": "C"}
    assert len(errors) == 1 and "cond" in errors[0] and "p5:L2" in errors[0]


# ── rows_guide ─────────────────────────────────────────

@pytest.mark.parametrize("no", rw.ROWS_SECTIONS_DEFAULT)
def test_rows_guide_tables_and_examples_parse(no):
    """표마다 머리글과 열 이름 줄이 있고, 예시 행은 그 항 스키마 검증을 통과한다."""
    guide = rw.rows_guide(no)
    for name, cols in rw.row_tables(no).items():
        assert f"### {name}\n{' | '.join(cols)}\n" in guide
    parsed, errors = rw.parse_rows(guide, no)
    assert errors == []
    assert validate(parsed, response_schema(no)) == []
    for name in response_schema(no)["properties"]:
        assert parsed[name], f"{no}항 {name} 예시 없음"


def test_rows_guide_rules():
    g = rw.rows_guide(11)
    for s in ("`|`", "`/`", "p2:L23", "자료없음", "해당없음", "미기재", "비워", "`converted`", "`statements`"):
        assert s in g, s
    assert "temp_unit" not in g and "temp_unit" in rw.rows_guide(9)          # 조건 열은 9항에만
    assert "`true`" not in g and "`true`" in rw.rows_guide(3)                # 참/거짓 열은 3항에만
    assert "S11_ROUTE" in g and "S12_OTHER" not in g                          # 서술 항목 코드는 이 항의 것


def test_rows_guide_only_this_section_tables():
    g = rw.rows_guide(12)
    assert "### ecotox\n" in g and "### toxicity\n" not in g and "### composition\n" not in g


# ── 선택지 열 (rows-tune step 0) ───────────────────────

def _enum(no: int, table: str, col: str) -> list[str]:
    """응답 스키마에서 읽은 그 열의 선택지."""
    t = next(t for t in rw._tables(no) if t.name == table)
    return rw._resolve(t.schema["properties"][col], t.schema["$defs"])["enum"]


def _choice_line(no: int, col: str) -> str:
    return next(ln for ln in rw.rows_guide(no).splitlines() if ln.startswith(f"- `{col}`: "))


def test_rows_guide_enum_applicable_15():
    line = _choice_line(15, "applicable")
    values = line.split(": ", 1)[1].split(" / ")
    assert "해당" in values and "비해당" in values
    assert values == _enum(15, "regulations", "applicable")      # 값은 스키마에서 읽는다


def test_rows_guide_enum_long_list_points_to_code_table():
    line = _choice_line(9, "prop_code")
    assert line == "- `prop_code`: [코드표]의 코드만"
    assert not any(code in line for code in _enum(9, "physchem", "prop_code"))
    assert _choice_line(15, "item_code") == "- `item_code`: [코드표]의 코드만"
    assert _choice_line(11, "endpoint") == "- `endpoint`: [코드표]의 코드만"


def test_rows_guide_enum_long_list_without_code_table_is_listed():
    """12항 지표는 선택지가 많아도 코드표에 없어 목록으로 쓴다."""
    values = _enum(12, "ecotox", "descriptor")
    assert len(values) > 12
    assert _choice_line(12, "descriptor") == "- `descriptor`: " + " / ".join(values)


@pytest.mark.parametrize("no", rw.ROWS_SECTIONS_DEFAULT)
def test_rows_guide_enum_lines_under_column_line(no):
    """표마다 열 이름 줄 바로 아래, 예시 행 위에 선택지 열마다 한 줄씩 열 순서대로 둔다."""
    lines = rw.rows_guide(no).splitlines()
    for t in rw._tables(no):
        i = lines.index(f"### {t.name}") + 2
        enum_cols = [c for c in t.columns
                     if "enum" in rw._resolve(t.schema["properties"].get(c, {}), t.schema["$defs"])]
        block = lines[i:i + len(enum_cols)]
        assert [ln.split("`")[1] for ln in block] == enum_cols, t.name
        assert all(ln.startswith("- `") for ln in block)
        assert " | " in lines[i + len(enum_cols)]                    # 그다음은 예시 행


def test_rows_guide_enum_rules():
    g = rw.rows_guide(15)
    assert "선택지" in g and "목록의 값만" in g
    assert any("`비해당`" in ln and "`applicable`" in ln and "`해당 없음`" in ln for ln in g.splitlines())
    assert "`-210 ℃`" in g and "다른 열" in g
    assert "extras" in g and "start" in g
    g9 = rw.rows_guide(9)
    assert any(ln.startswith("- `cond` 열에는") and "측정 조건" in ln for ln in g9.splitlines())
    assert "`비해당`을 쓴다" not in rw.rows_guide(11)          # 비해당만 있는 열이 없는 항
    assert "`start`~`end`" not in rw.rows_guide(9)             # 서술 항목이 없는 항


def test_parse_rows_enum_hae_dang_eopseum_to_bihaedang():
    text = table(15, "regulations",
                 row(15, "regulations", law="OSH", item_code="OSH_MEASURE", **COMP, applicable="해당 없음",
                     line="p9:L3"),
                 row(15, "regulations", law="OSH", item_code="OSH_MEASURE", **COMP, applicable=" 해당없음 ",
                     line="p9:L4"))
    parsed, errors = rw.parse_rows(text, 15)
    assert errors == []
    expected = "해당없음" if "해당없음" in _enum(15, "regulations", "applicable") else "비해당"
    assert [r["applicable"] for r in parsed["regulations"]] == [expected, expected]
    assert validate(parsed, response_schema(15)) == []


def test_parse_rows_enum_spaces_removed_when_in_choices():
    """선택지에 해당없음이 있는 열은 공백만 지운다 (14항 용기등급)."""
    text = table(14, "transport",
                 row(14, "transport", mode="해상", regulated="false", packing_group="해당 없음",
                     marine_pollutant="해당없음", line="p6:L3"))
    parsed, errors = rw.parse_rows(text, 14)
    assert errors == []
    tr = parsed["transport"][0]
    assert tr["packing_group"] == "해당없음" and tr["marine_pollutant"] == "비해당"


def test_parse_rows_enum_out_of_choices_is_error():
    text = table(15, "regulations",
                 row(15, "regulations", law="OSH", item_code="OSH_MEASURE", **COMP, applicable="가상값",
                     line="p9:L3"))     # '값있음'은 이제 '해당'으로 맞춘다 (ADR-029)
    parsed, errors = rw.parse_rows(text, 15)
    assert parsed["regulations"] == []
    assert len(errors) == 1 and "p9:L3" in errors[0] and "applicable" in errors[0]


def test_parse_rows_enum_status_fills_blank_q():
    text = table(11, "toxicity",
                 row(11, "toxicity", **COMP, endpoint="TX_SKIN", status="자료없음", line="p5:L5"),
                 row(11, "toxicity", **COMP, endpoint="TX_EYE", status="해당 없음", line="p5:L6"),
                 row(11, "toxicity", **COMP, endpoint="TX_ORAL", q="자료없음", status="미기재", line="p5:L7"),
                 row(11, "toxicity", **COMP, endpoint="TX_RESP_SENS", status="값있음", line="p5:L8"))
    parsed, errors = rw.parse_rows(text, 11)
    assert errors == []
    skin, eye, oral, sens = parsed["toxicity"]
    assert skin["q"] == {"raw": "자료없음"} and skin["converted"] is None     # 환산값 열은 채우지 않는다
    assert eye["status"] == "해당없음" and eye["q"] == {"raw": "해당없음"}
    assert oral["q"] == {"raw": "자료없음"}                                   # 쓴 값은 그대로
    assert sens["q"] is None
    assert validate(parsed, response_schema(11)) == []


def test_parse_rows_skips_guide_enum_lines():
    """모델이 안내문의 선택지 줄을 따라 써도 행으로 읽지 않는다."""
    text = "\n".join([table(15, "regulations"), _choice_line(15, "applicable"), _choice_line(15, "item_code"),
                      row(15, "regulations", law="OSH", item_code="OSH_MEASURE", **COMP, applicable="해당",
                          line="p9:L3")])
    parsed, errors = rw.parse_rows(text, 15)
    assert errors == [] and len(parsed["regulations"]) == 1


# ── 열 수가 하나 어긋난 행 살리기 (ADR-021) ───────────

ALIGN = {"endpoint": "TX_ORAL", "descriptor": "LD50", "q": "> 2000 mg/kg", "species": "랫드", "status": "값있음",
         "line": "p8:L8"}


def cells(no: int, name: str, **values) -> list[str]:
    """열 이름 → 값으로 행의 칸 목록. 빠진 열은 빈 칸. 칸을 빼거나 더해 열 수가 어긋난 행을 만든다."""
    return [str(values.get(c, "")) for c in rw.row_tables(no)[name]]


def tox_rows(*rows: list[str]) -> str:
    return table(11, "toxicity", *(" | ".join(r) for r in rows))


def test_parse_rows_align_missing_blank_in_gap():
    """19열 표에 가운데 빈 칸 하나를 빠뜨린 18칸 행: 빈 칸을 그 빈 칸 줄 어디에 끼워도 값 칸의 열이 같아 살린다.
    '값있음 | p8:L8' 사이에 끼우면 값있음이 statements(자유 글)로 가지만, status(선택지)를 비우는 해석이라 따지지 않는다."""
    full = cells(11, "toxicity", **ALIGN)
    short = full[:10] + full[11:]                  # exposure_type의 빈 칸 하나를 뺀다
    assert len(short) == 18 and not any(short[6:16])
    parsed, errors = rw.parse_rows(tox_rows(short), 11)
    assert errors == []
    [r] = parsed["toxicity"]
    assert (r["endpoint"], r["status"], r["line"]) == ("TX_ORAL", "값있음", "p8:L8")
    assert r["exposure_type"] is None and r["statements"] == []
    assert parsed["toxicity"] == rw.parse_rows(tox_rows(full), 11)[0]["toxicity"]


def test_parse_rows_align_value_in_middle_goes_to_choice_column():
    """빈 칸 줄 사이에 값(증기)이 있으면 빠진 빈 칸이 그 앞인지 뒤인지에 따라 physical_form과 exposure_type으로 갈린다.
    physical_form은 선택지 열이라 그 해석이 선택지 열을 하나 더 채워 그쪽으로 살린다 (ADR-029. 전에는 모호해 버렸다)."""
    full = cells(11, "toxicity", **ALIGN, physical_form="증기")
    short = full[:10] + full[11:]
    assert short[9] == "증기" and not any(short[6:9]) and not any(short[10:16])
    parsed, errors = rw.parse_rows(tox_rows(short), 11)
    assert errors == []
    [r] = parsed["toxicity"]
    assert r["physical_form"] == "증기" and r["exposure_type"] is None
    assert parsed["toxicity"] == rw.parse_rows(tox_rows(full), 11)[0]["toxicity"]


def test_parse_rows_align_extra_blank_in_gap():
    full = cells(11, "toxicity", **ALIGN)
    parsed, errors = rw.parse_rows(tox_rows(full[:10] + [""] + full[10:]), 11)
    assert errors == []
    assert parsed["toxicity"] == rw.parse_rows(tox_rows(full), 11)[0]["toxicity"]


def test_parse_rows_align_trailing_separator():
    """줄 끝에 '|'를 하나 더 붙인 행(마지막 칸이 빈 칸)도 빈 칸 하나 더로 보고 살린다."""
    full = cells(11, "toxicity", **ALIGN)
    parsed, errors = rw.parse_rows(table(11, "toxicity", " | ".join(full) + " |"), 11)
    assert errors == [] and parsed["toxicity"][0]["line"] == "p8:L8"


@pytest.mark.parametrize("n", [17, 21])
def test_parse_rows_align_two_off_is_error(n):
    full = cells(11, "toxicity", **ALIGN)
    bad = full[:9] + full[11:] if n == 17 else full[:10] + ["", ""] + full[10:]
    assert len(bad) == n
    parsed, errors = rw.parse_rows(tox_rows(bad, full), 11)
    assert len(parsed["toxicity"]) == 1
    assert len(errors) == 1 and errors[0].endswith(f": 열 {n}개, 기대 19개")


def test_parse_rows_align_no_blank_to_remove_is_error():
    """칸이 하나 많은데 빈 칸이 없으면 뺄 칸을 고를 수 없어 버린다."""
    full = cells(11, "cmr", **COMP, hazard="발암성", agency="IARC", status="값있음", note="가상 비고", line="p5:L9",
                 **{"class": "Group 3"})
    parsed, errors = rw.parse_rows(table(11, "cmr", " | ".join(full[:-1] + ["가상 비고 둘", full[-1]])), 11)
    assert parsed["cmr"] == [] and len(errors) == 1 and errors[0].endswith(": 열 9개, 기대 8개")


def test_parse_rows_align_choice_between_values_is_error():
    """값 두 칸 사이의 빈 칸(class)을 빠뜨린 행: 빈 칸 줄 옆에 끼우면 해당없음이 class로,
    값 사이에 끼우면 status(선택지)로 간다. class의 값 없음 글자는 status로 옮기므로(ADR-029) 두 해석이
    선택지 열을 똑같이 채우고, 열 배치가 달라 모호하다고 보고 버린다."""
    full = cells(11, "cmr", **COMP, hazard="발암성", agency="KR_OSH", status="해당없음", line="p5:L10")
    short = full[:4] + full[5:]
    parsed, errors = rw.parse_rows(table(11, "cmr", " | ".join(short)), 11)
    assert parsed["cmr"] == []
    assert len(errors) == 1 and errors[0].endswith(": 열 7개, 기대 8개")


def test_parse_rows_align_object_table():
    """객체 칸(3항 composition)의 한 행짜리 표도 같은 규칙으로 살린다."""
    full = cells(3, "composition", type="혼합물", line="p2:L3")
    parsed, errors = rw.parse_rows(table(3, "composition", " | ".join(full[:1] + full[2:])), 3)
    assert errors == []
    assert parsed["composition"] == rw.parse_rows(table(3, "composition", " | ".join(full)), 3)[0]["composition"]


# ── 표별 기본값: 함유량 단위, 9항 값 없음 (ADR-022) ───

def _content(cell: str) -> dict:
    text = table(3, "components", row(3, "components", name="가상물질 갑", cas_no="1234-56-6", content=cell,
                                      line="p2:L5"))
    parsed, errors = rw.parse_rows(text, 3)
    assert errors == []
    return parsed["components"][0]["content"]


def test_content_unit_defaults_to_percent():
    assert _content("99.999") == {"raw": "99.999", "value": 99.999, "unit": "%"}
    q = _content("40 ~ 50")
    assert (q["lower"], q["upper"], q["unit"], q["raw"]) == (40, 50, "%", "40 ~ 50")


def test_content_unit_keeps_written_unit():
    assert _content("10 ~ 20 %")["unit"] == "%"
    assert _content("1 ppm")["unit"] == "ppm"


def test_content_unit_not_added_without_number():
    assert _content("자료없음") == {"raw": "자료없음"}


def _physchem(**values) -> dict:
    text = table(9, "physchem", row(9, "physchem", **values))
    parsed, errors = rw.parse_rows(text, 9)
    assert errors == []
    return parsed["physchem"][0]


def test_physchem_no_value_moves_to_q():
    r = _physchem(prop_code="ODOR_THRESHOLD", text_value="자료없음", line="p5:L6")
    assert r["q"] == {"raw": "자료없음"} and r["text_value"] is None


def test_physchem_no_value_keeps_real_text_and_existing_q():
    r = _physchem(prop_code="APPEARANCE_COLOR", text_value="무색", line="p5:L2")
    assert r["text_value"] == "무색" and r["q"] is None
    r = _physchem(prop_code="ODOR_THRESHOLD", q="0.5 ppm", text_value="자료없음", line="p5:L6")
    assert r["q"]["value"] == 0.5 and r["text_value"] == "자료없음"


# ── 점수 고침: 행 파서 다섯 가지 (score-fix step 2, ADR-029) ───

REG14 = ["OSH", "OSH_PROHIBIT", "금지대상 유해물질", "", "", "해당없음", "", "", "", "", "", "", "", "p10:L23"]


def test_score_fix_realign_keeps_reading_with_more_choices():
    """15열 규제 표에 빈 칸 하나를 빠뜨린 14칸 행: 해당없음이 applicable(선택지)에 가는 해석이
    threshold(숫자 묶음)에 가는 해석보다 선택지 열을 하나 더 채우므로 그 행을 살린다."""
    assert len(REG14) == len(rw.row_tables(15)["regulations"]) - 1
    parsed, errors = rw.parse_rows(table(15, "regulations", " | ".join(REG14)), 15)
    assert errors == []
    [r] = parsed["regulations"]
    assert (r["law"], r["item_code"], r["item_raw"]) == ("OSH", "OSH_PROHIBIT", "금지대상 유해물질")
    assert r["applicable"] == "비해당" and r["threshold"] is None and r["line"] == "p10:L23"
    assert validate(parsed, response_schema(15)) == []


def test_score_fix_realign_extra_blank_keeps_reading_with_more_choices():
    """빈 칸 하나를 더 쓴 16칸 행도 같은 규칙으로 살린다."""
    cells16 = REG14[:6] + [""] * 9 + REG14[-1:]
    assert len(cells16) == len(rw.row_tables(15)["regulations"]) + 1
    parsed, errors = rw.parse_rows(table(15, "regulations", " | ".join(cells16)), 15)
    assert errors == [] and parsed["regulations"][0]["applicable"] == "비해당"


def test_score_fix_realign_tie_still_dropped():
    """값이 자유 글 열 두 곳(country·value_raw) 중 어디인지 모르는 행: 두 해석이 선택지 열을 똑같이 채워 버린다."""
    full = cells(15, "regulations", law="OSH", item_code="OSH_PROHIBIT", applicable="해당", value_raw="가상 값",
                 line="p10:L24")
    short = full[:8] + full[9:]                       # qty_alt의 빈 칸 하나를 뺀다
    assert short[11] == "가상 값" and not any(short[6:11]) and not short[12]
    parsed, errors = rw.parse_rows(table(15, "regulations", " | ".join(short)), 15)
    assert parsed["regulations"] == []
    assert len(errors) == 1 and errors[0].endswith(": 열 14개, 기대 15개")


def test_score_fix_realign_unique_reading_unchanged():
    """지금 규칙으로 하나가 남는 행(값 칸 뒤 빈 칸 줄 안에서 빠진 칸)은 결과가 같다."""
    full = cells(15, "regulations", law="OSH", item_code="OSH_PROHIBIT", item_raw="가상 항목", **COMP,
                 applicable="해당", line="p10:L25")
    parsed, errors = rw.parse_rows(table(15, "regulations", " | ".join(full[:8] + full[9:])), 15)
    assert errors == []
    assert parsed["regulations"] == rw.parse_rows(table(15, "regulations", " | ".join(full)), 15)[0]["regulations"]


@pytest.mark.parametrize("no, name, col, text, expected", [
    (15, "regulations", "applicable", "값있음", "해당"),
    (15, "regulations", "applicable", "값 있음", "해당"),
    (14, "transport", "mode", "육상(ADR·국내)", "육상"),
    (14, "transport", "mode", "해상 (IMDG)", "해상"),
    (14, "transport", "marine_pollutant", "해당없음(국내)", "비해당"),
])
def test_score_fix_choice_matches(no, name, col, text, expected):
    values = _enum(no, name, col)
    assert "값있음" not in values
    assert rw._choice(text, values) == expected


@pytest.mark.parametrize("no, name, col, text", [
    (11, "toxicity", "status", "값있음"),             # 값있음이 선택지에 있으면 그대로
    (15, "regulations", "applicable", "해당"),
    (14, "transport", "packing_group", "해당 없음"),   # 지금 규칙: 공백만 지운다
])
def test_score_fix_choice_existing_rules_unchanged(no, name, col, text):
    values = _enum(no, name, col)
    assert rw._choice(text, values) == re.sub(r"\s+", "", text)


@pytest.mark.parametrize("no, name, col, text", [
    (14, "transport", "packing_group", "값있음"),      # 선택지에 해당이 없는 열
    (14, "transport", "mode", "도로(ADR)"),             # 괄호를 떼도 선택지에 없음
    (15, "regulations", "applicable", "가상값"),
])
def test_score_fix_choice_out_of_choices_kept_as_is(no, name, col, text):
    assert rw._choice(text, _enum(no, name, col)) == text


def test_score_fix_choice_rows():
    text = "\n".join([
        table(15, "regulations", row(15, "regulations", law="OSH", item_code="OSH_MEASURE", **COMP,
                                     applicable="값있음", line="p9:L3")),
        table(14, "transport", row(14, "transport", mode="육상(ADR·국내)", regulated="true", un_no="9999",
                                   line="p10:L3"))])
    parsed15, errors15 = rw.parse_rows(text.split("### transport")[0], 15)
    parsed14, errors14 = rw.parse_rows("### transport" + text.split("### transport")[1], 14)
    assert errors15 == [] and parsed15["regulations"][0]["applicable"] == "해당"
    assert errors14 == [] and parsed14["transport"][0]["mode"] == "육상"


def _cmr(**values) -> dict:
    parsed, errors = rw.parse_rows(table(11, "cmr", row(11, "cmr", **COMP, hazard="발암성", agency="KR_OSH",
                                                         line="p5:L10", **values)), 11)
    assert errors == []
    return parsed["cmr"][0]


@pytest.mark.parametrize("cls, status", [("해당없음", "해당없음"), ("해당 없음", "해당없음"), ("자료없음", "자료없음"),
                                         ("미기재", "미기재"), ("비해당", "해당없음")])
def test_score_fix_cmr_no_value_class_to_status(cls, status):
    r = _cmr(**{"class": cls})
    assert r["class"] is None and r["status"] == status


def test_score_fix_cmr_class_kept():
    r = _cmr(**{"class": "Group 3"}, status="값있음")
    assert (r["class"], r["status"]) == ("Group 3", "값있음")
    r = _cmr(**{"class": "해당없음"}, status="자료없음")      # 상태가 있으면 그대로
    assert (r["class"], r["status"]) == ("해당없음", "자료없음")
    r = _cmr(**{"class": "1A"})
    assert (r["class"], r["status"]) == ("1A", None)


def _tox(**values) -> dict:
    parsed, errors = rw.parse_rows(table(11, "toxicity", row(11, "toxicity", **COMP, line="p5:L3", **values)), 11)
    assert errors == []
    return parsed["toxicity"][0]


@pytest.mark.parametrize("values", [
    {"endpoint": "TX_SKIN", "q": "자극성 없음", "status": "값있음"},
    {"endpoint": "TX_CARC", "status": "자료없음"},                    # q는 상태로 채운 {"raw": 자료없음}
    {"endpoint": "TX_STOT_RE", "statements": "가상 설명", "status": "값있음"},
])
def test_score_fix_tox_non_acute_descriptor(values):
    assert _tox(**values)["descriptor"] == "결과기술"


@pytest.mark.parametrize("values, expected", [
    ({"endpoint": "TX_ORAL", "status": "자료없음"}, None),                     # 급성 행
    ({"endpoint": "TX_INHAL", "q": "자료없음"}, None),
    ({"endpoint": "TX_DERMAL"}, None),
    ({"endpoint": "TX_SKIN", "q": "500 mg", "status": "값있음"}, None),         # q에 숫자
    ({"endpoint": "TX_STOT_RE", "q": "> 100 mg/kg", "status": "값있음"}, None),
    ({"endpoint": "TX_REPRO", "descriptor": "NOAEL", "status": "값있음"}, "NOAEL"),   # 지표가 있으면 그대로
])
def test_score_fix_tox_descriptor_kept(values, expected):
    assert _tox(**values)["descriptor"] == expected


@pytest.mark.parametrize("text, raw", [("해당 없음", "해당없음"), ("자료 없음", "자료없음"), (" 미기재", "미기재")])
def test_score_fix_physchem_no_value_ignores_spaces(text, raw):
    r = _physchem(prop_code="ODOR_THRESHOLD", text_value=text, line="p5:L6")
    assert r["q"] == {"raw": raw} and r["text_value"] is None


@pytest.mark.parametrize("text, unit", [("°C", "C"), ("℃", "C"), ("° F", "F"), ("℉", "F"), ("K", "K"), ("kPa", "kPa"),
                                        ("Kpa", "kPa"), ("KPA", "kPa"), ("hpa", "hPa"), ("Pa", "Pa"), ("Mpa", "MPa"),
                                        ("mmhg", "mmHg"), ("atm", "atm"), ("bar", "bar")])
def test_score_fix_physchem_unit_only_text_moves_to_q(text, unit):
    r = _physchem(prop_code="BOILING", q="100", text_value=text, line="p5:L7")
    assert r["q"]["value"] == 100 and r["q"]["unit"] == unit and r["text_value"] is None


@pytest.mark.parametrize("values", [
    {"q": "100 ℃", "text_value": "°F"},          # q에 단위가 이미 있음
    {"text_value": "°C"},                          # q가 없음
    {"q": "자료없음", "text_value": "°C"},          # q에 숫자가 없음
    {"q": "100", "text_value": "무색"},             # 단위가 아닌 글
    {"q": "100", "text_value": "°C 이상"},
])
def test_score_fix_physchem_unit_only_kept(values):
    r = _physchem(prop_code="BOILING", line="p5:L7", **values)
    assert r["text_value"] == values["text_value"]


@pytest.mark.parametrize("text, unit", [("2.3 Kpa", "kPa"), ("2.3 KPa", "kPa"), ("2.3 kpa", "kPa"), ("1013 hpa", "hPa"),
                                        ("0.1 Mpa", "MPa"), ("760 mmhg", "mmHg"), ("2.3 kPa (20 ℃)", "kPa")])
def test_score_fix_unit_pressure_case(text, unit):
    assert rw.parse_qm(text)["unit"] == unit


@pytest.mark.parametrize("text, unit", [("5 mPa·s", "mPa·s"), ("1.2 g/cm3", "g/cm3"), ("760 mmHg", "mmHg"),
                                        ("50 mg/kg", "mg/kg"), ("101.3 kPa", "kPa")])
def test_score_fix_unit_other_units_unchanged(text, unit):
    assert rw.parse_qm(text)["unit"] == unit
