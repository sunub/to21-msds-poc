"""extract/expand.py 시험. 줄과 응답은 직접 만든 가짜 MSDS다 (D-43). 모델 서버를 부르지 않는다."""
import importlib.util
import sys

import pytest

from msds.checks.validator import run_to21_validator
from msds.common.merge import DICTIONARY_VERSION, SCHEMA_VERSION
from msds.common.schema import load_schema, msds_item_schema, validate, validate_to21
from msds.extract import expand as ex
from msds.extract.inputs import EXTRACT_SECTIONS
from msds.extract import rows as rw
from msds.extract import section_specs as ss
from msds.extract.inputs import Line, line_index
from msds.extract.section_prompts import _unwrap
from msds.extract.section_runner import check_section

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
    L("p5:L2", " ο 색상 : 무색"),
    L("p5:L3", "점도  7.5 mPa·s"),
    L("p5:L5", "가상 추가 물성 1.20"),
    L("p5:L8", "가상물질 을 | 경구 LD50 > 2000 mg/kg (랫드)"),
    L("p5:L10", "IARC 3군"),
    L("p5:L12", "인화 또는 폭발 범위의 상한/하한 | 4.0~76% | 자료없음"),
    L("p5:L13", "인화점 | 자료없음 | 자료없음"),
    L("p5:L14", "인화 또는 폭발 범위의 상한/하한 75 / 4 %"),
    L("p5:L15", "인화 또는 폭발 범위의 상한/하한 | 자료없음"),
    L("p5:L16", "폭발상한(UEL) 8.0vol%"),
    L("p5:L17", "폭발하한(LEL) 1.2vol%"),
    L("p5:L18", "pH | 7.0 | 자료없음"),
    L("p6:L5", "UN 번호 : 해당없음"),
    L("p6:L10", "작업환경측정대상물질 : 해당"),
    L("p6:L11", "2)화학물질관리법에 의한 규제 : 해당 없음"),
    L("p6:L12", "나.유해화학물질관리법에 의한 규제 자료없음"),
    L("p6:L13", "등록대상기존화학물질 : 가상-0001"),
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


def omit_empty(response: dict, schema: dict) -> dict:
    """필수 칸을 줄인 서버 스키마로 받은 응답 모양 (ADR-017). 객체마다 그 객체의 required에 없는 칸 중
    값이 None이거나 []인 칸을 지운 새 사본. required에 있는 칸은 None이어도 남긴다(서버 문법이 늘 쓰게 한다)."""
    def walk(value, node):
        node = _unwrap(schema, node)
        if isinstance(value, list):
            return [walk(v, node) for v in value]
        if isinstance(value, dict):
            props, required = node.get("properties", {}), set(node.get("required", []))
            return {k: walk(v, props.get(k, {})) for k, v in value.items()
                    if k in required or not (v is None or v == [])}
        return value

    return walk(response, schema)


def omitted_responses():
    return {no: omit_empty(r, ss.response_schema(no)) for no, r in responses().items()}


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

    # 개정 정보는 16항 값이 1항 값보다 우선한다 (meta_from_16 시험 참고)
    assert m["meta"]["revision_no"] == 5
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


def test_split_statements_bullet_pipe():
    """version9는 불릿 기호를 표 칸처럼 ' | '로 묶어 준다. 표 행은 건드리지 않는다."""
    lines = [L("p1:L1", "- | 즉시 의료조치를 취하시오."),
             L("p1:L2", "· | 고용노동부고시 : 해당없음"),
             L("p1:L3", "| 환기가 잘 되는 곳에서 취급하시오."),
             L("p1:L4", "가상물질 | 가상 이름 | 1234-56-6 | 20 ~ 30")]
    st = ex.split_statements(lines)
    assert [s["value"] for s in st] == ["즉시 의료조치를 취하시오.", "해당없음",
                                        "환기가 잘 되는 곳에서 취급하시오.",
                                        "가상물질 | 가상 이름 | 1234-56-6 | 20 ~ 30"]
    assert [s["key"] for s in st] == [None, "고용노동부고시", None, None]
    assert [s["text"] for s in st] == [l.text for l in lines]


def test_evidence(no_conventions):
    m, _ = expand_one(responses())
    ev = {e["field"]: e for e in m["evidence"]}
    assert ev["components[1]"] == {"field": "components[1]", "page": 2, "bbox": None,
                                   "source_text": "가상물질 을 | 2345-67-7 | 0.5", "confidence": None,
                                   "method": "텍스트층", "needs_review": None}
    assert ev["meta.revision_no"]["page"] == 7                     # 16항 값이 우선이므로 16항 줄
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


def test_pictograms_from_section_2_response(no_conventions):
    """2항 응답의 그림문자(쪽 이미지에서 읽은 코드)가 hazard.pictograms로 펼쳐진다. 판독 방식은 받지 않아 null이다."""
    r = responses()
    r[2]["hazard"]["pictograms"] = [{"code": "GHS02"}, {"code": "GHS07"}]
    r[2]["hazard"]["lines"]["pictograms"] = "p1:L19"
    assert validate(r[2], ss.response_schema(2)) == []
    doc, problems = ex.to_to21(DOC_META, [r], LINES, "e")
    assert validate_to21(doc) == [] and problems == []
    hz = doc["msds"][0]["hazard"]
    assert hz["pictograms"] == [{"code": "GHS02", "detection": None}, {"code": "GHS07", "detection": None}]
    ev = {e["field"]: e for e in doc["msds"][0]["evidence"]}
    assert ev["hazard.pictograms"]["source_text"] == "유해성·위험성 분류 : 해당"
    assert not FORBIDDEN & set(keys_in(doc))


def test_empty_msds_is_valid(no_conventions):
    doc, problems = ex.to_to21(DOC_META, [{}], LINES, "e")
    assert validate_to21(doc) == []
    assert [(p["msds_index"], p["section"], p["kind"]) for p in problems] == \
           [(0, n, "missing_section") for n in EXTRACT_SECTIONS]
    m = doc["msds"][0]
    assert list(m) == list(msds_item_schema()["properties"])
    assert all(v is None for v in m["meta"].values())
    assert m["product"]["synonyms"] == [] and m["product"]["name"] is None
    assert m["components"] == [] and m["evidence"] == []


def test_none_sections_count_as_missing(no_conventions):
    _, problems = expand_one({n: None for n in range(1, 17)})
    assert len(problems) == len(EXTRACT_SECTIONS) and {p["kind"] for p in problems} == {"missing_section"}


def test_two_msds(no_conventions):
    doc, problems = ex.to_to21(DOC_META, [responses(), {3: responses()[3]}], LINES, "e")
    assert doc["doc"]["msds_count"] == 2 and len(doc["msds"]) == 2
    assert {p["msds_index"] for p in problems} == {1}
    assert len(problems) == len(EXTRACT_SECTIONS) - 1          # 응답이 있는 3항만 빠진다


def test_meta_from_16_overrides_section_1_dates():
    r = responses()
    r[1]["meta"].update({"first_issue_date": "2023-01-01", "lines": {"first_issue_date": "p1:L2"}})
    r[16]["meta_revision"].update({"first_issue_date": "2010-06-21",
                                   "lines": {**r[16]["meta_revision"]["lines"], "first_issue_date": "p7:L3"}})
    m, _ = expand_one(r)
    assert m["meta"]["first_issue_date"] == "2010-06-21"
    hits = [e for e in m["evidence"] if e["field"] == "meta.first_issue_date"]
    assert len(hits) == 1 and hits[0]["page"] == 7


def test_meta_from_16_keeps_section_1_when_16_has_none():
    r = responses()
    r[1]["meta"].update({"first_issue_date": "2023-01-01", "lines": {"first_issue_date": "p1:L2"}})
    m, _ = expand_one(r)
    assert m["meta"]["first_issue_date"] == "2023-01-01"
    hits = [e for e in m["evidence"] if e["field"] == "meta.first_issue_date"]
    assert len(hits) == 1 and hits[0]["page"] == 1


def test_meta_from_16_keeps_section_1_for_other_fields():
    r = responses()
    r[1]["meta"].update({"msds_no": "A-1", "lines": {"msds_no": "p1:L2"}})
    r[16]["meta_revision"].update({"msds_no": "B-2"})
    m, _ = expand_one(r)
    assert m["meta"]["msds_no"] == "A-1"


# ── 값 없는 칸을 뺀 응답 (ADR-017) ─────────────────────

def test_omit_empty_drops_optional_empty_fields():
    """도우미가 실제로 칸을 지우는지: 선택 칸의 None은 사라지고, 필수 칸과 값 있는 칸은 남는다."""
    r = responses()
    out = omitted_responses()
    tox, cmr = out[11]["toxicity"][0], out[11]["cmr"][0]
    assert "comp_cas" not in tox and tox["comp_name"] == "가상물질을" and tox["line"] == "p5:L8"
    assert "comp_name" not in cmr and "comp_cas" not in cmr and cmr["agency"] == "IARC"
    assert out[11]["narratives"] == [] and out[11]["extras"] == []          # 응답 최상위 칸은 모두 필수
    assert "last_revision_date" not in out[1]["meta"]
    assert out[1]["meta"]["lines"] == {"revision_no": "p1:L2"}
    assert out[3] == r[3]                                                   # 빈 칸이 없으면 그대로
    assert r == responses()                                                 # 입력은 바꾸지 않는다


