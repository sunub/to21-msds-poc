"""extract/source_rules.py 시험. 줄은 직접 만든 짧은 가짜 MSDS다 (D-43). 모델 서버를 부르지 않는다."""
import copy

import pytest

from msds.extract import expand as ex
from msds.extract.inputs import Line
from msds.extract.source_rules import apply_source_rules


def L(lid, text):
    page, no = lid[1:].split(":L")
    return Line(lid, int(page), int(no), text)


def doc(*texts):
    """줄 글 여러 개 → 1쪽부터 한 줄씩 번호를 붙인 줄 목록."""
    return [L(f"p1:L{i}", t) for i, t in enumerate(texts, 1)]


def empty_item():
    """펼치기가 만드는 빈 msds 항목 (모든 칸이 있는 모양)."""
    return ex.expand_msds({}, {}, 0, "텍스트층")[0]


def item_with(h=(), p=(), contacts=(), **meta):
    m = empty_item()
    m["hazard"]["h_statements"] = [{"seq": i, "code": c, "system": None, "mark": None, "text": t}
                                   for i, (c, t) in enumerate(h, 1)]
    m["hazard"]["p_statements"] = [{"seq": i, "code": c, "type": None, "text": t}
                                   for i, (c, t) in enumerate(p, 1)]
    m["companies"] = [{"seq": 1, "role": "제조자", "name": "가상화학", "contacts": [
        {"type": "긴급", "value": v, "hours": None} for v in contacts]}] if contacts else []
    m["meta"].update(meta)
    return m


H = [("H225", "고인화성 액체 및 증기"), ("EUH066", "피부가 건조해질 수 있음")]
P = [("P210", "열원에서 멀리하시오."), ("P301+P310", "삼켰다면 즉시 의료기관에 연락하시오.")]


def codes(m, kind):
    return [s["code"] for s in m["hazard"][kind]]


def texts(m, kind):
    return [s["text"] for s in m["hazard"][kind]]


# ── H·P 코드 ───────────────────────────────────────────

def test_codes_cleared_when_document_has_no_code_forms():
    lines = doc("2. 유해성·위험성", "고인화성 액체 및 증기", "열원에서 멀리하시오.")
    m = item_with(h=H, p=P)
    changes = apply_source_rules(m, lines)
    assert codes(m, "h_statements") == [None, None]
    assert codes(m, "p_statements") == [None, None]
    assert texts(m, "h_statements") == [t for _, t in H]       # 문장은 둔다
    assert texts(m, "p_statements") == [t for _, t in P]
    assert [s["seq"] for s in m["hazard"]["h_statements"]] == [1, 2]
    assert len(changes) == 2 and all(isinstance(c, str) for c in changes)


def test_only_p_cleared_when_text_has_h_but_no_p():
    lines = doc("H225 고인화성 액체 및 증기", "열원에서 멀리하시오.")
    m = item_with(h=H, p=P)
    apply_source_rules(m, lines)
    assert codes(m, "h_statements") == ["H225", "EUH066"]
    assert codes(m, "p_statements") == [None, None]


def test_only_h_cleared_when_text_has_p_but_no_h():
    lines = doc("고인화성 액체 및 증기", "- | P210 | 열원에서 멀리하시오.")
    m = item_with(h=H, p=P)
    apply_source_rules(m, lines)
    assert codes(m, "h_statements") == [None, None]
    assert codes(m, "p_statements") == ["P210", "P301+P310"]


@pytest.mark.parametrize("text", [
    "EUH208 가상물질을 함유함. 알레르기 반응을 일으킬 수 있음",
    "H319심한 눈 자극을 일으킴",            # 한글이 바로 붙어도 코드다
    "(H360FD) 태아에 손상을 일으킬 수 있음",  # TO21 접미 문자
    "H302+H332 | 삼키거나 흡입하면 유해함",
])
def test_h_code_forms_in_text_keep_codes(text):
    m = item_with(h=H)
    apply_source_rules(m, doc(text))
    assert codes(m, "h_statements") == ["H225", "EUH066"]


@pytest.mark.parametrize("text", [
    "제품 번호 AH2251-B",       # 앞이 영문
    "H2250 가상 규격",           # 숫자가 넷
    "용량 2H225 가상",           # 앞이 숫자
])
def test_not_h_code_forms_still_clear(text):
    m = item_with(h=H)
    apply_source_rules(m, doc(text))
    assert codes(m, "h_statements") == [None, None]


