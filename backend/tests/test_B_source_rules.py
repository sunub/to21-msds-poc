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