@pytest.mark.parametrize("no", range(1, 17))
def test_omit_empty_follows_section_schema(no):
    assert validate(omit_empty(responses()[no], ss.response_schema(no)), ss.response_schema(no)) == []


def test_omit_empty_expands_to_same_document(no_conventions, monkeypatch):
    monkeypatch.setattr(ex, "now_kst", lambda: "2026-10-29T00:00:00+09:00")
    full = ex.to_to21(DOC_META, [responses()], LINES, "가상엔진 v1")
    omitted = ex.to_to21(DOC_META, [omitted_responses()], LINES, "가상엔진 v1")
    assert omitted == full
    assert validate_to21(omitted[0]) == []


def as_cell(v) -> str:
    """중간 형식 값 하나를 행 글 한 칸으로. 숫자 묶음은 raw, 서술 문장은 value를 '; '로 잇는다."""
    if v is None:
        return ""
    if isinstance(v, dict):
        return v["raw"]
    if isinstance(v, list):
        return "; ".join(x["value"] if isinstance(x, dict) else x for x in v)
    return str(v).lower() if isinstance(v, bool) else str(v)


def rows_text(no: int, response: dict) -> str:
    """JSON 응답과 같은 내용의 행 글 (ADR-019)."""
    out = []
    for name, cols in rw.row_tables(no).items():
        out += [f"### {name}", " | ".join(cols), *(" | ".join(as_cell(r.get(c)) for c in cols)
                                                  for r in response.get(name, []))]
    return "\n".join(out)


def test_rows_same_document_as_json(no_conventions, monkeypatch):
    """행 글을 parse_rows로 바꾼 11항은 같은 내용의 JSON 응답과 같은 TO21 문서로 펼쳐진다."""
    monkeypatch.setattr(ex, "now_kst", lambda: "2026-10-29T00:00:00+09:00")
    text = rows_text(11, responses()[11])
    assert "가상 독성 설명" in text and "> 2000 mg/kg" in text
    parsed, errors = rw.parse_rows(text, 11)
    assert errors == []
    assert validate(parsed, ss.response_schema(11)) == []
    assert parsed != responses()[11]                       # 빈 칸이 None으로 들어 있어 dict는 다르다
    by_json = ex.to_to21(DOC_META, [responses()], LINES, "가상엔진 v1")
    by_rows = ex.to_to21(DOC_META, [{**responses(), 11: parsed}], LINES, "가상엔진 v1")
    assert by_rows == by_json
    assert by_rows[0]["msds"][0]["toxicity"][0]["q"]["lower"] == 2000


def test_transport_rows_same_document_as_json(no_conventions, monkeypatch):
    """14항 운송 2행 글도 같은 내용의 JSON 응답과 같은 TO21 문서가 되고 un_no가 들어간다."""
    monkeypatch.setattr(ex, "now_kst", lambda: "2026-10-29T00:00:00+09:00")
    text = "\n".join([
        "### transport", " | ".join(rw.row_tables(14)["transport"]),
        "해상 |  | true | 9999 | 가상 액체 | 8 |  | II | 비해당 | F-A | S-B | p6:L5",
        "공통 |  | false |  |  |  |  | 해당없음 | 자료없음 |  |  | p6:L10"])
    parsed, errors = rw.parse_rows(text, 14)
    assert errors == []
    as_json = {"transport": [
        {"mode": "해상", "regulated": True, "un_no": "9999", "shipping_name": "가상 액체", "hazard_class": "8",
         "packing_group": "II", "marine_pollutant": "비해당", "ems_fire": "F-A", "ems_spill": "S-B",
         "line": "p6:L5"},
        {"mode": "공통", "regulated": False, "packing_group": "해당없음", "marine_pollutant": "자료없음",
         "line": "p6:L10"}], "narratives": [], "extras": []}
    r_json, r_rows = responses(), responses()
    r_json[14], r_rows[14] = as_json, parsed
    by_json = ex.to_to21(DOC_META, [r_json], LINES, "가상엔진 v1")
    by_rows = ex.to_to21(DOC_META, [r_rows], LINES, "가상엔진 v1")
    assert by_rows == by_json
    assert by_rows[0]["msds"][0]["transport"][0]["un_no"] == "9999"


def kreach(**kw) -> dict:
    return {"law": "KREACH", "item_code": "KREACH_REG", "line": "p6:L13", **kw}


def regulations_of(rows: list[dict]) -> list[dict]:
    r = responses()
    r[15]["regulations"] = rows
    doc, _ = ex.to_to21(DOC_META, [r], LINES, "가상엔진 v1")
    assert validate_to21(doc) == []
    return doc["msds"][0]["regulations"]


@pytest.mark.parametrize("text, code", [
    ("성상  기체  ECHA", "APPEARANCE_STATE"),                 # 칸을 공백으로 나눈 표
    (" ο 색상 : 무색", "APPEARANCE_COLOR"),
    ("가. 외관 (물리적 상태, 색 등) 액체", "APPEARANCE_STATE"),
    ("증기밀도  0.07", "VAPOR_DENSITY"),                       # '밀도'(RELATIVE_DENSITY)보다 긴 이름이 먼저
    ("인화 또는 폭발 범위의 상한/하한  4.0~76%", None),         # 묶음 표기(UEL+LEL)는 코드 하나가 아니다
    ("가상 추가 물성 1.20", None),
])
def test_physchem_code_from_dictionary(text, code):
    assert ex.physchem_code(text) == code


def test_physchem_code_exact_for_titles():
    assert ex.physchem_code("러. 점도", exact=True) == "VISCOSITY"
    assert ex.physchem_code("증기압 온도", exact=True) is None


def test_physchem_rows_relinked_by_dictionary(no_conventions):
    """동의어 사전(R25)에 있는 물성 이름은 부가 행이 아니라 물성 행이고, 코드가 빈 물성 행은 원문 줄의 이름으로 코드를 채운다."""
    r = responses()
    r[9]["physchem"].append({"prop_code": None, "text_value": "무색", "line": "p5:L2"})
    r[9]["extras"] += [{"title_raw": "점도", "reason": "코드없음", "q": {"raw": "7.5 mPa·s", "value": 7.5, "unit": "mPa·s"},
                        "statements": [], "line": "p5:L3"},
                       {"title_raw": "증기압 온도", "reason": "필드없음", "q": {"raw": "21", "value": 21},   # 제목은 이름 전체로 비교
                        "statements": [], "line": "p5:L5"},
                       {"title_raw": "용해도", "reason": "코드없음", "q": None, "statements": [], "line": "p5:L5"}]
    m, _ = expand_one(r)
    assert [(p["prop_code"], p["text_value"], (p["q"] or {}).get("value")) for p in m["physchem"]] == [
        ("FLASH_POINT", None, 60), ("APPEARANCE_COLOR", "무색", None), ("VISCOSITY", None, 7.5)]
    assert [e["title_raw"] for e in m["extras"]] == ["가상 추가 물성", "증기압 온도", "용해도"]   # 값 없는 행은 옮기지 않는다


def test_regulation_law_from_item_code(no_conventions):
    """규제 항목 코드는 법령 하나에 속하므로(명세서 5-6) 비어 있는 법령은 항목 코드에서 채운다."""
    regs = regulations_of([
        {"comp_name": None, "comp_cas": None, "law": None, "item_code": c, "applicable": "해당", "line": "p6:L10"}
        for c in ("INTL_US", "OSH_MEASURE", "KR_ETC", None)])
    assert [r["law"] for r in regs] == ["INTL", "OSH", "KR_ETC", None, "KREACH"]     # 끝은 R18 화평법 미기재 행


def test_applicable_kreach_with_value_becomes_haedang(no_conventions):
    """화평법 행에 값(value_raw 또는 threshold)이 있고 해당 여부가 비면 '해당' (사용자 결정 10/29, A-1 참고)."""
    regs = regulations_of([kreach(value_raw="가상-0001"),
                           kreach(threshold={"raw": "1 %", "value": 1, "unit": "%"}),
                           kreach(value_raw="CMR", applicable=None)])
    assert [x["applicable"] for x in regs] == ["해당", "해당", "해당"]


def test_applicable_no_value_or_other_law_unchanged(no_conventions):
    """값 없는 행, 이미 채워진 행, 다른 법령 행은 그대로다.
    '비해당'·'해당 없음' 값은 A의 답(10/30, A-1 예외 ①)으로 이제 '비해당'이 된다(예전 기대치 None)."""
    regs = regulations_of([kreach(),
                           kreach(value_raw="자료없음"),
                           kreach(value_raw="비해당"),
                           kreach(threshold={"raw": "해당 없음"}),
                           kreach(value_raw="가상-0002", applicable="비해당"),
                           {"law": "OSH", "item_code": "OSH_MEASURE", "value_raw": "가상", "line": "p6:L10"}])
    assert [x["applicable"] for x in regs] == [None, None, "비해당", "비해당", "비해당", None]


