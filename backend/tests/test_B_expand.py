"""extract/expand.py 시험. 줄과 응답은 직접 만든 가짜 MSDS다 (D-43). 모델 서버를 부르지 않는다."""
import importlib.util
import sys

import pytest

from msds.checks.validator import run_to21_validator
from msds.common.merge import DICTIONARY_VERSION, SCHEMA_VERSION
from msds.common.schema import load_schema, msds_item_schema, validate, validate_to21
from msds.extract import expand as ex
from msds.extract import section_specs as ss
from msds.extract.inputs import Line, line_index

FORBIDDEN = {"line", "lines", "comp_name", "comp_cas", "start", "end"}
DOC_META = {"doc_id": "T21-X01", "source_file": "가상 세정액 A.pdf", "pages": "7",
            "text_layer": "정상", "language": "ko"}


def L(lid, text):
    page, no = lid[1:].split(":L")
    return Line(lid, int(page), int(no), text)


LINES = [
    L("p1:L2", "개정번호 : 3"),
    L("p1:L5", "제품명 : 가상 세정액 A"),
    L("p1:L8", "제조자 : 가상화학"),
    L("p1:L9", "긴급전화 : 000-0000-0000"),
    L("p1:L19", "유해성·위험성 분류 : 해당"),
    L("p1:L20", "심한 눈 자극성 : 구분 2"),
    L("p2:L3", "혼합물"),
    L("p2:L5", "가상물질 갑 | 1234-56-6 | 10 ~ 20"),
    L("p2:L6", "가상물질 을 | 2345-67-7 | 0.5"),
    L("p3:L1", "가. 눈에 들어갔을 때"),
    L("p3:L2", "- 즉시 다량의 물로 15분 이상 씻어내시오."),
    L("p3:L3", "• 콘택트렌즈 : 착용하고 있으면 제거하시오."),
    L("p3:L4", "② 의사의 진료를 받으시오."),
    L("p4:L1", "용기를 단단히 밀폐하시오."),
    L("p4:L2", "1) 환기가 잘 되는 곳에서 취급하시오."),
    L("p4:L3", "가상물질 갑 | TWA 1 ppm"),
    L("p5:L1", "인화점 60 ℃ (밀폐식)"),
    L("p5:L5", "가상 추가 물성 1.20"),
    L("p5:L8", "가상물질 을 | 경구 LD50 > 2000 mg/kg (랫드)"),
    L("p5:L10", "IARC 3군"),
    L("p6:L5", "UN 번호 : 해당없음"),
    L("p6:L10", "작업환경측정대상물질 : 해당"),
    L("p7:L3", "최종 개정일자 : 2024-05-01"),
]


def narr(no, start, end, title):
    return {"item_code": ss.load_specs()[no].narrative_codes[0], "title_raw": title, "start": start, "end": end}