@pytest.mark.parametrize("text, kept", [
    ("P301+P310 삼켰다면 즉시 의료기관에 연락하시오.", True),
    ("가상 포장 단위 P1000", False),
    ("BP210 가상 규격", False),
])
def test_p_code_forms(text, kept):
    m = item_with(p=P)
    apply_source_rules(m, doc(text))
    assert codes(m, "p_statements") == (["P210", "P301+P310"] if kept else [None, None])


def test_codes_already_empty_report_nothing():
    m = item_with(h=[(None, "고인화성 액체 및 증기")])
    assert apply_source_rules(m, doc("고인화성 액체 및 증기")) == []
    assert texts(m, "h_statements") == ["고인화성 액체 및 증기"]


# ── 개정 횟수 ──────────────────────────────────────────

@pytest.mark.parametrize("text, before, after", [
    ("○ 개정 횟수 : 0", 3, 0),                         # 0도 값이다
    ("○ 개정 횟수 : 0", None, 0),
    ("개정횟수 : 11회", None, 11),
    ("- 개정 횟수 | : 1", None, 1),
    ("개정 횟수 ： 4 회", None, 4),
    ("3)개정 횟수 및 최종 개정 일자 : 8회, 2026. 01. 15", None, 8),
    ("○ 개정 횟수 : 2-2", 2, None),
])
def test_revision_no_from_line(text, before, after):
    m = item_with(revision_no=before)
    changes = apply_source_rules(m, doc("16. 그 밖의 참고사항", text))
    assert m["meta"]["revision_no"] == after and type(m["meta"]["revision_no"]) is type(after)
    assert len(changes) == 1


def test_revision_no_multiple_colons_on_line():
    lines = doc("최초 작성일자 : 2020-01-01   개정 횟수 : 3",
                "가. 개정 횟수 : 5, 최종 개정일자 : 2021-02-02")
    m = item_with(revision_no=9)
    apply_source_rules(m, lines)
    assert m["meta"]["revision_no"] == 3          # 첫 줄, 개정 횟수 뒤의 콜론


def test_revision_no_comma_cut_with_colons_after():
    m = item_with()
    apply_source_rules(m, doc("가. 개정 횟수 : 5, 최종 개정일자 : 2021-02-02"))
    assert m["meta"]["revision_no"] == 5


@pytest.mark.parametrize("text", [
    "다. 개정횟수 및 최종 개정일자",            # 콜론 없음
    "개정횟수 | 4 회",                         # 콜론 없음
    "○ 개정 횟수 : 자료없음",                   # 숫자가 아님
    "○ 개정 횟수 : Rev.2",
    "개정번호 : 6",                            # '개정 횟수'가 아님
])
def test_revision_no_unchanged(text):
    m = item_with(revision_no=7)
    assert apply_source_rules(m, doc(text)) == []
    assert m["meta"]["revision_no"] == 7


def test_revision_no_first_matching_line():
    m = item_with()
    apply_source_rules(m, doc("다. 개정횟수 및 최종 개정일자", "○ 개정 횟수 : 2", "개정 횟수 : 6"))
    assert m["meta"]["revision_no"] == 2


def test_revision_no_same_value_reports_nothing():
    m = item_with(revision_no=0)
    assert apply_source_rules(m, doc("○ 개정 횟수 : 0")) == []
    assert m["meta"]["revision_no"] == 0


# ── 메타 값 없음 ───────────────────────────────────────

def test_meta_no_value_strings_become_none():
    m = item_with(msds_no="자료없음", doc_code=" 해당 없음 ", revision_label="미기재",
                  header_product_name="가상 세정액 A", source_note="자료 없음 표기 예", revision_no=2)
    changes = apply_source_rules(m, doc("가상 세정액 A"))
    assert m["meta"]["msds_no"] is None and m["meta"]["doc_code"] is None and m["meta"]["revision_label"] is None
    assert m["meta"]["header_product_name"] == "가상 세정액 A"
    assert m["meta"]["source_note"] == "자료 없음 표기 예"
    assert m["meta"]["revision_no"] == 2
    assert len(changes) == 3


# ── 메타 값의 원문 확인 ─────────────────────────────────

@pytest.mark.parametrize("value, kept", [
    ("AA01234-0000000056", True),          # 원문에 있다 (공백·하이픈 차이는 무시)
    ("AA00000-0000000000", False),         # 명세서 예시 꼴이지만 원문에 없다
    ("YNCC", False),                       # 원문 글자지만 제출번호 꼴(^AA\d{5}-\d{10}$)이 아니다
])
def test_msds_no_must_match_form_and_source(value, kept):
    m = item_with(msds_no=value)
    apply_source_rules(m, doc("[ YNCC MSDS ]", "MSDS 번호 : AA01234 - 0000000056"))
    assert m["meta"]["msds_no"] == (value if kept else None)