def test_kreach_negative_values_become_bihaedang(no_conventions):
    regs = regulations_of([kreach(value_raw="해당없음"),
                           kreach(value_raw="규제되지 않음"),
                           kreach(value_raw="Not applicable"),
                           kreach(value_raw="비위험물"),
                           kreach(value_raw="Unlisted"),
                           kreach(threshold={"raw": "해당 없음"})])
    assert [x["applicable"] for x in regs] == ["비해당"] * 6


def test_kreach_guidance_and_no_value_not_filled(no_conventions):
    regs = regulations_of([kreach(value_raw="공급자에게 문의할 것"),
                           kreach(value_raw="자료없음"),
                           kreach(value_raw="가상-0001")])
    assert [x["applicable"] for x in regs] == [None, None, "해당"]


def test_omit_empty_check_section_no_problems():
    ids = {l.id for l in LINES}
    assert {no: check_section(r, ids) for no, r in omitted_responses().items()} == {no: [] for no in range(1, 17)}


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


# ── 서술 구간 안의 extras (ADR-022) ────────────────────

NARR_LINES = [L(f"p3:L{i}", f"가상 독성 문장 {i}") for i in range(1, 13)]
EXTRA_IN = {"title_raw": "가. 소제목", "reason": "코드없음", "line": "p3:L4"}
EXTRA_OUT = {"title_raw": "비고", "reason": "필드없음", "line": "p3:L9"}


def expand_narr(extras_11=(), extras_12=(), start="p3:L2", end="p3:L6"):
    """11항 서술 구간 하나(start~end)와 11·12항 extras만 있는 가짜 MSDS를 펼친다. 다른 항은 빈 응답이다."""
    sections = {no: {} for no in range(1, 17)}
    sections[11] = {"narratives": [narr(11, start, end, "가. 독성 정보")], "extras": list(extras_11)}
    sections[12] = {"extras": list(extras_12)}
    return ex.expand_msds(sections, line_index(NARR_LINES), 0, "텍스트층")


def kinds(problems, kind="extras_in_narrative"):
    return [p for p in problems if p["kind"] == kind]


def test_extras_in_narrative_dropped(no_conventions):
    m, problems = expand_narr(extras_11=[EXTRA_IN, EXTRA_OUT])
    assert [(e["seq"], e["section_no"], e["title_raw"]) for e in m["extras"]] == [(1, 11, "비고")]
    assert kinds(problems) == [{"msds_index": 0, "section": 11, "kind": "extras_in_narrative", "detail": "1행"}]
    # 뺀 행은 근거도 남지 않고, 남은 행의 근거가 extras[0]이다
    extras_ev = [e for e in m["evidence"] if e["field"].startswith("extras")]
    assert [(e["field"], e["source_text"]) for e in extras_ev] == [("extras[0]", "가상 독성 문장 9")]
    # 서술 문장은 그대로다
    assert [s["text"] for s in m["narratives"][0]["statements"]] == [f"가상 독성 문장 {i}" for i in range(2, 7)]


def test_extras_in_narrative_bounds_inclusive(no_conventions):
    """구간 양 끝 줄은 거르고, 바로 바깥 줄은 남긴다."""
    rows = [{**EXTRA_IN, "title_raw": lid, "line": lid} for lid in ("p3:L1", "p3:L2", "p3:L6", "p3:L7")]
    m, problems = expand_narr(extras_11=rows)
    assert [e["title_raw"] for e in m["extras"]] == ["p3:L1", "p3:L7"]
    assert [p["detail"] for p in kinds(problems)] == ["2행"]


def test_extras_in_narrative_other_section_kept(no_conventions):
    """12항 extras가 11항 서술 구간 안의 줄을 가리켜도 남긴다."""
    m, problems = expand_narr(extras_12=[EXTRA_IN])
    assert [(e["section_no"], e["title_raw"]) for e in m["extras"]] == [(12, "가. 소제목")]
    assert kinds(problems) == []


@pytest.mark.parametrize("start, end, kind", [("p3:L6", "p3:L2", "bad_range"), ("p3:L2", "p3:L99", "bad_line")])
def test_extras_in_narrative_ignores_bad_span(no_conventions, start, end, kind):
    """구간이 잘못된 서술 행은 거르기에 쓰지 않는다."""
    m, problems = expand_narr(extras_11=[EXTRA_IN], start=start, end=end)
    assert [e["title_raw"] for e in m["extras"]] == ["가. 소제목"]
    assert [p["kind"] for p in problems] == [kind]


def test_extras_in_narrative_unknown_line_kept(no_conventions):
    """원문에 없는 줄을 가리키는 extras는 지금처럼 남기고 bad_line으로 센다."""
    m, problems = expand_narr(extras_11=[{**EXTRA_IN, "line": "p9:L99"}])
    assert [e["title_raw"] for e in m["extras"]] == ["가. 소제목"]
    assert [(p["kind"], p["detail"]) for p in problems] == [("bad_line", "extras[0]: p9:L99")]


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


def test_single_component_unnamed_rows_point_to_it(no_conventions):
    """성분이 하나면 성분 표기 없는 11·12·15항 행은 그 성분이다 (명세서 1_항목정의 예시 '1'). 물성·부가행은 제품 값이라 MIX."""
    r = responses()
    r[3]["components"] = r[3]["components"][:1]
    m, _ = expand_one(r)
    assert m["cmr"][0]["comp_ref"] == "1"
    assert m["physchem"][0]["comp_ref"] == "MIX"
    assert m["extras"][0]["comp_ref"] == "MIX"


def test_single_component_exposure_and_product_laws(no_conventions):
    """성분이 하나면 성분 표기 없는 8항 노출기준도 그 성분이다 (R10, 1_항목정의 예시 '1').
    15항의 위험물·폐기물 행은 제품 단위라 MIX로 둔다 (1_항목정의 예시, TO21 정합성 설계서 v0.4 29·40장)."""
    r = responses()
    r[3]["components"] = r[3]["components"][:1]
    r[8]["exposure_limits"][0]["comp_cas"] = None
    r[15]["regulations"] += [
        {"comp_name": None, "comp_cas": None, "law": law, "item_code": code, "applicable": "비해당", "line": line}
        for law, code, line in (("OSH", "OSH_PSM", "p2:L5"), ("DG", "DG_HAZMAT", "p6:L10"),
                                (None, "WASTE_DESIG", "p6:L10"))]   # 법령이 비면 항목 코드로. 근거 범위(p2~p6)에 성분이 나온다
    m, _ = expand_one(r)
    assert m["exposure_limits"][0]["comp_ref"] == "1"
    assert [(x["item_code"], x["comp_ref"]) for x in m["regulations"]] == [
        ("OSH_MEASURE", "1"), ("OSH_PSM", "1"), ("DG_HAZMAT", "MIX"), ("WASTE_DESIG", "MIX"), (None, "MIX")]   # 끝은 R18 행


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


@pytest.mark.parametrize("raw, status, note", [
    ("해당없음(불연성)", "해당없음", "불연성"),          # TO21 예제 25 FLASH_POINT
    ("No data available", "자료없음", None),            # 동의어 사전 status
    ("N/A", "해당없음", None),
    ("-", "미기재", None),                              # R15
    ("판독불가", "판독불가", None),                      # C7
])
def test_fill_q_status_word(raw, status, note):
    q = ex.fill_q({"raw": raw})
    assert (q["raw"], q["status"], q["note"], q["value"]) == (raw, status, note, None)


def test_status_text_value_moves_to_q(no_conventions):
    """값 대신 상태어만 적힌 행은 text_value가 아니라 q의 상태다 (TO21 예제 25 FLAMMABILITY, 2_공통구조 Q.status)."""
    r = responses()
    r[9]["physchem"] += [{"prop_code": "FLAMMABILITY", "text_value": "해당없음", "line": "p5:L1"},
                         {"prop_code": "APPEARANCE_COLOR", "text_value": "무색", "line": "p5:L1"},
                         {"prop_code": "PH", "data_source": "자료없음", "line": "p5:L1"}]   # 칸이 밀려 출처에 적힘
    m, _ = expand_one(r)
    flam, color, ph = m["physchem"][1:]
    assert flam["text_value"] is None and (flam["q"]["raw"], flam["q"]["status"]) == ("해당없음", "해당없음")
    assert color["text_value"] == "무색" and color["q"] is None
    assert ph["data_source"] is None and ph["q"]["status"] == "자료없음"


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


def test_link_components_drops_trailing_qualifier():
    """'NATURAL GAS, LIQUIFIED'처럼 쉼표·괄호 뒤 수식어가 붙은 이름은 수식어를 떼고 다시 비교한다.
    공백으로 이어진 이름은 다른 물질일 수 있어 떼지 않는다."""
    rows = [{"comp_name": "가상물질 갑, 액화", "comp_cas": None},
            {"comp_name": "가상물질 을 (98%)", "comp_cas": None},
            {"comp_name": "가상물질 갑 염", "comp_cas": None}]
    assert [r["comp_ref"] for r in ex.link_components(rows, COMPS)] == ["1", "2", "MIX"]


