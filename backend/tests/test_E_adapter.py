"""GhsInputs → label·acute 입력 어댑터 시험 (25번 황산 예제)."""
import json
from pathlib import Path

import pytest

from msds.compliance.label import derive_label
from msds.compliance.loader import load_ghs_inputs
from msds.compliance.mixture.adapter import stated_mix_ate, to_acute_components, to_label_classes

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "to21" / "v0.6" / "TO21_MSDS_추출예제_25_황산_v0.6.json"


@pytest.fixture(scope="module")
def inputs():
    return load_ghs_inputs(json.loads(EXAMPLE.read_text(encoding="utf-8")))


def test_라벨_입력(inputs):
    r = derive_label(to_label_classes(inputs))
    assert r["pictograms"] == ["GHS05", "GHS06", "GHS08"]
    assert r["signal_word"] == "위험"


def test_성분_함량과_경구_독성값(inputs):
    comps = to_acute_components(inputs)
    assert len(comps) == 2
    sulfuric = comps[0]
    assert (sulfuric["content_lower"], sulfuric["content_upper"]) == (93, 98)
    assert {"route": "경구", "op": "=", "value": 2140, "unit": "mg/kg"} in sulfuric["tox"]


def test_표기된_혼합물_ATE(inputs):
    oral = next(x for x in stated_mix_ate(inputs) if x["route"] == "경구")
    assert (oral["lower_op"], oral["lower"]) == (">", 2000)
    assert (oral["upper_op"], oral["upper"]) == ("<=", 5000)


def test_노출시간이_hours로_넘어감(inputs):
    mist = next(t for t in to_acute_components(inputs)[0]["tox"] if t["route"] == "흡입")
    assert mist["hours"] == 4
    oral = next(t for t in to_acute_components(inputs)[0]["tox"] if t["route"] == "경구")
    assert "hours" not in oral