def responses():
    """1~16항 가짜 응답. 성분 2개, 8·11·15항 행은 CAS·이름(공백 차이)·빈 값으로 성분을 가리킨다."""
    return {
        1: {"meta": {"revision_no": 3, "last_revision_date": None,
                     "lines": {"revision_no": "p1:L2", "last_revision_date": None}},
            "product": {"name": "가상 세정액 A", "uses": ["세척제"], "lines": {"name": "p1:L5"}},
            "companies": [{"role": "제조자", "name": "가상화학",
                           "contacts": [{"type": "긴급", "value": "000-0000-0000", "line": "p1:L9"}],
                           "line": "p1:L8"}],
            "extras": []},
        2: {"hazard": {"classified": True, "signal_word": "경고",
                       "classes": [{"group": "건강", "class_code": "HH_EYE_DMG", "category": "2", "line": "p1:L20"}],
                       "other_hazards": [{"value": "가상 기타 유해성", "line": "p1:L20"}],
                       "lines": {"classified": "p1:L19"}},
            "narratives": [], "extras": []},
        3: {"composition": {"type": "혼합물", "lines": {"type": "p2:L3"}},
            "components": [
                {"name": "가상물질 갑", "cas_no": "1234-56-6",
                 "content": {"raw": "10 ~ 20", "lower_op": ">=", "lower": 10, "upper_op": "<=", "upper": 20,
                             "unit": "%"}, "line": "p2:L5"},
                {"name": "가상물질 을", "cas_no": "2345-67-7",
                 "content": {"raw": "0.5", "value": 0.5, "unit": "%"}, "line": "p2:L6"}],
            "extras": []},
        4: {"narratives": [narr(4, "p3:L1", "p3:L4", "가. 눈에 들어갔을 때")], "extras": []},
        5: {"narratives": [], "extras": []},
        6: {"narratives": [], "extras": []},
        7: {"narratives": [narr(7, "p4:L1", "p4:L2", "취급요령")], "extras": []},
        8: {"exposure_limits": [{"comp_name": None, "comp_cas": "1234-56-6", "standard": "국내",
                                 "limit_type": "TWA", "q": {"raw": "1 ppm", "value": 1, "unit": "ppm"},
                                 "line": "p4:L3"}],
            "narratives": [], "extras": []},
        9: {"physchem": [{"prop_code": "FLASH_POINT", "q": {"raw": "60 ℃", "value": 60, "unit": "℃"},
                          "cond": {"method": "밀폐식"}, "line": "p5:L1"}],
            "extras": [{"title_raw": "가상 추가 물성", "reason": "필드없음",
                        "q": {"raw": "1.20", "value": 1.2}, "line": "p5:L5"}]},
        10: {"narratives": [], "extras": []},
        11: {"toxicity": [{"comp_name": "가상물질을", "comp_cas": None, "endpoint": "TX_ORAL",
                           "descriptor": "LD50", "species": "랫드",
                           "q": {"raw": "> 2000 mg/kg", "lower_op": ">", "lower": 2000, "unit": "mg/kg"},
                           "statements": [{"value": "가상 독성 설명", "line": "p5:L8"}],
                           "line": "p5:L8"}],
             "cmr": [{"comp_name": None, "comp_cas": None, "hazard": "발암성", "agency": "IARC", "class": "3",
                      "line": "p5:L10"}],
             "narratives": [], "extras": []},
        12: {"ecotox": [], "narratives": [], "extras": []},
        13: {"narratives": [], "extras": []},
        14: {"transport": [{"mode": "공통", "regulated": False, "line": "p6:L5"}], "narratives": [], "extras": []},
        15: {"regulations": [{"comp_name": "가상물질 갑", "comp_cas": None, "law": "OSH",
                              "item_code": "OSH_MEASURE", "applicable": "해당", "line": "p6:L10"}],
             "dangerous_goods": [], "waste": [], "intl_class": [], "narratives": [], "extras": []},
        16: {"narratives": [],
             "meta_revision": {"revision_no": 5, "last_revision_date": "2024-05-01",
                               "lines": {"revision_no": "p7:L3", "last_revision_date": "p7:L3"}},
             "extras": []},
    }