def test_link_components_from_source_line():
    """성분 표기가 빈 행은 근거 줄에 성분 이름·CAS가 하나만 보이면 그 성분이다 ('- 이소부텐 : 자료없음' 꼴 목록).
    둘 이상 보이거나 하나도 없으면 MIX. 이름이 다른 이름에 들어 있으면 긴 이름만 센다."""
    comps = [*COMPS, {"seq": 3, "name": "가상물질 을 염", "cas_no": None}]
    lines = {x.id: x for x in [L("p9:L1", "- 가상물질 을 : 자료없음"), L("p9:L2", "- 1234-56-6 : 해당없음"),
                               L("p9:L3", "가상물질 갑, 가상물질 을 : 자료없음"), L("p9:L4", "PRODUCT : 자료없음"),
                               L("p9:L5", "- 가상물질 을 염 : 자료없음")]}
    rows = [{"comp_name": None, "comp_cas": None, "line": f"p9:L{i}"} for i in range(1, 6)]
    rows.append({"comp_name": "PRODUCT", "comp_cas": None, "line": "p9:L1"})   # 적힌 이름이 있으면 줄을 보지 않는다
    assert [r["comp_ref"] for r in ex.link_components(rows, comps, lines)] == ["2", "1", "MIX", "MIX", "3", "MIX"]


# ── 11항 CMR·중복 행 ────────────────────────────────────

@pytest.mark.parametrize("raw, want", [
    ("구분 1B", ("1B", None)), ("구분1A", ("1A", None)), ("생식세포변이원성 1B", ("1B", None)),
    ("발암성 : 구분 2", ("2", None)), ("해당없음", (None, "해당없음")), ("해당 없음", (None, "해당없음")),
    ("자료없음", (None, "자료없음")), ("Group 1", ("Group 1", None)), ("Carc. 1A", ("Carc. 1A", None)),
    ("A2", ("A2", None)), ("분류되지않음", ("분류되지않음", None))])
def test_fix_cmr_class(raw, want):
    """CMR 등급은 '구분'과 유해성 이름을 뺀 기관 표기다 (R07). 상태어(C7)만 적혔으면 등급을 비우고 status로 옮긴다."""
    r = {"hazard": "발암성", "agency": "KR_OSH", "class": raw, "status": "값있음"}
    ex.fix_cmr_class([r])
    assert (r["class"], r["status"] if want[1] else None) == want


def test_repeated_rows_with_same_line_are_dropped(no_conventions):
    """원문 줄까지 같은 행은 모델이 반복한 것이라 하나만 남긴다. 줄이 다르면 같은 내용이어도 남긴다."""
    r = responses()
    row = r[11]["cmr"][0]
    r[11]["cmr"] += [dict(row), dict(row), {**row, "line": "p5:L8"}]
    m, _ = expand_one(r)
    assert len(m["cmr"]) == 2


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


def test_to_to21_applies_source_rules_before_conventions(monkeypatch):
    """펼친 뒤 원문 대조 규칙(source_rules)을 부르고, 그 다음에 A의 함수를 부른다 (ADR-029).
    가짜 줄에 H코드 꼴이 없으므로 모델이 쓴 H코드는 비고 문장은 남는다."""
    name = "msds.common.conventions"
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader=None))
    seen = []
    mod.apply = lambda m: seen.append([s["code"] for s in m["hazard"]["h_statements"]]) or m
    monkeypatch.setitem(sys.modules, name, mod)
    r = responses()
    r[2]["hazard"]["h_statements"] = [{"code": "H319", "text": "눈에 심한 자극을 일으킴", "line": "p1:L20"}]
    assert validate(r[2], ss.response_schema(2)) == []
    doc, _ = ex.to_to21(DOC_META, [r], LINES, "e")
    h = doc["msds"][0]["hazard"]["h_statements"]
    assert [(s["code"], s["text"]) for s in h] == [(None, "눈에 심한 자극을 일으킴")]
    assert seen == [[None]]


def test_module_without_apply_is_ignored(monkeypatch):
    name = "msds.common.conventions"
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader=None))
    monkeypatch.setitem(sys.modules, name, mod)
    item = {"meta": {}}
    assert ex.apply_conventions(item) is item


def test_rows_physchem_no_value_expands_to_q_status(no_conventions, monkeypatch):
    """행 형식 9항의 text_value 자료없음은 q.status 자료없음이 되고 text_value는 null이다."""
    monkeypatch.setattr(ex, "now_kst", lambda: "2026-10-29T00:00:00+09:00")
    text = "\n".join(["### physchem", " | ".join(rw.row_tables(9)["physchem"]),
                      "ODOR_THRESHOLD |  |  |  | 자료없음 |  |  | p3:L2"])
    parsed, errors = rw.parse_rows(text, 9)
    assert errors == []
    doc = ex.to_to21(DOC_META, [{**responses(), 9: parsed}], LINES, "가상엔진 v1")
    row = next(r for r in doc[0]["msds"][0]["physchem"] if r["prop_code"] == "ODOR_THRESHOLD")
    assert row["q"]["status"] == "자료없음" and row["text_value"] is None


def test_link_components_from_parent_line():
    """근거 줄에 성분이 없으면 부모 줄('- 가상물질 을 : 구분 1A' 아래 '· IARC : 2A')에서 찾는다. 가까운 부모부터 보고,
    성분이 보이는 첫 부모에서 하나면 그 성분, 둘 이상이면 MIX."""
    texts = ["○ 발암성 PRODUCT : 구분 1A", "- 가상물질 을 : 구분 1A", "· IARC : 2A",
             "○ 생식독성 : 가상물질 갑, 가상물질 을", "· IARC : 해당없음", "· 자료없음"]
    lines = {f"p9:L{i}": L(f"p9:L{i}", t) for i, t in enumerate(texts, 1)}
    rows = [{"comp_name": None, "comp_cas": None, "line": f"p9:L{i}"} for i in (3, 5, 1)]
    assert [r["comp_ref"] for r in ex.link_components(rows, COMPS, lines)] == ["2", "MIX", "MIX"]


def test_link_components_short_name_needs_word_edges():
    """두 글자 이하 이름은 앞뒤에 글자가 없을 때만 줄에서 찾는다. '물'은 '유독물질'·'물벼룩'에도 들어 있다."""
    comps = [{"seq": 1, "name": "물", "cas_no": None}, {"seq": 2, "name": "가상물질 갑", "cas_no": None},
             {"seq": 3, "name": "Ag", "cas_no": None}]
    lines = {x.id: x for x in [L("p9:L1", "유독물질 : 해당없음"), L("p9:L2", "물벼룩 EC50 : 자료없음"),
                               L("p9:L3", "- 물 : 자료없음"), L("p9:L4", "Agency : 자료없음"),
                               L("p9:L5", "- Ag : 자료없음"), L("p9:L6", "- 가상물질 갑 : 자료없음")]}
    rows = [{"comp_name": None, "comp_cas": None, "line": f"p9:L{i}"} for i in range(1, 7)]
    assert [r["comp_ref"] for r in ex.link_components(rows, comps, lines)] == ["MIX", "MIX", "1", "MIX", "3", "2"]


def test_short_name_inside_word_does_not_stop_parent_search():
    """줄 안 낱말에 든 짧은 이름 때문에 부모 줄 찾기를 멈추지 않는다."""
    comps = [{"seq": 1, "name": "물", "cas_no": None}, {"seq": 2, "name": "가상물질 갑", "cas_no": None}]
    lines = {x.id: x for x in [L("p9:L1", "- 가상물질 갑 : 구분 1A"), L("p9:L2", "· 유독물질 : 해당")]}
    rows = [{"comp_name": None, "comp_cas": None, "line": "p9:L2"}]
    assert ex.link_components(rows, comps, lines)[0]["comp_ref"] == "2"


def test_toxicity_descriptor_cleared_without_value(no_conventions):
    """숫자가 없는 독성 행의 지표는 상태와 관계없이 '결과기술'이다. 혼합물 급성의 값 없는 행도 같다
    (개발 골드 10건의 숫자 없는 독성 261행 모두. A 규칙의 'ATE'는 예제 1건에서 온 기본값이다).
    숫자가 있는 행의 지표는 그대로 둔다. 설명만 있는 행(값있음)의 q는 비우고, q에만 적힌 글은 statements로 옮긴다
    (골드 135행 모두 q 없음)."""
    r = responses()
    r[11]["toxicity"] += [
        {"comp_name": "가상물질 을", "comp_cas": None, "endpoint": "TX_DERMAL", "descriptor": "LD50", "status": "자료없음",
         "species": None, "q": {"raw": "자료없음"}, "statements": [], "line": "p5:L8"},
        {"comp_name": "가상물질 을", "comp_cas": None, "endpoint": "TX_SKIN", "descriptor": "Draize", "status": "값있음",
         "species": None, "q": None, "statements": [{"value": "비자극성", "line": "p5:L8"}], "line": "p5:L8"}]
    r[11]["toxicity"].append({"comp_name": "가상물질 을", "comp_cas": None, "endpoint": "TX_EYE", "descriptor": None,
                              "status": "값있음", "species": None, "q": {"raw": "가상 자극 없음"}, "statements": [],
                              "line": "p5:L8"})
    m, _ = expand_one(r)
    assert [x["descriptor"] for x in m["toxicity"]] == ["LD50", "결과기술", "결과기술", "결과기술"]
    assert m["toxicity"][2]["q"] is None and m["toxicity"][3]["q"] is None
    assert [s["value"] for s in m["toxicity"][3]["statements"]] == ["가상 자극 없음"]
    assert m["toxicity"][1]["q"]["status"] == "자료없음"                 # 값 없는 행의 q(상태)는 둔다