@pytest.mark.parametrize("value, kept", [
    ("2019-03-08", True), ("2010-06-21", True), ("2017-12-21", True), ("2023-02-18", True),
    ("2024-01-01", False),
])
def test_dates_must_appear_in_source(value, kept):
    """날짜는 원문에 연·월·일이 그 순서(또는 일·월·연 순서)로 적혀 있어야 남는다. 없는 날짜는 모델이 만든 것이다."""
    m = item_with(last_revision_date=value)
    apply_source_rules(m, doc("최종 개정일자 : 2019. 3. 8", "작성일자 2010년 06월 21일", "Revision date: 21/12/2017",
                              "개정일 20230218"))
    assert m["meta"]["last_revision_date"] == (value if kept else None)


# ── 전화번호 ───────────────────────────────────────────

def phones(m):
    return [c["value"] for c in m["companies"][0]["contacts"]]


def test_phone_replaced_with_source_text():
    lines = doc("- 긴급 전화번호 | : 0410001234", "팩스 : 031 000 2222")
    m = item_with(contacts=["041-000-1234", "031-000-2222"])
    changes = apply_source_rules(m, lines)
    assert phones(m) == ["0410001234", "031 000 2222"]
    assert len(changes) == 2


def test_phone_in_source_as_written_unchanged():
    m = item_with(contacts=["02-000-0000"])
    assert apply_source_rules(m, doc("대표전화 : 02-000-0000 (평일)")) == []
    assert phones(m) == ["02-000-0000"]


@pytest.mark.parametrize("value, text", [
    ("010-9999-9999", "긴급전화 : 02-000-0000"),     # 같은 숫자가 없음
    ("041-000-1234", "번호 0410001234567"),          # 더 긴 숫자의 일부
    ("1 19", "화재 시 : 119"),                       # 7자 미만
    (None, "긴급전화 : 02-000-0000"),
])
def test_phone_not_found_unchanged(value, text):
    m = item_with(contacts=[value])
    before = copy.deepcopy(m)
    assert apply_source_rules(m, doc(text)) == []
    assert m == before


# ── 유해성 분류 (hazard.classes) ───────────────────────

CLASS_LINES = ("2. 유해성·위험성 정보",
               "가. 유해성·위험성 분류",
               "- 인화성 액체 : 구분2",
               "- 발암성 : 구분 1A",
               "- 만성 수생환경 유해성 : 구분2",
               "나. 예방조치 문구를 포함한 경고 표지 항목",
               "○ 그림문자")


def classes(m):
    return [(c["group"], c["class_code"], c["category"]) for c in m["hazard"]["classes"]]


def class_evidence(m):
    return [e for e in m["evidence"] if e["field"].startswith("hazard.classes")]


def test_classes_from_section_lines():
    lines = doc(*CLASS_LINES)
    m = item_with()
    changes = apply_source_rules(m, lines)
    assert classes(m) == [("물리적", "PH_FLAM_LIQ", "2"), ("건강", "HH_CARCINOGEN", "1A"),
                          ("환경", "ENV_AQ_CHRONIC", "2")]
    rows = m["hazard"]["classes"]
    assert [c["seq"] for c in rows] == [1, 2, 3]
    assert [c["raw"] for c in rows] == ["인화성 액체 : 구분2", "발암성 : 구분 1A", "만성 수생환경 유해성 : 구분2"]
    assert all(c["route_form"] is None and c["effect"] is None and c["target_organs"] == [] for c in rows)
    ev = class_evidence(m)
    assert [e["field"] for e in ev] == ["hazard.classes[0]", "hazard.classes[1]", "hazard.classes[2]"]
    assert [e["source_text"] for e in ev] == list(CLASS_LINES[2:5])
    assert all(e["page"] == 1 and e["needs_review"] is True for e in ev)
    assert len(changes) == 1


def test_classes_rows_pass_item_schema():
    from msds.common.schema import msds_item_schema
    from jsonschema import Draft202012Validator

    m = item_with()
    apply_source_rules(m, doc(*CLASS_LINES))
    errors = list(Draft202012Validator(msds_item_schema()).iter_errors(m))
    assert errors == []


def test_classes_outside_section_not_read():
    lines = doc(*CLASS_LINES, "15. 법적 규제현황", "- 가상물질 : 구분 1A", "- 생식세포 변이원성 : 구분 1B")
    m = item_with()
    apply_source_rules(m, lines)
    assert classes(m) == [("물리적", "PH_FLAM_LIQ", "2"), ("건강", "HH_CARCINOGEN", "1A"),
                          ("환경", "ENV_AQ_CHRONIC", "2")]


