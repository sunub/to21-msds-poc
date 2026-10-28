import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from msds.compliance.ghs.models import ClassificationDecision, GhsInputs
from msds.compliance.loader import load_ghs_inputs


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "to21" / "v0.5" / "TO21_MSDS_추출예제_25_황산_v0.5.json"
needs_example = pytest.mark.skipif(
    not EXAMPLE.exists(), reason="TO21 제공 파일이 없습니다 (to21/README.md 참고)"
)


@needs_example
def test_typed_loader_preserves_sulfuric_acid_contract():
    doc = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    inputs = load_ghs_inputs(doc)

    assert isinstance(inputs, GhsInputs)
    assert inputs.doc_id == "T21-025"
    assert inputs.msds_index == 0
    assert inputs.components[0].content is not None
    assert inputs.components[0].content.lower == 93
    assert inputs.components[0].content.upper == 98
    inhalation = next(
        item for item in inputs.hazard.classes if item.class_code == "HH_ACUTE_INHAL"
    )
    assert inhalation.route_form == "증기"
    assert "BOILING" in inputs.physchem
    assert "BOILING_POINT" not in inputs.physchem


def test_typed_loader_selects_msds_and_preserves_quantity_range():
    doc = {
        "doc": {"doc_id": "T21-MULTI"},
        "msds": [
            {"composition": {"type": "단일물질"}},
            {
                "meta": {"last_revision_date": "2026-10-26"},
                "composition": {"type": "혼합물"},
                "components": [
                    {
                        "seq": 1,
                        "name": "성분 A",
                        "cas_no": "64-17-5",
                        "content": {
                            "raw": "40~<50",
                            "lower_op": ">=",
                            "lower": 40,
                            "upper_op": "<",
                            "upper": 50,
                            "unit": "%",
                            "status": "값있음",
                        },
                    }
                ],
                "hazard": {
                    "classes": [
                        {"class_code": "PH_FLAM_LIQ", "category": "2"}
                    ],
                    "signal_word": "위험",
                },
                "physchem": [{"prop_code": "BOILING", "q": {"value": 78.5}}],
            },
        ],
    }

    inputs = load_ghs_inputs(doc, 1)

    assert inputs.msds_index == 1
    assert inputs.as_of_date == "2026-10-26"
    assert inputs.composition.type == "혼합물"
    content = inputs.components[0].content
    assert content is not None
    assert (content.lower_op, content.lower, content.upper_op, content.upper) == (
        ">=",
        40,
        "<",
        50,
    )
    assert list(inputs.physchem) == ["BOILING"]


def test_classification_decision_carries_rule_provenance():
    decision = ClassificationDecision(
        class_code="HH_ACUTE_INHAL",
        category="2",
        route_form="증기",
        status="확정",
        rule_id="ATE-MIX-1",
        rule_version="고용노동부고시-2026-26",
        valid_from="2026-04-24",
        source="별표1 3.1",
        evidence=[{"ate_mix": 0.4, "unit": "mg/L"}],
    )

    assert decision.route_form == "증기"
    assert decision.status == "확정"
    assert decision.valid_from == "2026-04-24"
    assert decision.evidence[0]["ate_mix"] == 0.4


def test_typed_loader_preserves_physchem_row_without_code():
    inputs = load_ghs_inputs(
        {"msds": [{"physchem": [{"prop_code": None, "q": {"status": "미기재"}}]}]}
    )

    assert inputs.physchem[None][0]["q"]["status"] == "미기재"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"class_code": "HH_ACUTE_INHAL", "route_form": None},
        {"class_code": "HH_ACUTE_INHAL_VAPOUR", "route_form": "증기"},
        {"class_code": "HH_ACUTE_ORAL", "route_form": "증기"},
    ],
)
def test_classification_decision_rejects_invalid_inhalation_contract(kwargs):
    with pytest.raises(ValidationError):
        ClassificationDecision(
            category="2",
            status="확정",
            rule_id="RULE-1",
            rule_version="2026-26",
            valid_from="2026-04-24",
            source="별표1",
            evidence=[{"input": "test"}],
            **kwargs,
        )


def test_definite_classification_requires_evidence():
    with pytest.raises(ValidationError):
        ClassificationDecision(
            class_code="PH_FLAM_LIQ",
            category="2",
            status="확정",
            rule_id="FLQ-2",
            rule_version="2026-26",
            valid_from="2026-04-24",
            source="별표1",
        )