# ── 9항 폭발 범위(UEL·LEL)와 빈 값 ─────────────────────

def phys_rows(r9_physchem, no_conv=True):
    r = responses()
    r[9]["physchem"] = r9_physchem
    m, _ = expand_one(r)
    return [(x["prop_code"], (x["q"] or {}).get("value"), (x["q"] or {}).get("unit"), (x["q"] or {}).get("status"),
             (x["q"] or {}).get("lower"), (x["q"] or {}).get("upper")) for x in m["physchem"]]


@pytest.mark.parametrize("row, want", [
    ({"prop_code": None, "q": {"raw": "4.0~76%", "lower_op": ">=", "lower": 4.0, "upper_op": "<=", "upper": 76, "unit": "%"},
      "line": "p5:L12"}, [("UEL", 76, "%", "값있음", None, None), ("LEL", 4.0, "%", "값있음", None, None)]),
    ({"prop_code": "UEL", "q": {"raw": "75 / 4 %", "value": 75, "unit": "/ 4 %"}, "line": "p5:L14"},
     [("UEL", 75, "%", "값있음", None, None), ("LEL", 4, "%", "값있음", None, None)]),
    ({"prop_code": None, "q": {"raw": "자료없음"}, "line": "p5:L15"},
     [("UEL", None, None, "자료없음", None, None), ("LEL", None, None, "자료없음", None, None)]),
])
def test_flammability_range_split_into_uel_lel(no_conventions, row, want):
    """폭발 범위 상한/하한 한 줄은 UEL·LEL 두 행이다. UEL은 큰 숫자, LEL은 작은 숫자를 단일값으로 두고 원문 표기는
    raw에 둔다(골드·실버 6건과 TO21 재생성 도구의 '상한/하한 X / Y' 표기). 상태어만 있으면 두 행 모두 그 상태다."""
    assert phys_rows([row]) == want


def test_flammability_rows_on_separate_lines_unchanged(no_conventions):
    rows = [{"prop_code": "UEL", "q": {"raw": "8.0vol%", "value": 8.0, "unit": "vol%"}, "line": "p5:L16"},
            {"prop_code": "LEL", "q": {"raw": "1.2vol%", "value": 1.2, "unit": "vol%"}, "line": "p5:L17"}]
    assert phys_rows(rows) == [("UEL", 8.0, "vol%", "값있음", None, None), ("LEL", 1.2, "vol%", "값있음", None, None)]


def test_split_pair_replaces_both_model_rows_on_same_line(no_conventions):
    """모델이 같은 줄로 UEL·LEL을 모두 범위로 썼어도 두 행만 남는다."""
    q = {"raw": "4.0~76%", "lower_op": ">=", "lower": 4.0, "upper_op": "<=", "upper": 76, "unit": "%"}
    rows = [{"prop_code": "UEL", "q": q, "line": "p5:L12"}, {"prop_code": "LEL", "q": q, "line": "p5:L12"}]
    assert phys_rows(rows) == [("UEL", 76, "%", "값있음", None, None), ("LEL", 4.0, "%", "값있음", None, None)]


def test_blank_physchem_value_filled_from_line_status(no_conventions):
    """값·글자가 모두 빈 물성 행은 근거 줄에서 이름 다음 칸이 상태어면 그 상태다 ('인화점 | 자료없음 | 자료없음').
    상태어가 아닌 값(숫자 등)은 채우지 않는다."""
    rows = [{"prop_code": "FLASH_POINT", "line": "p5:L13"}, {"prop_code": "PH", "line": "p5:L18"}]
    assert phys_rows(rows) == [("FLASH_POINT", None, None, "자료없음", None, None), ("PH", None, None, None, None, None)]


def test_lone_flammability_status_row_gets_partner(no_conventions):
    """UEL만 있고 상태어뿐이면 LEL도 같은 상태다(골드의 상태어 행은 두 행이 같다). 숫자 하나뿐인 행은 짝을 만들지 않는다."""
    assert phys_rows([{"prop_code": "UEL", "q": {"raw": "해당 없음"}, "line": "p5:L18"}]) == [
        ("UEL", None, None, "해당없음", None, None), ("LEL", None, None, "해당없음", None, None)]
    assert phys_rows([{"prop_code": "UEL", "q": {"raw": "8.0vol%", "value": 8.0, "unit": "vol%"}, "line": "p5:L16"}]) == [
        ("UEL", 8.0, "vol%", "값있음", None, None)]


@pytest.mark.parametrize("raw, unit", [("인화 상한값 15 %(V) 인화 하한값 5 %(V)", "%(V)"), ("1.6 ~ 12% (volume in air)", "%"),
                                       ("8.0vol%/1.2vol%", "vol%"), ("1.4 ~ 11.7", None)])
def test_flammability_pair_unit(raw, unit):
    """단위는 마지막 숫자 뒤 표기다. 공백 뒤 괄호 설명은 떼고, 붙은 괄호(%(V))는 둔다 (골드 M001·M005·S016·M004)."""
    uel, lel = ex._flammability_pair(raw)
    assert uel["unit"] == unit == lel["unit"] and uel["value"] > lel["value"]


def test_biological_exposure_limit_is_bei(no_conventions):
    """8항 생물학적 노출기준은 기준 종류가 늘 BEI다 (골드·실버 33행 모두). 모델이 '기타'로 쓴 일이 있었다."""
    r = responses()
    r[8]["exposure_limits"] = [{"comp_name": None, "comp_cas": "1234-56-6", "standard": "생물학적", "limit_type": "기타",
                                "q": {"raw": "25 ㎍/g", "value": 25, "unit": "ug/g"}, "line": "p4:L3"}]
    m, _ = expand_one(r)
    assert m["exposure_limits"][0]["limit_type"] == "BEI"


# ── 8항 두 단위 값·단순 질식제, 3항 합계 행 ───────────────

def el_rows(r8, conventions=False):
    r = responses()
    r[8]["exposure_limits"] = r8
    m, _ = expand_one(r)
    return [(x["standard"], x["limit_type"], (x["q"] or {}).get("value"), (x["q"] or {}).get("unit"), (x["q"] or {}).get("status"))
            for x in m["exposure_limits"]]


@pytest.mark.parametrize("raw", ["0.5 ppm (1.6 mg/m3)", "0.5 ppm (1.6 mg/m3"])
def test_exposure_value_with_second_unit_split(no_conventions, raw):
    """'0.5 ppm (1.6 mg/m3)'는 단위마다 한 행이다 (골드 S016, 실버 M002). 닫는 괄호가 빠져도 같다."""
    row = {"comp_name": None, "comp_cas": "1234-56-6", "standard": "ACGIH", "limit_type": "TWA",
           "q": {"raw": raw, "value": 0.5, "unit": "ppm"}, "line": "p4:L3"}
    assert el_rows([row]) == [("ACGIH", "TWA", 0.5, "ppm", "값있음"), ("ACGIH", "TWA", 1.6, "mg/m3", "값있음")]


def test_simple_asphyxiant_is_not_applicable(no_conventions):
    """값이 '단순 질식제'뿐이면 수치 기준이 없는 것이라 상태는 해당없음이다 (골드 S003, 실버 S001·S003)."""
    row = {"comp_name": None, "comp_cas": "1234-56-6", "standard": "ACGIH", "limit_type": None,
           "q": {"raw": "단순 질식제"}, "line": "p4:L3"}
    assert el_rows([row]) == [("ACGIH", None, None, None, "해당없음")]


def test_total_component_row_is_dropped(no_conventions):
    """성분표의 합계 행('Total | 100%')은 성분이 아니다. 골드·실버에 없고, 남기면 단일 성분 문서가 두 성분이 된다 (S001)."""
    r = responses()
    r[3]["components"] = r[3]["components"][:1] + [{"name": "Total", "cas_no": None, "content": {"raw": "100%", "value": 100, "unit": "%"},
                                                    "line": "p2:L6"}]
    r[8]["exposure_limits"][0]["comp_cas"] = None
    m, _ = expand_one(r)
    assert [c["name"] for c in m["components"]] == ["가상물질 갑"] and m["exposure_limits"][0]["comp_ref"] == "1"