def test_classes_no_heading_reads_nothing():
    m = item_with()
    assert apply_source_rules(m, doc("15. 법적 규제현황", "- 발암성 : 구분 1A")) == []
    assert m["hazard"]["classes"] == []


def test_classes_kept_when_model_wrote_some():
    m = item_with()
    m["hazard"]["classes"] = [{"seq": 1, "group": "건강", "class_code": "HH_EYE_DMG", "category": "2",
                               "route_form": None, "effect": None, "target_organs": [], "raw": "눈 자극 : 구분2"}]
    before = copy.deepcopy(m)
    assert apply_source_rules(m, doc(*CLASS_LINES)) == []
    assert m == before


def test_classes_not_filled_when_many_msds():
    m = item_with()
    before = copy.deepcopy(m)
    assert apply_source_rules(m, doc(*CLASS_LINES), single_msds=False) == []
    assert m == before


def test_classes_on_heading_line():
    lines = doc("가. 유해성·위험성 분류 | 인화성 가스 : 구분1", "나. 예방조치문구를 포함한 경고표지 항목")
    m = item_with()
    apply_source_rules(m, lines)
    assert classes(m) == [("물리적", "PH_FLAM_GAS", "1")]       # 5-1 이름은 괄호 설명이 붙어 13 시트로 찾는다
    assert m["hazard"]["classes"][0]["raw"] == "인화성 가스 : 구분1"
    assert [e["field"] for e in class_evidence(m)] == ["hazard.classes[0]"]


@pytest.mark.parametrize("heading", ["가. 유해·위험성 분류", "가. 유해위험성분류", "가. 유해성ㆍ위험성 분류",
                                     "1) 유해성위험성 분류"])
def test_classes_heading_forms(heading):
    m = item_with()
    apply_source_rules(m, doc(heading, "- 피부 과민성 : 구분 1", "○ 신호어 : 경고"))
    assert classes(m) == [("건강", "HH_SKIN_SENS", "1")]


@pytest.mark.parametrize("bullet", ["ο ", "○ ", "• ", "1) ", "가) ", ""])
def test_classes_bullets_removed_from_name(bullet):
    m = item_with()
    apply_source_rules(m, doc("가. 유해성·위험성 분류", f"{bullet}흡인 유해성 : 구분 1", "나. 그림문자"))
    assert classes(m) == [("건강", "HH_ASPIRATION", "1")]
    assert m["hazard"]["classes"][0]["raw"] == "흡인 유해성 : 구분 1"


def test_classes_several_on_one_line_and_pipe_bullet():
    lines = doc("가. 유해성·위험성 분류",
                "- | 인화성 액체 : 구분3, 급성 독성(경구) : 구분 4 | 심한 눈 손상성/눈 자극성 : 구분2A",
                "- 특정표적장기 독성(1회 노출) : 구분3(호흡기계 자극)",
                "- 피부 부식성 또는 자극성 물질 : 구분 1B",       # 13 시트의 '이름 : 구분 N' 글
                "나. 그림문자")
    m = item_with()
    apply_source_rules(m, lines)
    assert classes(m) == [("물리적", "PH_FLAM_LIQ", "3"), ("건강", "HH_ACUTE_ORAL", "4"),
                          ("건강", "HH_EYE_DMG", "2A"), ("건강", "HH_STOT_SE", "3"),
                          ("건강", "HH_SKIN_CORR", "1B")]
    assert [e["source_text"] for e in class_evidence(m)] == [lines[1].text] * 3 + [lines[2].text, lines[3].text]


def test_classes_unknown_names_dropped():
    lines = doc("가. 유해성·위험성 분류", "- 가상 유해성 : 구분1", "- 급성 수생환경 유해성 : 구분 1", "○ 그림문자")
    m = item_with()
    apply_source_rules(m, lines)
    assert classes(m) == [("환경", "ENV_AQ_ACUTE", "1")]
    assert m["hazard"]["classes"][0]["seq"] == 1


def test_classes_none_found_reports_nothing():
    m = item_with()
    assert apply_source_rules(m, doc("가. 유해성·위험성 분류", "- 분류되지 않음", "○ 그림문자")) == []
    assert m["hazard"]["classes"] == [] and class_evidence(m) == []


def test_classes_to_to21_single_vs_many_msds():
    lines = doc(*CLASS_LINES)
    meta = {"doc_id": "T21-X001", "source_file": "x.pdf", "pages": "1", "text_layer": "정상", "language": "ko"}
    one, _ = ex.to_to21(meta, [{}], lines, "가짜")
    two, _ = ex.to_to21(meta, [{}, {}], lines, "가짜")
    assert [c["class_code"] for c in one["msds"][0]["hazard"]["classes"]] == ["PH_FLAM_LIQ", "HH_CARCINOGEN",
                                                                             "ENV_AQ_CHRONIC"]
    assert all(m["hazard"]["classes"] == [] for m in two["msds"])


