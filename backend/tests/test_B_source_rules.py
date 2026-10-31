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
    t0, t1 = (r["threshold"] for r in item["regulations"])
    assert (t0["lower_op"], t0["lower"], t0["unit"], t0["status"], t0["dp"]) == (">=", 0.1, "%", "값있음", 1)
    assert (t1["lower_op"], t1["lower"], t1["unit"], t1["status"]) == (">=", 1, "%", "값있음")
    assert [e["field"] for e in item["evidence"]] == ["regulations[0]", "regulations[1]"]