def test_exposure_value_none_word_is_not_applicable(no_conventions):
    """노출기준 표의 '없음'은 기준이 없다는 뜻이라 해당없음이다 (골드 S013)."""
    row = {"comp_name": None, "comp_cas": "1234-56-6", "standard": "국내", "limit_type": None, "q": {"raw": "없음"}, "line": "p4:L3"}
    assert el_rows([row]) == [("국내", None, None, None, "해당없음")]


def test_empty_component_row_is_dropped(no_conventions):
    """이름도 CAS도 없는 성분 행은 버린다. 남기면 단일 성분 문서가 두 성분이 된다 (S001). 골드·실버에 이런 행은 없다."""
    r = responses()
    r[3]["components"] = r[3]["components"][:1] + [{"name": None, "cas_no": None, "line": "p2:L6"}]
    r[8]["exposure_limits"][0]["comp_cas"] = None
    m, _ = expand_one(r)
    assert len(m["components"]) == 1 and m["exposure_limits"][0]["comp_ref"] == "1"


def test_single_component_regulations_mix_when_section_never_names_it(no_conventions):
    """성분이 하나여도 15항 원문(규제 행 근거 줄의 범위)에 그 성분 이름·CAS가 한 번도 없으면 15항 행은 제품 값(MIX)이다
    (골드 S001·S003: 법령 단위 '화학물질관리법에 의한 규제 : 해당 없음'). 성분이 나오면 성분 번호다 (골드 S014·S016)."""
    r = responses()
    r[3]["components"] = r[3]["components"][:1]
    r[15]["regulations"] = [{"comp_name": None, "comp_cas": None, "law": "OSH", "item_code": "OSH_MEASURE",
                             "applicable": "해당", "line": "p6:L10"}]
    m, _ = expand_one(r)
    assert m["regulations"][0]["comp_ref"] == "MIX"                 # p6:L10 '작업환경측정대상물질 : 해당'
    r[15]["regulations"][0]["line"] = "p2:L5"                        # '가상물질 갑 | 1234-56-6 | 10 ~ 20'
    m, _ = expand_one(r)
    assert m["regulations"][0]["comp_ref"] == "1"



def reg_rows(r15, single=True):
    r = responses()
    if single:
        r[3]["components"] = r[3]["components"][:1]
    r[15]["regulations"] = r15
    m, _ = expand_one(r)
    return [(x["law"], x["item_code"], x["applicable"], x["comp_ref"]) for x in m["regulations"]]


def test_kreach_unrecorded_row_added_when_absent(no_conventions):
    """화평법 행이 하나도 없으면 'KREACH / 코드 없음 / 미기재 / MIX' 행을 하나 더한다 (R18, 골드 6건 모두).
    화평법 행이 있으면 더하지 않는다."""
    row = {"comp_name": "가상물질 갑", "comp_cas": None, "law": "OSH", "item_code": "OSH_MEASURE", "applicable": "해당", "line": "p6:L10"}
    assert reg_rows([row], single=False) == [("OSH", "OSH_MEASURE", "해당", "1"), ("KREACH", None, "미기재", "MIX")]
    kreach = {**row, "law": "KREACH", "item_code": "KREACH_REG", "line": "p6:L13"}
    assert [x[0] for x in reg_rows([row, kreach], single=False)] == ["OSH", "KREACH"]


def test_single_component_regulations_mix_even_if_model_names_component(no_conventions):
    """15항 원문에 성분이 나오지 않으면 모델이 성분 칸에 적었어도 MIX다. 원문에 근거가 없는 성분 지정이다 (골드 S003)."""
    row = {"comp_name": "가상물질 갑", "comp_cas": "1234-56-6", "law": "CCA", "item_code": "CCA_TOXIC", "applicable": "비해당",
           "line": "p6:L11"}
    assert reg_rows([row])[0][3] == "MIX"


@pytest.mark.parametrize("line", ["p6:L11", "p6:L12"])
def test_law_level_line_has_no_item_code(no_conventions, line):
    """근거 줄이 '○○법에 의한 규제 : 해당 없음'처럼 법령 단위면 산안법·화관법·화평법 행의 항목 코드를 비운다 (골드 S001·S003).
    위험물·폐기물은 코드를 둔다."""
    rows = [{"comp_name": None, "comp_cas": None, "law": "CCA", "item_code": "CCA_PRTR", "applicable": "비해당", "line": line},
            {"comp_name": None, "comp_cas": None, "law": "DG", "item_code": "DG_HAZMAT", "applicable": "비해당", "line": line}]
    out = reg_rows(rows)
    assert (out[0][1], out[1][1]) == (None, "DG_HAZMAT")


def test_cmr_rows_without_agency_dropped(no_conventions):
    """기관이 빈 CMR 행은 CMR에서 빼고 독성 행으로 옮긴다. 'PRODUCT : 분류되지않음', '발암성 : 자료없음' 같은 제품·항목 줄이라 기관 분류가 아니다
    (개발 골드 10건의 CMR 61행은 모두 기관이 있다. 그 내용은 독성 표의 발암성 등에 있다)."""
    r = responses()
    r[11]["cmr"] = [
        {"comp_name": None, "comp_cas": None, "hazard": "발암성", "agency": None, "class": None, "status": "자료없음",
         "note": None, "line": "p5:L9"},
        {"comp_name": "가상물질 갑", "comp_cas": "1234-56-6", "hazard": "발암성", "agency": "IARC", "class": "Group 3",
         "status": "값있음", "note": None, "line": "p5:L9"}]
    r[11]["cmr"].append({"comp_name": "가상물질 을", "comp_cas": None, "hazard": "생식세포변이원성", "agency": None, "class": None,
                         "status": "값있음", "note": "가상 음성 결과", "line": "p5:L8"})
    m, _ = expand_one(r)
    assert [(x["agency"], x["class"]) for x in m["cmr"]] == [("IARC", "Group 3")]
    assert [e["field"] for e in m["evidence"] if e["field"].startswith("cmr")] == ["cmr[0]"]
    # 기관 없는 행은 독성 행으로 옮긴다 (골드 S013 'Methane : 음성 …' → TX_MUTA, '자료없음' → TX_CARC 자료없음)
    moved = [(x["endpoint"], x["status"], [s["value"] for s in x["statements"]]) for x in m["toxicity"]
             if x["endpoint"] in ("TX_CARC", "TX_MUTA")]
    assert moved == [("TX_CARC", "자료없음", []), ("TX_MUTA", "값있음", ["가상 음성 결과"])]


@pytest.mark.parametrize("line, want", [("p5:L10", "2B"), ("p5:L9", "Group 2B")])
def test_cmr_group_prefix_only_when_written(no_conventions, line, want):
    """CMR 등급은 원문 표기대로다. 근거 줄('IARC 3군')에 'Group'이 없는데 모델이 붙였으면 뗀다
    (골드 M013 '2B' / S016 'Group 1'). 근거 줄을 모르면(p5:L9 없음) 그대로 둔다."""
    r = responses()
    r[11]["cmr"] = [{"comp_name": "가상물질 갑", "comp_cas": "1234-56-6", "hazard": "발암성", "agency": "IARC",
                     "class": "Group 2B", "status": "값있음", "note": None, "line": line}]
    m, _ = expand_one(r)
    assert m["cmr"][0]["class"] == want


@pytest.mark.parametrize("line, want", [("p5:L8", "2"), ("p6:L10", "2"), ("p2:L5", "1")])
def test_link_name_and_cas_disagree(line, want):
    """이름과 CAS가 서로 다른 성분을 가리키면 근거 줄에 적힌 쪽을 따르고, 둘 다 안 적혔으면 이름을 따른다.
    모델이 '1,3 부타디엔 | 106-97-8'(부탄의 CAS)처럼 맞는 이름에 다른 성분의 CAS를 붙였다 (M004, 실행 8개 372행)."""
    comps = [{"seq": 1, "name": "가상물질 갑", "cas_no": "1234-56-6"}, {"seq": 2, "name": "가상물질 을", "cas_no": "2345-67-7"}]
    lines = {l.id: l for l in LINES}
    row = {"comp_name": "가상물질 을", "comp_cas": "1234-56-6", "line": line}
    assert ex.link_components([row], comps, lines)[0]["comp_ref"] == want


@pytest.mark.parametrize("line, want", [("p6:L10", ["MIX"]), ("p2:L5", ["1", "2"])])
def test_unnamed_line_rows_per_component_collapse_to_mix(no_conventions, line, want):
    """근거 줄·부모 줄에 성분이 없는데 성분만 다르고 나머지가 같은 11·12항 행이 여럿이면 MIX 한 행이다
    (골드: 성분 없는 줄의 독성·CMR·생태 행은 모두 MIX 한 행. M002 'ο 발암성 : 자료없음'을 모델이 성분마다 복제했다).
    줄에 성분이 보이면 그대로 둔다."""
    r = responses()
    r[11]["cmr"] = [{"comp_name": n, "comp_cas": None, "hazard": "발암성", "agency": "IARC", "class": None,
                     "status": "해당없음", "note": None, "line": line} for n in ("가상물질 갑", "가상물질 을")]
    m, _ = expand_one(r)
    assert [x["comp_ref"] for x in m["cmr"]] == want