# ── 15항 기준농도 ───────────────────────────────────────

from msds.extract.rows import parse_qm                         # noqa: E402
from msds.extract.source_rules import fill_thresholds          # noqa: E402

THRESHOLD_LINES = [                                            # 가짜 15항. 줄이 바뀌어 '(1%' / '이상)'으로 끊긴다
    "15. 법적 규제현황",
    "가. 산업안전보건법에 의한 규제",
    "- 가상물질 : 관리대상 유해물질(0.1% 이상), 작업환경 측정물질(1%",
    "이상), 노출기준 설정물질",
    "- 해당됨 (1% 이상 함유한 가상물질)",
    "나. 화학물질관리법에 의한 규제",
    "- 가상물질 : 가상물질(가-123) : 함유율(0.1 wt% 이상), 취급량(10 ton/yr)",
    "● 가상 대상 물질",
    "- 가상물질 : 유독물질 (이를 0.1%이상 함유한 혼합물질)",
    "- 가상물질 : 측정대상물질(및 이를 1",
    "wt% 이상 함유한 제제)",
    "다. 위험물안전관리법에 의한 규제",
]


def reg(item_raw, line, threshold=None, **extra):
    return {"law": "OSH", "item_code": "OSH_MEASURE", "item_raw": item_raw, "comp_ref": "1",
            "applicable": "해당", "threshold": threshold, "line": line, **extra}


def th(rows):
    return [(t.get("lower_op"), t.get("lower"), t.get("value"), t.get("unit"), t.get("raw")) if t else None
            for t in (r["threshold"] for r in rows)]


def by_id():
    return ex.line_index(doc(*THRESHOLD_LINES))


def test_threshold_fill_after_item_raw_and_line_break():
    rows = [reg("관리대상 유해물질", "p1:L3"), reg("작업환경 측정물질", "p1:L3"), reg("노출기준 설정물질", "p1:L3")]
    out = fill_thresholds(rows, by_id())
    assert th(out) == [(">=", 0.1, None, "%", "0.1% 이상"), (">=", 1, None, "%", "1% 이상"), None]


def test_threshold_fill_item_raw_ignores_spaces():
    out = fill_thresholds([reg("관리대상유해물질", "p1:L3"), reg("작업 환경측정물질", "p1:L3")], by_id())
    assert th(out) == [(">=", 0.1, None, "%", "0.1% 이상"), (">=", 1, None, "%", "1% 이상")]


def test_threshold_fill_only_one_in_line():
    out = fill_thresholds([reg("작업환경측정대상물질", "p1:L5"), reg("배출량조사 대상물질", "p1:L7"),
                           reg(None, "p1:L9")], by_id())
    assert th(out) == [(">=", 1, None, "%", "1% 이상"), (">=", 0.1, None, "wt%", "0.1 wt% 이상"),
                       (">=", 0.1, None, "%", "0.1%이상")]


def test_threshold_fill_only_one_across_line_break():
    out = fill_thresholds([reg("측정대상물질", "p1:L10")], by_id())        # '(및 이를 1' / 'wt% 이상 함유한 제제)'
    assert th(out) == [(">=", 1, None, "wt%", "1 wt% 이상")]


def test_threshold_fill_value_matches_parse_qm():
    out = fill_thresholds([reg("가상 항목", "p1:L7")], by_id())
    assert out[0]["threshold"] == {**parse_qm("0.1 wt% 이상"), "raw": "0.1 wt% 이상"}


def test_threshold_fill_when_raw_only():
    out = fill_thresholds([reg("가상 항목", "p1:L5", {"raw": "해당"})], by_id())
    assert th(out) == [(">=", 1, None, "%", "1% 이상")]


def test_threshold_two_or_more_and_item_raw_not_matched_unchanged():
    rows = [reg("작업환경측정 대상물질", "p1:L3"), reg("허용기준 설정물질", "p1:L3", {"raw": "해당"})]
    out = fill_thresholds(rows, by_id())
    assert out == rows


def test_threshold_correct_unit_from_line():
    out = fill_thresholds([reg("배출량조사 대상물질", "p1:L7", parse_qm("0.1 %"))], by_id())
    assert th(out) == [(">=", 0.1, None, "wt%", "0.1 wt% 이상")]
    assert not {"value", "upper", "upper_op"} & set(out[0]["threshold"])


