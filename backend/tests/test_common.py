"""common/ 의 모델과 성분 참조 맞춤 시험."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from msds.common.align import comp_map
from msds.common.models import ExtractionDoc, Quantity

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "to21" / "v0.5" / "TO21_MSDS_추출예제_25_황산_v0.5.json"


def test_empty_fields_are_allowed():
    doc = ExtractionDoc.model_validate({"msds": [{"components": [{"name": "A", "cas_no": None}]}]})
    assert doc.msds[0].hazard is None
    assert doc.msds[0].components[0].cas_no is None


def test_unknown_fields_are_ignored():
    doc = ExtractionDoc.model_validate({"msds": [{"product": {"name": "x"}, "extras": []}]})
    assert len(doc.msds) == 1


def test_text_digit_is_not_coerced():
    # category 는 글자 "1" 이어야 한다. 숫자 1 이 들어오면 거부한다.
    ok = {"msds": [{"hazard": {"classes": [{"category": "1"}]}}]}
    bad = {"msds": [{"hazard": {"classes": [{"category": 1}]}}]}
    assert ExtractionDoc.model_validate(ok).msds[0].hazard.classes[0].category == "1"
    with pytest.raises(ValidationError):
        ExtractionDoc.model_validate(bad)


def test_number_as_text_is_rejected():
    with pytest.raises(ValidationError):
        Quantity.model_validate({"lower": "93"})


def test_int_is_accepted_for_number():
    assert Quantity.model_validate({"lower": 93, "upper": 98.5}).lower == 93


@pytest.mark.parametrize("field,value", [
    ("lower_op", "=>"),
    ("upper_op", ">"),
    ("status", "있음"),
])
def test_out_of_range_values_are_rejected(field, value):
    with pytest.raises(ValidationError):
        Quantity.model_validate({field: value})


def test_models_are_frozen():
    q = Quantity.model_validate({"lower": 1})
    with pytest.raises(ValidationError):
        q.lower = 2


def test_comp_map_prefers_cas_then_name():
    m = {"components": [
        {"seq": 1, "name": "가", "cas_no": "7664-93-9"},
        {"seq": 2, "name": "나", "cas_no": None},
        {"seq": 3, "name": None, "cas_no": None},
    ]}
    assert comp_map(m) == {"1": "7664-93-9", "2": "나"}


def test_comp_map_has_no_mix_key():
    assert "MIX" not in comp_map({"components": [{"seq": 1, "cas_no": "7664-93-9"}]})


def test_comp_map_handles_missing_components():
    assert comp_map({}) == {}
    assert comp_map({"components": None}) == {}


@pytest.mark.skipif(not EXAMPLE.exists(), reason="TO21 제공 파일이 없습니다 (to21/README.md 참고)")
def test_to21_example_parses_and_maps():
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    doc = ExtractionDoc.model_validate(data)
    msds = doc.msds[0]
    assert msds.composition.type == "혼합물"
    assert len(msds.components) == 2
    assert set(comp_map(data["msds"][0])) == {"1", "2"}