# ── 11·12항 extras → 독성·생태 행 (모델이 서술 행을 extras로 보냄) ─────

X_LINES = [L("p9:L1", "나. 건강 유해성 정보"),
           L("p9:L2", "o 피부 과민성 알레르기성 피부 반응을 일으킬 수 있음."),
           L("p9:L3", "○ 발암성물질"),
           L("p9:L4", "○ 생식독성"),
           L("p9:L5", "  - 가상물질 을 : 자료없음"),
           L("p9:L6", "라.토양이동성 자료없음"),
           L("p9:L7", "* 경피 독성"),
           L("p9:L8", "가.생분해성 : 자료 없음")]


def x_rows(extras):
    lines = {l.id: l for l in X_LINES}
    moved, left = ex.extras_to_rows(extras, lines)
    return {k: [(no, r["endpoint"], r["status"], r.get("comp_name"), (r.get("statements") or [{}])[0].get("value"))
                for no, r in v] for k, v in moved.items()}, left


def test_extras_to_rows_heading_lines():
    """원문 줄이 독성·생태 항목명으로 시작하고 뒤에 값이 있으면 그 표의 서술 행으로 옮긴다 (M013 'o 피부 과민성 …').
    값이 상태어 하나면 그 상태, 아니면 값있음. 제목만 있는 줄('○ 발암성물질', '* 경피 독성')과 생분해성은 옮기지 않는다."""
    ext = [(11, {"title_raw": "o 피부 과민성 알레르기성 피부 반응을 일으킬 수 있음.", "reason": "코드없음", "line": "p9:L2"}),
           (11, {"title_raw": "○ 발암성물질", "reason": "코드없음", "line": "p9:L3"}),
           (11, {"title_raw": "* 경피 독성", "reason": "코드없음", "line": "p9:L7"}),
           (12, {"title_raw": "라.토양이동성", "reason": "코드없음", "line": "p9:L6"}),
           (12, {"title_raw": "가.생분해성", "reason": "코드없음", "line": "p9:L8"})]
    moved, left = x_rows(ext)
    assert moved["toxicity"] == [(11, "TX_SKIN_SENS", "값있음", None, "알레르기성 피부 반응을 일으킬 수 있음.")]
    assert moved["ecotox"] == [(12, "ECO_SOIL", "자료없음", None, None)]
    assert [r["line"] for _, r in left] == ["p9:L3", "p9:L7", "p9:L8"]


def test_extras_to_rows_component_under_heading():
    """제목이 성분인 extras('- 가상물질 을 : 자료없음')는 부모 줄의 항목명으로 옮기고 성분을 둔다."""
    ext = [(11, {"title_raw": "- 가상물질 을", "reason": "코드없음", "comp_name": "가상물질 을",
                 "statements": [{"value": "자료없음", "line": "p9:L5"}], "line": "p9:L5"})]
    moved, left = x_rows(ext)
    assert moved["toxicity"] == [(11, "TX_REPRO", "자료없음", "가상물질 을", None)] and left == []


def test_extras_to_rows_skips_other_sections():
    ext = [(9, {"title_raw": "o 피부 과민성 알레르기성", "reason": "코드없음", "line": "p9:L2"})]
    moved, left = x_rows(ext)
    assert moved == {"toxicity": [], "ecotox": []} and len(left) == 1



def test_extras_to_rows_ecotox_only_status_values():
    """생태는 값이 상태어 하나일 때만 옮긴다 ('잔류성 및 분해성'의 '및 분해성'을 값으로 읽지 않게)."""
    lines = {l.id: l for l in [L("p9:L1", "나.잔류성 및 분해성"), L("p9:L2", "다.오존층 유해성 : 몬트리올 의정서 미등재")]}
    moved, left = ex.extras_to_rows([(12, {"title_raw": "나.잔류성 및 분해성", "line": "p9:L1"}),
                                     (12, {"title_raw": "다.오존층 유해성", "line": "p9:L2"})], lines)
    assert moved["ecotox"] == [] and len(left) == 2


# ── 15항 항목 코드: 근거 줄·제목 줄을 동의어 사전으로 (모델이 앞 제목의 코드를 붙이거나 지어냄) ─────

R_LINES = [L("p10:L1", "가. 산업안전보건법에 의한 규제"),
           L("p10:L2", "- 가상물질 갑 : 해당없음"),
           L("p10:L3", "- 가상물질 을 : 노출기준 설정물질"),
           L("p10:L4", "노출기준설정물질"),
           L("p10:L5", "가상물질 갑 (CAS 1234-56-6)"),
           L("p10:L6", "배출저감계획서 제출 대상 물질"),
           L("p10:L7", "- 가상물질 갑 : 가상 비고"),
           L("p10:L8", "등록대상 기존 화학물질 (PEC) (가상 고시)"),
           L("p10:L9", "작업환경 측정대상물질"),
           L("p10:L10", "규제되지 않음."),
           L("p11:L1", "가. 산업안전보건법에 의한 규제 PRODUCT : 관리대상유해물질, 노출기준설정물질, 작업환경측"),
           L("p11:L2", "정대상물질"),
           L("p11:L3", "- 가상물질 을 : 관리대상유해물질, 노출기준설정대상물질, 작업환경측정대상물질"),
           L("p11:L4", "- 가상물질 갑 : 해당없음")]
R_COMPS = [{"seq": 1, "name": "가상물질 갑", "cas_no": "1234-56-6"}, {"seq": 2, "name": "가상물질 을", "cas_no": "2345-67-7"}]


@pytest.mark.parametrize("line, law, code, want", [
    ("p10:L5", "OSH", "OSH_MEASURE", ("OSH", "OSH_EXPOSURE_STD")),    # 성분 줄 → 위 제목 '노출기준설정물질' (M013)
    ("p10:L2", "OSH", "OSH_EXPOSURE_STD", ("OSH", None)),           # 성분 줄 → 위가 법령 제목이면 코드 없음 (M004)
    ("p10:L3", "OSH", "OSH_EXPOSURE_STD", ("OSH", "OSH_EXPOSURE_STD")),   # 값 부분이 항목명이면 그 코드
    ("p10:L7", "CCA", "CCA_PRTR", ("CCA", "CCA_PRTR")),             # 위 제목이 사전에 없으면 그대로
    ("p10:L8", "KREACH", "KREACH_EXIST", ("KREACH", "KREACH_REG")), # 근거 줄이 항목명이면 그 코드
    ("p10:L10", "OSH", "OSH_HEALTH_EXAM", ("OSH", "OSH_MEASURE")),  # 상태 줄 → 위 제목
    ("p11:L3", "OSH", "OSH_MEASURE", ("OSH", "OSH_MEASURE")),       # 한 줄에 항목 여럿: 모델 코드가 그중 하나면 그대로 (M004)
    ("p11:L3", "OSH", "OSH_PSM", ("OSH", "OSH_PSM")),               # 그중에 없으면 모호해 그대로
    ("p11:L4", "OSH", "OSH_EXPOSURE_STD", ("OSH", None)),           # 부모(글머리 '가.')가 법령 제목. 끊긴 줄을 건너뛴다 (M004)
])
def test_recode_regulations(line, law, code, want):
    """15항 항목 코드는 근거 줄이나 그 목록의 제목 줄에 적힌 항목명(동의어 사전 R25)으로 정한다."""
    rows = [{"law": law, "item_code": code, "applicable": "해당", "comp_ref": "1", "line": line}]
    ex.recode_regulations(rows, {l.id: l for l in R_LINES}, R_COMPS)
    assert (rows[0]["law"], rows[0]["item_code"]) == want


def test_recode_regulations_skips_intl():
    rows = [{"law": "INTL", "item_code": "INTL_EU", "applicable": "해당", "comp_ref": "1", "line": "p10:L5"}]
    ex.recode_regulations(rows, {l.id: l for l in R_LINES}, R_COMPS)
    assert rows[0]["item_code"] == "INTL_EU"


def test_recode_regulations_keeps_row_when_threshold_not_in_line():
    """행의 기준농도 숫자가 근거 줄에 없으면 줄 번호가 틀린 행이라 코드를 바꾸지 않는다
    (S016: 유독물질 85% 행이 다음 항목 줄 '- 해당됨 (0.1% 이상 …)'을 가리켰다)."""
    lines = {l.id: l for l in [L("p8:L45", "○ 유독물질"), L("p8:L46", "- 해당됨 (85% 이상 함유한 가상물질 갑)"),
                               L("p8:L47", "○ 배출량조사대상화학물질"), L("p8:L48", "- 해당됨 (0.1% 이상 함유한 가상물질 갑)")]}
    rows = [{"law": "CCA", "item_code": "CCA_TOXIC", "applicable": "해당", "comp_ref": "1", "line": "p8:L48",
             "threshold": {"raw": "85% 이상", "lower_op": ">=", "lower": 85, "unit": "%"}}]
    ex.recode_regulations(rows, lines, R_COMPS)
    assert rows[0]["item_code"] == "CCA_TOXIC"
    rows[0]["threshold"] = {"raw": "0.1% 이상", "lower_op": ">=", "lower": 0.1, "unit": "%"}
    ex.recode_regulations(rows, lines, R_COMPS)
    assert rows[0]["item_code"] == "CCA_PRTR"