def test_threshold_correct_op_from_line():
    out = fill_thresholds([reg("유독물질", "p1:L9", parse_qm("0.1")), reg("가상 항목", "p1:L5", parse_qm("< 1 %"))],
                          by_id())
    assert th(out) == [(">=", 0.1, None, "%", "0.1%이상"), (">=", 1, None, "%", "1% 이상")]
    assert not {"value", "upper", "upper_op"} & set(out[1]["threshold"])


def test_threshold_correct_prefers_fragment_after_item_raw():
    out = fill_thresholds([reg("작업환경 측정물질", "p1:L3", parse_qm("1 wt%"))], by_id())
    assert th(out) == [(">=", 1, None, "%", "1% 이상")]


def test_threshold_number_not_in_line_unchanged():
    rows = [reg("유독물질", "p1:L9", parse_qm("10 %")), reg("가상 항목", "p1:L5", parse_qm("1 ~ 5 %"))]
    assert fill_thresholds(rows, by_id()) == rows


def test_threshold_no_line_or_unknown_line_unchanged():
    rows = [reg("관리대상 유해물질", None), reg("관리대상 유해물질", "p9:L99"), reg("관리대상 유해물질", "")]
    assert fill_thresholds(rows, by_id()) == rows


def test_threshold_last_line_has_no_next_line():
    lines = ex.line_index(doc("가. 산업안전보건법에 의한 규제", "- 해당됨 (0.1% 이상 함유한 가상물질)"))
    assert th(fill_thresholds([reg("가상 항목", "p1:L2")], lines)) == [(">=", 0.1, None, "%", "0.1% 이상")]


def test_threshold_next_line_new_item_not_joined():
    """다음 줄이 글머리(-, ●, 가. 등)로 시작하면 다른 행의 줄이라 잇지 않는다."""
    lines = ex.line_index(doc("- 가상물질 갑 : 해당없음",
                              "- 가상물질 을 : 관리대상 유해물질(1% 이상)",
                              "- 가상물질 병 : 관리대상 유해물질",
                              "● 관리대상 유해물질(0.1% 이상)",
                              "- 가상물질 정 : 가상 항목",
                              "나. 가상 항목(0.1% 이상)"))
    rows = [reg("관리대상 유해물질", "p1:L1"), reg("관리대상 유해물질", "p1:L3"),
            reg("관리대상 유해물질", "p1:L1", parse_qm("1 %")), reg("가상 항목", "p1:L5")]
    assert fill_thresholds(rows, lines) == rows
    assert th(fill_thresholds([reg("관리대상 유해물질", "p1:L2")], lines)) == [(">=", 1, None, "%", "1% 이상")]


def test_threshold_next_line_continuation_joined():
    """글머리 없이 이어진 다음 줄은 같은 항목이다. 그 줄의 item_raw도 찾는다."""
    lines = ex.line_index(doc("- 가상물질 : 관리대상 유해물질, 작업환경 측정물질(1%",
                              "이상), 특별관리물질(0.1% 이상), 허용기준 설정물질",
                              "- 가상물질 : 측정대상물질(및 이를",
                              "0.1% 이상 함유한 제제)"))
    out = fill_thresholds([reg("작업환경 측정물질", "p1:L1"), reg("특별관리물질", "p1:L1"),
                           reg("관리대상 유해물질", "p1:L1"), reg("측정대상물질", "p1:L3")], lines)
    assert th(out) == [(">=", 1, None, "%", "1% 이상"), (">=", 0.1, None, "%", "0.1% 이상"), None,
                       (">=", 0.1, None, "%", "0.1% 이상")]


def test_threshold_input_rows_not_changed():
    rows = [reg("관리대상 유해물질", "p1:L3"), reg("배출량조사 대상물질", "p1:L7", parse_qm("0.1 %"))]
    before = copy.deepcopy(rows)
    out = fill_thresholds(rows, by_id())
    assert rows == before and out is not rows
    assert out[0] is not rows[0] and out[0]["threshold"] is not None


def test_threshold_number_boundaries():
    lines = ex.line_index(doc("- 가상물질 : 가상 항목(10.1% 이상)", "- 가상물질 : 가상 항목(21% 이상)"))
    out = fill_thresholds([reg("가상 항목", "p1:L1", parse_qm("1 %")), reg("가상 항목", "p1:L1")], lines)
    assert th(out)[0] == (None, None, 1, "%", "1 %")                   # 10.1의 끝 '1'을 1로 읽지 않는다
    assert th(out)[1] == (">=", 10.1, None, "%", "10.1% 이상")


