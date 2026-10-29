"""혼합물 급성독성 ATEmix 시험."""
import json
from pathlib import Path

import pytest

from msds.compliance.mixture.acute import ate_mix, category_to_ate, value_to_category

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "to21" / "v0.5" / "TO21_MSDS_추출예제_25_황산_v0.5.json"


def test_slide_example():
    parts = [
        {"c": 10, "ate": 352, "known": True},
        {"c": 5, "ate": category_to_ate("경구", None, 3), "known": True},
        {"c": 50, "ate": 3000, "known": True},
        {"c": 5, "ate": None, "known": True},
        {"c": 20, "ate": None, "known": False},
        {"c": 10, "ate": 250, "known": True},
    ]
    ate, formula = ate_mix(parts)
    assert formula == "공식2"
    assert ate == pytest.approx(592.26, abs=0.01)


def test_70_30():
    parts = [
        {"c": 70, "ate": category_to_ate("경구", None, 2), "known": True},
        {"c": 30, "ate": category_to_ate("경구", None, 3), "known": True},
    ]
    ate, formula = ate_mix(parts)
    assert formula == "공식1"
    assert ate == pytest.approx(6.99, abs=0.01)
    assert value_to_category("경구", None, ate) == "2"


@pytest.mark.skipif(not EXAMPLE.exists(), reason="TO21 제공 파일이 없습니다")
def test_sulfuric_acid():
    json.loads(EXAMPLE.read_text(encoding="utf-8"))
    for c in (93, 98):
        parts = [{"c": c, "ate": 2140, "known": True}, {"c": 100 - c, "ate": None, "known": True}]
        ate, _ = ate_mix(parts)
        assert 2000 < ate <= 5000
        assert value_to_category("경구", None, ate) is None
