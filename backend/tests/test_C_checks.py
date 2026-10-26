"""역할 C 완료 기준: 이 파일의 시험이 모두 passed (skipped 0)."""
from conftest import todo
from msds.checks import source_match as sm

PAGES = {1: "가. 제품명\n KZ-A-S004_황산\n", 2: "황산\n7664-93-9\n93 ~ 98\n물\n7732-18-5\n2 ~ 7"}
STATES = {1: "정상", 2: "정상", 3: "글꼴깨짐"}


def test_normalize():
    assert todo(sm.normalize, " 93 ~ 98 \n") == "93~98"
    assert todo(sm.normalize, "（주）") == "(주)"


def test_match_same_page():
    r = todo(sm.match, "KZ-A-S004_황산", 1, PAGES, STATES)
    assert r["result"] == "일치" and r["found_page"] == 1


def test_match_table_row():
    r = todo(sm.match, "황산 | 7664-93-9 | 93 ~ 98", 2, PAGES, STATES)
    assert r["result"] == "일치"


def test_other_page():
    r = todo(sm.match, "7664-93-9", 1, PAGES, STATES)
    assert r["result"] == "일치" and r["found_page"] == 2


def test_not_found_and_unusable():
    assert todo(sm.match, "7664-93-8", 2, PAGES, STATES)["result"] == "불일치"
    assert todo(sm.match, "아무거나", 3, PAGES, STATES)["result"] == "대조불가"
    assert todo(sm.match, None, 1, PAGES, STATES)["result"] == "대조불가"