def test_threshold_expand_msds_fills_regulations():
    """펼치기가 15항 행을 _shape 전에 고쳐 TO21 Q(status·dp)가 된다."""
    lines = doc(*THRESHOLD_LINES)
    s15 = {"regulations": [
        {"law": "OSH", "item_code": "OSH_MANAGED", "item_raw": "관리대상 유해물질", "applicable": "해당",
         "line": "p1:L3"},
        {"law": "OSH", "item_code": "OSH_MEASURE", "item_raw": "가상 항목", "applicable": "해당",
         "threshold": {"raw": "lower_op:>=,lower:1,unit:%", "lower_op": ">=", "lower": 1, "unit": "%"},
         "line": "p1:L5"}]}
    item, _ = ex.expand_msds({15: s15}, ex.line_index(lines), 0, "텍스트층")
    t0, t1 = (r["threshold"] for r in item["regulations"][:2])      # 셋째는 R18 화평법 미기재 행
    assert (t0["lower_op"], t0["lower"], t0["unit"], t0["status"], t0["dp"]) == (">=", 0.1, "%", "값있음", 1)
    assert (t1["lower_op"], t1["lower"], t1["unit"], t1["status"]) == (">=", 1, "%", "값있음")
    assert [e["field"] for e in item["evidence"]] == ["regulations[0]", "regulations[1]"]


HEADING_LINES = [                                              # 가짜 15항. 항목 제목 줄 아래 자식 줄에 기준농도가 있다
    "가. 산업안전보건법에 의한 규제",
    "○ 작업환경측정물질",
    "- 해당됨 (1% 이상 함유한 가상물질)",
    "○ 노출기준설정물질",
    "- 해당됨 (가상물질)",
    "○ 관리대상유해물질",
    "- 가상물질 갑 : 0.1% 이상",
    "- 가상물질 을 : 1% 이상",
]


def test_threshold_from_child_line_of_heading():
    """근거 줄이 항목 제목('○ 작업환경측정물질')이고 기준농도가 그 자식 줄에 있으면 자식 줄로 채우거나 바로잡는다.
    모델이 제목 줄을 근거로 적고 '1 %'만 옮긴 일이 있었다 (S016). 자식 줄에 'N% 이상'이 여럿이면 채우지 않는다."""
    lines = ex.line_index(doc(*HEADING_LINES))
    rows = [reg(None, "p1:L2", {"raw": "1 %", "value": 1, "unit": "%"}), reg(None, "p1:L2"),
            reg(None, "p1:L4"), reg(None, "p1:L6"), reg(None, "p1:L6", {"raw": "1 %", "value": 1, "unit": "%"})]
    assert th(fill_thresholds(rows, lines)) == [(">=", 1, None, "%", "1% 이상"), (">=", 1, None, "%", "1% 이상"), None,
                                                None, (">=", 1, None, "%", "1% 이상")]


def test_threshold_without_number_is_dropped():
    """숫자 없는 기준농도('비해당' 등)는 기준농도가 아니라 비운다. 골드·실버 기준농도 28개는 모두 숫자가 있다.
    숫자가 있는 기준농도는 둔다."""
    from msds.extract.source_rules import clear_numberless_thresholds
    rows = [reg(None, "p1:L1", {"raw": "비해당"}), reg(None, "p1:L1", {"raw": "해당없음", "status": "해당없음"}),
            reg(None, "p1:L1", {"raw": "1% 이상", "lower_op": ">=", "lower": 1, "unit": "%"})]
    clear_numberless_thresholds(rows)
    assert th(rows) == [None, None, (">=", 1, None, "%", "1% 이상")]


def test_threshold_not_taken_from_children_of_law_heading_with_content():
    """근거 줄이 '가. 법령 PRODUCT : 항목, 항목'처럼 ':' 뒤에 내용이 있는 제목이면 자식 줄을 보지 않는다.
    자식 줄은 성분마다의 기준농도라 제품 행에 붙이면 틀린다 (M004)."""
    lines = ex.line_index(doc("가. 산업안전보건법에 의한 규제 PRODUCT : 관리대상유해물질, 작업환경측정대상물질",
                              "- 가상물질 갑 : 작업환경측정대상물질(및 이를 1 wt% 이상 함유한 제제)"))
    rows = [reg(None, "p1:L1", {"raw": "1 wt%", "value": 1, "unit": "wt%"}, comp_ref="MIX"), reg(None, "p1:L1", comp_ref="MIX")]
    out = fill_thresholds(rows, lines)
    assert th(out) == [(None, None, 1, "wt%", "1 wt%"), None]


