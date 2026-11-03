"""오류 주입 시험 (설계서 48장 e2e 오류 주입, 49장 오류 주입셋).

25번 황산 추출본을 한 곳씩 바꾼 사본으로 엔진을 돌려, 바꾼 자리에서 기대한 판정·유형·심각도가 나오는지 확인한다.
주입 목록과 실행은 scripts/f_inject.py 에 있다. 지식DB 샘플 CSV(저장소 밖)가 없으면 건너뛴다.
"""
import pytest

from msds.compliance.htodb.csv_repo import CsvRepo
from scripts.f_inject import CASES, INPUT, evaluate

pytestmark = pytest.mark.skipif(not (INPUT.exists() and CsvRepo().available()), reason="T21-025.json 또는 to21_sample 없음")


@pytest.fixture(scope="module")
def out():
    return evaluate(CsvRepo())


def test_설계서_48장_두_경우를_잡는다(out):
    by = {r["id"]: r for r in out["results"]}
    assert by["INJ-01"]["detected"] and by["INJ-01"]["got"] == "불일치·과소분류"   # 피부 부식성 삭제 → 과소분류(높음)
    assert by["INJ-02"]["detected"] and by["INJ-02"]["got"] == "불일치·규제 누락"  # 사고대비물질 삭제 → 규제 누락(높음)


def test_모든_주입을_잡고_대조군은_일치(out):
    missed = [r["id"] for r in out["results"] if not r["detected"]]
    assert not missed, missed
    s = out["summary"]
    assert s["detected"] == s["cases"] == len(CASES) - 1 and s["high_detected"] == s["high_cases"] == 5
    assert s["controls_ok"]


def test_같이_바뀐_줄은_설명할_수_있는_것만(out):
    side = {r["id"]: r["side"] for r in out["results"]}
    for i in ("INJ-01", "INJ-03", "INJ-04"):  # 분류를 바꾸면 MSDS에 남은 H코드가 분류와 어긋난다
        assert side[i] == ["2항 LABEL_H_CODES: 일치 → 불일치·표시 요소 불일치"], i
    assert side["INJ-09"] == ["2항 PH_FLAM_LIQ: 일치 → 불일치·과소분류"]  # 인화점 15℃ → 인화성 액체 구분2
    assert side["INJ-05"] == ["2항 HH_ACUTE_INHAL/증기: 없음 → 근거부족"]  # 형태를 고치면 묶였던 증기 줄이 따로 남음
    for i in ("INJ-02", "INJ-06", "INJ-07", "INJ-08", "INJ-10", "INJ-11"):
        assert side[i] == [], i


def test_같은_입력을_두번_돌리면_같다(out):
    assert evaluate(CsvRepo()) == out