def keys_in(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from keys_in(v)
    elif isinstance(node, list):
        for v in node:
            yield from keys_in(v)


@pytest.fixture
def no_conventions(monkeypatch):
    """A의 표기 규칙 모듈이 없는 상태. sys.modules에 None을 두면 find_spec이 None을 돌려준다."""
    monkeypatch.setitem(sys.modules, "msds.common.conventions", None)


def expand_one(sections):
    return ex.expand_msds(sections, line_index(LINES), 0, "텍스트층")


# ── 문서 전체 ──────────────────────────────────────────

@pytest.mark.parametrize("no", range(1, 17))
def test_fake_responses_follow_section_schema(no):
    """시험 입력이 실제 중간 형식(step 2 response_schema)에 맞아야 시험이 의미가 있다."""
    assert validate(responses()[no], ss.response_schema(no)) == []


def test_full_example_is_valid_to21(no_conventions):
    doc, problems = ex.to_to21(DOC_META, [responses()], LINES, "가상엔진 v1")
    assert validate_to21(doc) == []
    assert problems == []
    assert [e for e in run_to21_validator(doc) if e["rule"] == "V11"] == []
    assert not FORBIDDEN & set(keys_in(doc))

    d = doc["doc"]
    assert d["doc_id"] == "T21-X01" and d["source_file"] == "가상 세정액 A.pdf"
    assert d["page_count"] == 7 and d["text_layer"] == "정상" and d["language"] == "ko"
    assert d["msds_count"] == 1
    assert d["schema_version"] == SCHEMA_VERSION and d["dictionary_version"] == DICTIONARY_VERSION
    assert d["extraction"]["engine"] == "가상엔진 v1" and d["extraction"]["extracted_at"].endswith("+09:00")


def test_full_example_fields(no_conventions):
    m, _ = expand_one(responses())
    assert list(m) == list(msds_item_schema()["properties"])
    assert m["validation"] == []

    assert [c["seq"] for c in m["components"]] == [1, 2]
    assert all(type(c["seq"]) is int for c in m["components"])
    assert m["components"][0]["content"]["status"] == "값있음"
    assert m["exposure_limits"][0]["comp_ref"] == "1"     # CAS 일치
    assert m["toxicity"][0]["comp_ref"] == "2"            # 이름 일치 (공백 차이)
    assert m["cmr"][0]["comp_ref"] == "MIX"               # 둘 다 비어 있음
    assert m["regulations"][0]["comp_ref"] == "1"
    assert m["regulations"][0]["seq"] == 1
    assert m["physchem"][0]["comp_ref"] == "MIX"
    assert m["physchem"][0]["cond"]["method"] == "밀폐식" and m["physchem"][0]["cond"]["temp"] is None

    assert m["hazard"]["classes"][0]["seq"] == 1
    assert m["hazard"]["pictograms"] == []
    assert m["hazard"]["nfpa"] == {"health": None, "fire": None, "reactivity": None, "special": None}
    oh = m["hazard"]["other_hazards"][0]
    assert oh["seq"] == 1 and oh["text"] == "심한 눈 자극성 : 구분 2" and oh["value"] == "가상 기타 유해성"
    assert m["toxicity"][0]["statements"][0]["text"] == "가상물질 을 | 경구 LD50 > 2000 mg/kg (랫드)"
    assert m["companies"][0]["seq"] == 1 and m["companies"][0]["contacts"][0]["value"] == "000-0000-0000"

    # 16항 개정 정보는 1항 meta의 빈 칸만 채운다
    assert m["meta"]["revision_no"] == 3
    assert m["meta"]["last_revision_date"] == "2024-05-01"
    assert m["meta"]["page_start"] is None and m["meta"]["msds_no"] is None

    ext = m["extras"][0]
    assert (ext["seq"], ext["section_no"], ext["page"], ext["comp_ref"]) == (1, 9, 5, "MIX")
    assert ext["q"]["dp"] == 2 and ext["statements"] == []


def test_narratives(no_conventions):
    m, _ = expand_one(responses())
    eye, handling = m["narratives"]
    assert eye["item_code"] == ss.load_specs()[4].narrative_codes[0]
    assert eye["status"] == "값있음"
    # 첫 줄이 소제목(title_raw)과 같아 빠진다
    assert [s["text"] for s in eye["statements"]] == [
        "- 즉시 다량의 물로 15분 이상 씻어내시오.",
        "• 콘택트렌즈 : 착용하고 있으면 제거하시오.",
        "② 의사의 진료를 받으시오."]
    assert [s["seq"] for s in eye["statements"]] == [1, 2, 3]
    # 첫 줄이 소제목과 다르면 남는다
    assert [s["value"] for s in handling["statements"]] == ["용기를 단단히 밀폐하시오.",
                                                            "환기가 잘 되는 곳에서 취급하시오."]


def test_evidence(no_conventions):
    m, _ = expand_one(responses())
    ev = {e["field"]: e for e in m["evidence"]}
    assert ev["components[1]"] == {"field": "components[1]", "page": 2, "bbox": None,
                                   "source_text": "가상물질 을 | 2345-67-7 | 0.5", "confidence": None,
                                   "method": "텍스트층", "needs_review": None}
    assert ev["meta.revision_no"]["page"] == 1                     # 1항 값을 썼으므로 1항 줄
    assert ev["meta.last_revision_date"]["page"] == 7              # 16항에서 채운 칸
    assert ev["product.name"]["source_text"] == "제품명 : 가상 세정액 A"
    assert ev["hazard.classified"]["page"] == 1
    assert ev["hazard.classes[0]"]["source_text"] == "심한 눈 자극성 : 구분 2"
    assert ev["companies[0].contacts[0]"]["source_text"] == "긴급전화 : 000-0000-0000"
    assert ev["narratives[0]"]["page"] == 3
    assert ev["narratives[0]"]["source_text"].startswith("가. 눈에 들어갔을 때")
    assert ev["extras[0]"]["page"] == 5
    assert all(e["needs_review"] is None for e in m["evidence"])
    # V14: 필수 묶음 근거가 있다
    assert {"components", "hazard", "meta", "product"} <= {f.split("[")[0].split(".")[0] for f in ev}


def test_evidence_source_text_is_capped(no_conventions):
    """TO21 evidence.source_text는 200자 이내다 (옛 merge.py와 같다)."""
    lines = LINES + [L("p6:L20", "가" * 250)]
    r = responses()
    r[14]["transport"][0]["line"] = "p6:L20"
    m, _ = ex.expand_msds(r, line_index(lines), 0, "텍스트층")
    e = next(e for e in m["evidence"] if e["field"] == "transport[0]")
    assert e["source_text"] == "가" * 200


def test_narrative_evidence_stays_on_start_page(no_conventions):
    """원문 대조(source_match)는 한 쪽 안에서 찾으므로, 서술 근거는 시작 쪽의 줄만 담는다."""
    r = responses()
    r[4]["narratives"][0].update(start="p3:L3", end="p4:L1")
    m, problems = expand_one(r)
    assert problems == []
    e = next(e for e in m["evidence"] if e["field"] == "narratives[0]")
    assert e["page"] == 3
    assert e["source_text"] == "• 콘택트렌즈 : 착용하고 있으면 제거하시오.\n② 의사의 진료를 받으시오."
    assert m["narratives"][0]["statements"][-1]["text"] == "용기를 단단히 밀폐하시오."


def test_evidence_method_follows_text_layer(no_conventions):
    doc, _ = ex.to_to21({**DOC_META, "text_layer": "없음"}, [responses()], LINES, "e")
    assert {e["method"] for e in doc["msds"][0]["evidence"]} == {"OCR"}


def test_empty_msds_is_valid(no_conventions):
    doc, problems = ex.to_to21(DOC_META, [{}], LINES, "e")
    assert validate_to21(doc) == []
    assert [(p["msds_index"], p["section"], p["kind"]) for p in problems] == \
           [(0, n, "missing_section") for n in range(1, 17)]
    m = doc["msds"][0]
    assert list(m) == list(msds_item_schema()["properties"])
    assert all(v is None for v in m["meta"].values())
    assert m["product"]["synonyms"] == [] and m["product"]["name"] is None
    assert m["components"] == [] and m["evidence"] == []


def test_none_sections_count_as_missing(no_conventions):
    _, problems = expand_one({n: None for n in range(1, 17)})
    assert len(problems) == 16 and {p["kind"] for p in problems} == {"missing_section"}


def test_two_msds(no_conventions):
    doc, problems = ex.to_to21(DOC_META, [responses(), {3: responses()[3]}], LINES, "e")
    assert doc["doc"]["msds_count"] == 2 and len(doc["msds"]) == 2
    assert {p["msds_index"] for p in problems} == {1}
    assert len(problems) == 15


# ── 문제 목록 ──────────────────────────────────────────

def test_bad_line_keeps_value():
    r = responses()
    r[14]["transport"][0]["line"] = "p9:L99"
    m, problems = expand_one(r)
    assert problems == [{"msds_index": 0, "section": 14, "kind": "bad_line", "detail": "transport[0]: p9:L99"}]
    assert m["transport"][0]["mode"] == "공통"
    e = next(e for e in m["evidence"] if e["field"] == "transport[0]")
    assert (e["page"], e["source_text"], e["needs_review"]) == (None, None, True)


def test_bad_line_in_narrative():
    r = responses()
    r[7]["narratives"][0]["end"] = "p4:L99"
    m, problems = expand_one(r)
    assert [(p["section"], p["kind"]) for p in problems] == [(7, "bad_line")]
    assert m["narratives"][1]["statements"] == [] and m["narratives"][1]["status"] is None
    e = next(e for e in m["evidence"] if e["field"] == "narratives[1]")
    assert e["needs_review"] is True


def test_bad_range():
    r = responses()
    r[4]["narratives"][0].update(start="p3:L4", end="p3:L1")
    m, problems = expand_one(r)
    assert [(p["section"], p["kind"]) for p in problems] == [(4, "bad_range")]
    assert m["narratives"][0]["statements"] == [] and m["narratives"][0]["status"] is None


def test_empty_string_in_format_field_becomes_null(no_conventions):
    """형식(pattern)이 정해진 칸의 빈 글자는 값 없음(null)으로 펼친다. 형식이 없는 칸의 빈 글자는 그대로 둔다."""
    r = responses()
    r[3]["components"][0].update(ec_no="", ke_no="", other_id="")
    doc, _ = ex.to_to21(DOC_META, [r], LINES, "가상엔진 v1")
    comp = doc["msds"][0]["components"][0]
    assert comp["ec_no"] is None and comp["ke_no"] is None
    assert comp["other_id"] == ""
    assert validate_to21(doc) == []


def test_unlinked_component():
    r = responses()
    r[8]["exposure_limits"][0].update(comp_name="없는 물질", comp_cas="9999-99-9")
    m, problems = expand_one(r)
    assert m["exposure_limits"][0]["comp_ref"] == "MIX"
    assert [(p["section"], p["kind"]) for p in problems] == [(8, "unlinked_component")]


# ── 숫자 묶음 ──────────────────────────────────────────

def test_fill_q_no_value():
    q = ex.fill_q({"raw": "자료없음"})
    assert q["status"] == "자료없음" and q["dp"] is None and q["note"] is None
    assert set(q) == set(load_schema()["$defs"]["Q"]["properties"])
    assert ex.fill_q({"raw": "해당 없음"})["status"] == "해당없음"
    assert ex.fill_q({"raw": "미기재"})["status"] == "미기재"


def test_fill_q_range():
    q = ex.fill_q({"raw": "93 ~ 98", "lower_op": ">=", "lower": 93, "upper_op": "<=", "upper": 98, "unit": "%"})
    assert q["status"] == "값있음" and q["dp"] == 0
    assert (q["lower"], q["upper"], q["value"]) == (93, 98, None)


def test_fill_q_decimal():
    assert ex.fill_q({"raw": "0.5", "value": 0.5})["dp"] == 1
    assert ex.fill_q({"raw": "2.0 g/cm3", "value": 2, "unit": "g/cm3"})["dp"] == 1
    assert ex.fill_q({"raw": "1,000 mg/kg", "value": 1000})["dp"] == 0
    assert ex.fill_q({"raw": "-10.25 ℃", "value": -10.25})["dp"] == 2


def test_fill_q_unknown():
    assert ex.fill_q(None) is None
    q = ex.fill_q({"raw": "무색"})
    assert q["status"] is None and q["dp"] is None
    assert ex.fill_q({"raw": "1.5E-3", "value": 0.0015})["dp"] is None


# ── 서술 문장 ──────────────────────────────────────────

def test_split_statements():
    lines = [L("p1:L1", "- 즉시 물로 씻으시오."), L("p1:L2", "   "), L("p1:L3", "① 소화제 : 물분무, 포말"),
             L("p1:L4", "가. 의사의 진료를 받으시오."), L("p1:L5", "1) 환기하시오."),
             L("p1:L6", "작업 시간 09:00 이후 환기"), L("p1:L7", "·  보호장갑을 착용하시오.")]
    st = ex.split_statements(lines)
    assert [s["seq"] for s in st] == [1, 2, 3, 4, 5, 6]
    assert [s["text"] for s in st] == [l.text for l in lines if l.text.strip()]
    assert [(s["key"], s["value"]) for s in st] == [
        (None, "즉시 물로 씻으시오."), ("소화제", "물분무, 포말"), (None, "의사의 진료를 받으시오."),
        (None, "환기하시오."), (None, "작업 시간 09:00 이후 환기"), (None, "보호장갑을 착용하시오.")]
    assert all(s["refs"] == [] and s["cond"] is None and s["std_code"] is None and s["match_score"] is None
               for s in st)


def test_split_statements_keeps_minus_sign():
    st = ex.split_statements([L("p1:L1", "-20 ℃ 이하에서 보관하시오."), L("p1:L2", "- 20분 이상 씻으시오.")])
    assert [s["value"] for s in st] == ["-20 ℃ 이하에서 보관하시오.", "20분 이상 씻으시오."]


def test_split_statements_long_key_is_not_split():
    text = "이 문장은 콜론 앞이 서른 글자를 넘는 아주 긴 설명 문장입니다 그래서 : 나누지 않는다"
    st = ex.split_statements([L("p1:L1", text)])
    assert (st[0]["key"], st[0]["value"]) == (None, text)


# ── 성분 연결 ──────────────────────────────────────────

COMPS = [{"seq": 1, "name": "가상물질 갑", "cas_no": "1234-56-6"},
         {"seq": 2, "name": "가상물질 을", "cas_no": "2345-67-7"}]


def test_link_components():
    rows = [{"comp_name": None, "comp_cas": "2345-67-7", "line": "p1:L1"},
            {"comp_name": "가상 물질갑", "comp_cas": None},
            {"comp_name": "가상물질 을", "comp_cas": "0000-00-0"},
            {"comp_name": None, "comp_cas": None},
            {"comp_name": "없는 물질", "comp_cas": "9999-99-9"}]
    out = ex.link_components(rows, COMPS)
    assert [r["comp_ref"] for r in out] == ["2", "1", "2", "MIX", "MIX"]
    assert out[0]["line"] == "p1:L1"
    assert not {"comp_name", "comp_cas"} & set(keys_in(out))
    assert rows[0]["comp_cas"] == "2345-67-7"      # 입력은 바꾸지 않는다


# ── 표기 규칙 자리 ─────────────────────────────────────

def test_apply_conventions_absent(no_conventions):
    item = {"meta": {"source_note": None}}
    assert ex.apply_conventions(item) is item


def test_apply_conventions_present(monkeypatch):
    name = "msds.common.conventions"
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader=None))
    calls = []

    def apply(m):
        calls.append(m)
        return {**m, "meta": {**m["meta"], "source_note": "표기 규칙 적용"}}

    mod.apply = apply
    monkeypatch.setitem(sys.modules, name, mod)
    doc, _ = ex.to_to21(DOC_META, [responses(), {}], LINES, "e")
    assert len(calls) == 2
    assert [m["meta"]["source_note"] for m in doc["msds"]] == ["표기 규칙 적용"] * 2


def test_module_without_apply_is_ignored(monkeypatch):
    name = "msds.common.conventions"
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader=None))
    monkeypatch.setitem(sys.modules, name, mod)
    item = {"meta": {}}
    assert ex.apply_conventions(item) is item