def test_threshold_in_listed_items_goes_only_to_its_item():
    """한 줄에 항목이 쉼표로 나열되고 'N% 이상'이 그중 한 항목 뒤 괄호에만 있으면, 그 항목 행만 채운다 (M004).
    괄호 안의 쉼표는 나누지 않는다. 항목 이름이 없는 행은 예전처럼 줄에 하나뿐인 'N% 이상'으로 채운다."""
    lines = ex.line_index(doc("- 가상물질 : 관리대상유해물질, 노출기준설정대상물질, 작업환경측정대상물질(및 이를 1 wt% 이상 "
                              "함유한 제제, 측정주기:6개월), 특별관리대상물질"))
    rows = [reg("관리대상유해물질", "p1:L1"), reg("작업환경측정대상물질", "p1:L1"), reg("특별관리대상물질", "p1:L1"),
            reg(None, "p1:L1")]
    assert th(fill_thresholds(rows, lines)) == [None, (">=", 1, None, "wt%", "1 wt% 이상"), None,
                                                (">=", 1, None, "wt%", "1 wt% 이상")]


def test_threshold_follows_unclosed_parenthesis_to_later_line():
    """괄호가 닫히지 않은 채 줄이 끝나면 다음 줄을 더 잇는다 (최대 2줄). M004 '특수건강진단물질(및 이를 1' / 'wt% 이상 …)'."""
    lines = ex.line_index(doc("- 가상물질 : 관리대상유해물질, 작업환경측정대상물질(및 이를 1 wt% 이상 함유한",
                              "제제, 측정주기:6개월), 특수건강진단물질(및 이를 1",
                              "wt% 이상 함유한 제제, 진단:6개월 이내)"))
    rows = [reg("특수건강진단물질", "p1:L1"), reg("관리대상유해물질", "p1:L1")]
    assert th(fill_thresholds(rows, lines)) == [(">=", 1, None, "wt%", "1 wt% 이상"), None]
# ── 9항 값 없음 ─────────────────────────────────────────

from msds.extract.source_rules import fill_no_value              # noqa: E402

PHYS_LINES = [                                                 # 가짜 9항. 표의 값 칸에 상태어만 적혔다
    "9. 물리화학적 특성",
    "pH  자료없음  자료없음",
    "3)냄새 역치  자료 없음",
    "인화점  해당 없음",
    "끓는점  -161 ℃",
    "증기압(25℃)  자료없음",
    "점도  자료없음 / 해당없음",
]


def phys(code, line, q=None, text_value=None):
    return {"prop_code": code, "comp_name": None, "comp_cas": None, "q": q, "text_value": text_value,
            "cond": None, "data_source": None, "line": line}


def phys_by_id():
    return ex.line_index(doc(*PHYS_LINES))


def test_no_value_fills_blank_row_from_line():
    rows = [phys("PH", "p1:L2"), phys("ODOR_THRESHOLD", "p1:L3"), phys("FLASH_POINT", "p1:L4")]
    out = fill_no_value(rows, phys_by_id())
    assert [r["q"] for r in out] == [{"raw": "자료없음"}, {"raw": "자료없음"}, {"raw": "해당없음"}]


@pytest.mark.parametrize("row", [
    phys("BOILING", "p1:L5"),                              # 줄에 숫자가 있으면 값을 놓친 것일 수 있다
    phys("VAPOR_PRESSURE", "p1:L6"),                       # 조건의 숫자도 같다
    phys("VISCOSITY", "p1:L7"),                            # 상태어가 둘이면 고르지 않는다
    phys("PH", "p9:L1"),                                   # 원문에 없는 줄
    phys("PH", "p1:L2", text_value="산성"),                # 값이 있는 행
    phys("PH", "p1:L2", q=parse_qm("7")),
])
def test_no_value_leaves_other_rows(row):
    assert fill_no_value([row], phys_by_id()) == [row]


def test_no_value_input_rows_not_changed():
    rows = [phys("PH", "p1:L2")]
    before = copy.deepcopy(rows)
    out = fill_no_value(rows, phys_by_id())
    assert rows == before and out[0] is not rows[0]


def test_no_value_expand_msds_fills_physchem():
    """펼치기가 9항 행을 _shape 전에 고쳐 TO21 Q의 status가 된다."""
    s9 = {"physchem": [{"prop_code": "PH", "line": "p1:L2"}, {"prop_code": "BOILING", "q": parse_qm("-161 ℃"),
                                                              "line": "p1:L5"}]}
    item, _ = ex.expand_msds({9: s9}, phys_by_id(), 0, "텍스트층")
    q0, q1 = (r["q"] for r in item["physchem"])
    assert (q0["raw"], q0["status"], q0["value"]) == ("자료없음", "자료없음", None)
    assert (q1["value"], q1["status"]) == (-161, "값있음")
