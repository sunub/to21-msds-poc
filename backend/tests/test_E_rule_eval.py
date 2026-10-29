import pytest

from msds.compliance.mixture.rule_eval import evaluate_rules

C1 = '"1","1A","1B","1C"'
SKIN = [
    {"id": "SKIN-PH", "category": "1", "when": 'has("PH") and (prop("PH") <= 2 or prop("PH") >= 11.5)'},
    {"id": "SKIN-1X", "category": "1", "when": 'flag("ph_extreme") >= 1 or flag("non_additive_1") >= 1'},
    {"id": "SKIN-1", "category": "1", "when": f'sum("1") > 0 and sum({C1}) >= 5'},
    {"id": "SKIN-1A", "category": "1A", "when": 'sum("1A") >= 5'},
    {"id": "SKIN-1B", "category": "1B", "when": 'sum("1A","1B") >= 5'},
    {"id": "SKIN-1C", "category": "1C", "when": 'sum("1A","1B","1C") >= 5'},
    {"id": "SKIN-2X", "category": "2", "when": 'flag("non_additive_2") >= 3'},
    {"id": "SKIN-2", "category": "2", "when": f'sum({C1}) >= 1 or sum("2") >= 10 or 10*sum({C1}) + sum("2") >= 10'},
]
ASP = [
    {"id": "ASP-1", "category": "1", "when": 'sum("1") >= 10 and prop("VISCOSITY_40") <= 20.5'},
    {"id": "ASP-2", "category": "2", "when": 'sum("2") >= 10 and prop("VISCOSITY_40") <= 14'},
]
AQC = [
    {"id": "AQC-1", "category": "1", "when": 'sumx("1") >= 25'},
    {"id": "AQC-2", "category": "2", "when": '10*sumx("1") + sum("2") >= 25'},
    {"id": "AQC-3", "category": "3", "when": '100*sumx("1") + 10*sum("2") + sum("3") >= 25'},
]


@pytest.mark.parametrize("comps, kw, out", [
    ({"1": [3]}, {}, "2"),
    ({"1": [7]}, {}, "1"),
    ({"1A": [3], "1B": [3]}, {}, "1B"),
    ({"1A": [6]}, {}, "1A"),
    ({"2": [11]}, {}, "2"),
    ({"1": [0.5]}, {"include_min": 1.0}, "분류안됨"),
    ({}, {"flags": {"ph_extreme": 2}}, "1"),
    ({}, {"props": {"PH": 1.0}}, "1"),
    ({}, {"flags": {"non_additive_2": 4}}, "2"),
])
def test_skin(comps, kw, out):
    assert evaluate_rules(SKIN, comps, **kw) == out


def test_aspiration_and_missing_prop():
    assert evaluate_rules(ASP, {"1": [40]}, props={"VISCOSITY_40": 5}) == "1"
    assert evaluate_rules(ASP, {"1": [40]}, props={"VISCOSITY_40": 30}) == "분류안됨"
    assert evaluate_rules(ASP, {"2": [20]}, props={"VISCOSITY_40": 10}) == "2"
    assert evaluate_rules(ASP, {"1": [40]}) == "근거부족(prop VISCOSITY_40)"


def test_aquatic_m_factor():
    assert evaluate_rules(AQC, {"1": [3]}) == "2"
    assert evaluate_rules(AQC, {"1": [1], "3": [6]}) == "3"
    assert evaluate_rules(AQC, {"1": [3]}, m=10) == "1"


def test_other_and_effect_and_dict_include_min():
    eye = [{"id": "E", "category": "1", "when": 'other("HH_SKIN_CORR","1") + sum("1") >= 3'}]
    assert evaluate_rules(eye, {"1": [1.5]}, other={"HH_SKIN_CORR": {"1": [2]}}) == "1"
    stot = [{"id": "S", "category": "3", "when": 'sum("3:호흡기자극") >= 20'}]
    assert evaluate_rules(stot, {"3:호흡기자극": [25]}) == "3"
    assert evaluate_rules(stot, {"3:호흡기자극": [25]}, include_min={"3": 30}) == "분류안됨"


@pytest.mark.parametrize("when", ['__import__("os")', 'open("x")', 'x > 1', 'sum("1")[0] > 1'])
def test_rejects_unsafe_expression(when):
    with pytest.raises(ValueError):
        evaluate_rules([{"id": "X", "category": "1", "when": when}], {})