def test_add_missing_items_heading_and_status():
    """항목 이름만 적힌 제목 줄과 그 상태(같은 줄 ':' 뒤 또는 다음 상태 줄)가 있는데 그 코드의 행이 없으면 MIX 행을 더한다
    (M013 '작업환경 측정대상물질' / '규제되지 않음.'을 모델이 뺐다. 개발 골드는 15항에 적힌 국내 항목 66개 모두 행이 있다).
    그 코드의 행이 이미 있거나, 다음 줄이 상태 줄이 아니면 더하지 않는다."""
    lines = {l.id: l for l in R_LINES}
    rows = [{"law": "OSH", "item_code": "OSH_EXPOSURE_STD", "applicable": "해당", "comp_ref": "1", "line": "p10:L5"},
            {"law": "OSH", "item_code": None, "applicable": "비해당", "comp_ref": "1", "line": "p11:L4"}]   # 범위 끝
    new = ex.add_missing_items(rows, lines)
    assert [(r["law"], r["item_code"], r["applicable"], r["comp_ref"], r["line"]) for r in new] == [
        ("OSH", "OSH_MEASURE", "비해당", "MIX", "p10:L9")]
    rows.append({"law": "OSH", "item_code": "OSH_MEASURE", "applicable": "해당", "comp_ref": "1", "line": "p10:L9"})
    assert ex.add_missing_items(rows, lines) == []


@pytest.mark.parametrize("cls, want", [("제4류", [("DG", "DG_HAZMAT", "해당", "MIX")]),
                                       ("해당없음", [("DG", "DG_HAZMAT", "비해당", "MIX")]),
                                       (None, [])])
def test_dg_row_from_dangerous_goods(no_conventions, cls, want):
    """규제 행이 있는데 위험물(DG) 행이 없고 위험물 표가 있으면 그 표로 DG_HAZMAT 행을 더한다. 류(제N류)가 있으면 해당,
    상태어면 그 상태 (개발 골드: 15항이 있는 문서마다 DG_HAZMAT 행이 하나. 모델은 M013 '제4류 …'를 위험물 표에만 넣었다)."""
    r = responses()
    r[15]["dangerous_goods"] = [{"class": cls, "item": "제2석유류" if cls == "제4류" else None, "line": "p6:L11"}]
    m, _ = expand_one(r)
    assert [(x["law"], x["item_code"], x["applicable"], x["comp_ref"]) for x in m["regulations"] if x["law"] == "DG"] == want


def test_standard_status_rows():
    """8항 범위의 '기준 이름 : 상태어' 줄을 가리키는 노출기준 행이 없으면 MIX 행을 더한다. 종류는 TWA, 생물학적은 BEI
    (골드 값 없는 노출기준 40행 모두. 모델은 M002 'ο 국내규정 : 자료없음' 등 6줄을 extras 한 덩어리로 묶었다).
    이미 행이 가리키는 줄과 값이 상태어가 아닌 줄은 두지 않는다."""
    lines = {l.id: l for l in [L("p5:L1", "가. 화학물질의 노출기준, 생물학적 노출기준 등"), L("p5:L2", "ο 국내규정 : 자료없음"),
                               L("p5:L3", "ο 생물학적 노출기준 : 해당없음"), L("p5:L4", "ο ACGIH 규정 : TWA 1 ppm"),
                               L("p5:L5", "- OSHA 규정 자료없음"), L("p5:L6", "나. 적절한 공학적 관리")]}
    have = [{"comp_name": None, "standard": "ACGIH", "line": "p5:L4"}, {"comp_name": None, "standard": "OSHA", "line": "p5:L5"}]
    new = ex.standard_status_rows(have, ["p5:L1", "p5:L6"], lines)
    assert [(r["standard"], r["limit_type"], r["q"]["raw"], r["line"]) for r in new] == [
        ("국내", "TWA", "자료없음", "p5:L2"), ("생물학적", "BEI", "해당없음", "p5:L3")]


def test_fix_eco_descriptor():
    """생태 행: 값이 없으면 지표를 비워 A 규칙(어류 등 결과기술, 잔류성 분해율, 농축성 BCF→분해율)에 맡긴다 — 골드 표기와 같다.
    모델은 '- 트랜스 2 부텐 : 자료없음'에 LC50·EC50을 붙였다 (M004). 숫자 행인데 근거 줄에 log Kow·log Pow가 있으면 logKow (골드 21행)."""
    lines = {l.id: l for l in [L("p12:L1", "- 가상물질 갑 : log Kow 1.99"), L("p12:L2", "- 가상물질 갑 : 자료없음")]}
    no_value = {"endpoint": "ECO_FISH", "descriptor": "LC50", "q": {"raw": "자료없음"}, "status": "자료없음", "line": "p12:L2"}
    kow = {"endpoint": "ECO_PERSIST", "descriptor": "결과기술", "q": {"raw": "1.99", "value": 1.99}, "status": "값있음", "line": "p12:L1"}
    lc50 = {"endpoint": "ECO_FISH", "descriptor": "LC50", "q": {"raw": "10 mg/L", "value": 10, "unit": "mg/L"}, "status": "값있음",
            "line": "p12:L2"}
    assert [ex.fix_eco_descriptor(r, lines)["descriptor"] for r in (no_value, kow, lc50)] == [None, "logKow", "LC50"]


# ── 표·소제목 아래의 '성분 : 상태어' 칸 → 행 (모델이 뺀 값 없는 행, 골드 M004) ─────

T_LINES = [L("p5:L37", "구성성분 | 국내규정 | ACGIH규정 | 생물학적 노출기준"),
           L("p5:L38", "가상물질 갑 | TWA : 2ppm | TWA 2 ppm | 자료없음"),
           L("p5:L39", "5"),
           L("p6:L2", "구성성분 | 국내규정 | ACGIH규정 | 생물학적 노출기준"),
           L("p6:L3", "가상물질 을 | 자료없음 | TWA 250 ppm | 해당없음"),
           L("p11:L31", "● 어류"),
           L("p11:L32", "- 가상물질 갑 : LC50 45 mg/L"),
           L("p11:L33", "- 가상물질 을 : 자료없음"),
           L("p11:L34", "11"),
           L("p12:L1", "[ 가상 머리글 ]"),
           L("p12:L2", "● 조류"),
           L("p12:L3", "- 가상물질 갑 : 자료없음")]


def test_table_status_rows():
    """8항 표(머리글 '구성성분 | 국내규정 | ACGIH규정 | 생물학적 노출기준')의 성분 줄 칸이 상태어면, 그 성분 × 기준 행이 없을 때
    더한다. 종류는 TWA, 생물학적은 BEI (골드 M004 18행). 값 칸과 이미 있는 행은 두지 않는다. 쪽이 바뀌어 머리글이 반복돼도 같다."""
    lines = {l.id: l for l in T_LINES}
    have = [{"comp_name": "가상물질 을", "standard": "국내", "line": "p6:L3"}]
    new = ex.table_status_rows(have, ["p5:L37", "p6:L3"], lines)
    assert [(r["comp_name"], r["standard"], r["limit_type"], r["q"]["raw"], r["line"]) for r in new] == [
        ("가상물질 갑", "생물학적", "BEI", "자료없음", "p5:L38"), ("가상물질 을", "생물학적", "BEI", "해당없음", "p6:L3")]


def test_heading_status_rows():
    """11·12항 '- 성분 : 상태어' 줄이 항목 소제목(● 어류 등) 아래 있고 그 행이 없으면 더한다. 위로 올라가며 성분 줄·쪽 머리글을
    건너뛴다 (골드 M004 '● 조류' 아래 '- 트랜스 2 부텐 : 자료없음'). 값 줄과 이미 있는 행은 두지 않는다."""
    lines = {l.id: l for l in T_LINES}
    comps = [{"seq": 1, "name": "가상물질 갑", "cas_no": "1234-56-6"}, {"seq": 2, "name": "가상물질 을", "cas_no": "2345-67-7"}]
    have = [{"comp_name": "가상물질 갑", "endpoint": "ECO_FISH", "line": "p11:L32"}]
    new = ex.heading_status_rows("ecotox", have, ["p11:L31", "p12:L3"], lines, comps)
    assert [(r["comp_name"], r["endpoint"], r["status"], r["line"]) for r in new] == [
        ("가상물질 을", "ECO_FISH", "자료없음", "p11:L33"), ("가상물질 갑", "ECO_ALGAE", "자료없음", "p12:L3")]
    have.append({"comp_name": "가상물질 을", "endpoint": "ECO_FISH", "line": "p11:L33"})
    assert len(ex.heading_status_rows("ecotox", have, ["p11:L31", "p12:L3"], lines, comps)) == 1
