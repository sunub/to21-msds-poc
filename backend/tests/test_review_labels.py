"""추출값 화면(2.2)의 칸 이름·묶음 제목·보이는 값: 스키마 키나 코드가 그대로 보이지 않는다. 모델을 부르지 않는다."""
import re

from msds.service import review

ROW = {
    "meta": {"doc_code": "TEST-001"},
    "companies": [{"name": "가상화학", "department": "영업부", "role": "공급자",
                   "contacts": [{"type": "전화", "value": "000-0000-0000"}]}],
    "hazard": {"classified": True, "classes": [{"group": "물리적", "class_code": "PH_FLAM_LIQ", "category": "2"}],
               "nfpa": {"health": 1, "fire": 3}},
    "composition": {"type": "혼합물", "no_hazardous_component": False},
    "components": [{"name": "가상 성분", "content": {"lower": 1, "upper": 2, "unit": "%"}}],
    "exposure_limits": [{"standard": "국내", "limit_type": "TWA", "kr_basis": "노출기준", "q": {"value": 150, "unit": "ppm"}}],
    "physchem": [{"prop_code": "FLASH_POINT", "q": {"value": 22, "unit": "℃"}, "cond": {"temp": 20, "temp_unit": "C", "method": "c.c"}}],
    "toxicity": [{"endpoint": "TX_ORAL", "descriptor": "LD50", "species": "Rat", "duration_value": 4, "duration_unit": "hr"}],
    "ecotox": [{"endpoint": "ECO_FISH", "descriptor": "LC50", "species": "가상종"}],
    "transport": [{"un_no": "1123", "ems_fire": "F-E", "regulated": True}],
    "regulations": [{"law": "OSH", "item_code": "OSH_MANAGED", "item_raw": "관리대상유해물질", "applicable": "해당",
                     "cycle": {"value": 6, "unit": "개월"}}],
    "dangerous_goods": [{"class": "제4류", "item": "제2석유류", "water_soluble": "비수용성"}],
    "waste": [{"designated": "비해당", "waste_type": "사업장폐기물"}],
    "intl_class": [{"system": "EU_CLP", "class_raw": "R10"}],
    "extras": [{"section_no": 9, "statements": [{"key": None, "value": "가상 문장"}]}],
    "narratives": [{"item_code": "S15_OTHER", "title_raw": "마. 기타 규제", "statements": [
        {"key": "〇 | 금지물질 |", "value": "해당안됨"}, {"key": "눈 접촉 |", "value": "자료없음"}]}],
    "evidence": [], "validation": [],
}
VIEW = review.build_view({"doc": {"doc_id": "x"}, "msds": [ROW]}, {}, [], review.empty())
FIELDS = {f["path"]: f for s in VIEW["msds"][0]["sections"] for g in s["groups"] for f in g["fields"]}
GROUPS = {g["path"]: g["title"] for s in VIEW["msds"][0]["sections"] for g in s["groups"]}
CODE = re.compile(r"[A-Za-z]+_[A-Za-z_]+|^[a-z_]+$")


def test_no_schema_key_or_code_in_labels_and_titles():
    leaked = [f["label"] for f in FIELDS.values() if CODE.search(f["label"])] + [t for t in GROUPS.values() if CODE.search(t)]
    assert leaked == []


def test_labels_follow_spec_names():
    label = {p: f["label"] for p, f in FIELDS.items()}
    assert label["companies[0].department"] == "담당부서"
    assert label["companies[0].contacts[0].type"] == "연락처 종류" and label["companies[0].contacts[0].value"] == "연락처"
    assert label["hazard.classes[0].class_code"] == "분류" and label["hazard.nfpa.fire"] == "NFPA 화재"
    assert label["components[0].content.lower"] == "함유량 하한" and label["components[0].content.unit"] == "함유량 단위"
    assert label["exposure_limits[0].limit_type"] == "기준 종류" and label["exposure_limits[0].q.value"] == "값"
    assert label["physchem[0].cond.temp"] == "측정 온도" and label["physchem[0].cond.method"] == "측정 방법"
    assert label["toxicity[0].endpoint"] == "독성 항목" and label["toxicity[0].duration_value"] == "노출 시간"
    assert label["regulations[0].cycle.value"] == "측정·진단 주기" and label["regulations[0].cycle.unit"] == "측정·진단 주기 단위"
    assert label["narratives[0].statements[0].value"] == "금지물질"
    assert label["narratives[0].statements[1].value"] == "눈 접촉"


def test_group_titles_use_korean_names():
    assert GROUPS["physchem[0]"] == "인화점"
    assert GROUPS["toxicity[0]"] == "급성 독성(경구) · LD50"
    assert GROUPS["ecotox[0]"] == "생태독성-어류 · LC50"
    assert GROUPS["regulations[0]"] == "관리대상유해물질"
    assert GROUPS["extras[0]"] == "기타 항목"      # 원문 제목이 없는 기타 항목


def test_display_shows_codes_in_words_but_value_stays_editable():
    f = FIELDS["toxicity[0].endpoint"]
    assert (f["value"], f["display"]) == ("TX_ORAL", "급성 독성(경구)")
    assert FIELDS["hazard.classes[0].class_code"]["display"] == "인화성 액체"
    assert FIELDS["physchem[0].prop_code"]["display"] == "인화점"
    assert FIELDS["regulations[0].law"]["display"] == "산업안전보건법"
    assert FIELDS["physchem[0].cond.temp_unit"]["display"] == "℃"
    assert (FIELDS["hazard.classified"]["value"], FIELDS["hazard.classified"]["display"]) == (True, "예")
    assert FIELDS["composition.no_hazardous_component"]["display"] == "아니오"
    assert FIELDS["companies[0].name"]["display"] is None    # 그대로 보이는 값
