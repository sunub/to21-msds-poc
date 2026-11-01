"""25번 황산 e2e 정답본 시험 (설계서 47장 7단계 완료 기준, 48장 e2e 케이스, 10/30 결정 B2).

고정본: tests/e2e/T21-025_2항_기대.json (만드는 법: python scripts/f_e2e_25.py --write)
- 지금 결과가 고정본과 같아야 한다. 코드를 고치다 2항 결과가 바뀌면 여기서 알린다.
- 같은 입력을 두 번 돌리면 결과가 완전히 같아야 한다(재현성).
- 설계서 38장과 다른 줄에는 이유가 적혀 있어야 한다.
지식DB 샘플 CSV(to21/v0.4/to21_sample, 저장소 밖)가 없으면 건너뛴다.
"""
import json

import pytest

from msds.compliance.htodb.csv_repo import CsvRepo
from scripts.f_e2e_25 import FIXED, INPUT, compare, run, sha256

pytestmark = pytest.mark.skipif(not (INPUT.exists() and CsvRepo().available()), reason="T21-025.json 또는 to21_sample 없음")


@pytest.fixture(scope="module")
def fixed():
    return json.loads(FIXED.read_text(encoding="utf-8"))


def test_입력_파일이_고정할_때와_같다(fixed):
    assert fixed["meta"]["input_sha256"] == sha256(INPUT), \
        "25번 입력(data/silver/claude/T21-025.json)이 바뀜 → 결과를 확인하고 python scripts/f_e2e_25.py --write 로 다시 고정"


def test_25번_2항_판정목록이_고정본과_같다(fixed):
    diffs = compare(fixed, run("csv"))
    assert not diffs, "\n".join(diffs)


def test_같은_입력을_두번_돌리면_결과가_완전히_같다():
    assert run("csv") == run("csv")


def test_설계서_38장과_다른_줄에는_이유가_있다(fixed):
    rows = [v for v in fixed["verdicts"] if v["design_38"] and not v["design_38"]["same"]]
    assert rows, "설계서 38장과 다른 줄이 하나도 없다면 이 시험의 전제를 다시 볼 것"
    for v in rows:
        assert v.get("diff_reason") and "확인 필요" not in v["diff_reason"], (v["class_code"], v["form"])


def test_설계서_수치와_같다(fixed):
    assert fixed["ate_mix"]["HH_ACUTE_ORAL|"] == {"low": 2301.1, "high": 2183.7}         # 24장 예제 1
    assert fixed["ate_mix"]["HH_ACUTE_INHAL|분진·미스트"] == {"low": 0.403, "high": 0.383}  # 24장 예제 2, 41장
