"""혼합물 분류 결과 조립(classify_item, classify_mixture_all)과 evaluate_rules_trace 시험."""
import pytest

from msds.compliance.mixture.classify_mixture import classify_item, classify_mixture_all
from msds.compliance.mixture.rule_eval import evaluate_rules, evaluate_rules_trace
from msds.compliance.mixture.rules_loader import load_class_map, load_mixture_rules

MAP = load_class_map()["rows"]
RULES = load_mixture_rules()


def code(class_code, category, effect=""):
    return next(r["to21_result_code"] for r in MAP
                if (r["class_code"], r["category"], r["effect"]) == (class_code, category, effect))


def comp(name, low, high, *classes, **kw):
    rows = [{"result_code": code(*c), "source": "KR02"} for c in classes]
    return {"cas": name, "name": name, "low": low, "high": high, "class_rows": rows, "flags": [], "m": None, **kw}


def sulfuric():
    sul = comp("황산", 93, 98, ("HH_SKIN_CORR", "1"), ("HH_EYE_DMG", "1"), ("HH_ACUTE_INHAL", "2"),
               db=[{"route": "oral", "form": None, "value": 2140, "unit": "mg/kg", "op": "="},
                   {"route": "inhal", "form": "mist", "value": 0.375, "unit": "mg/L", "op": "=", "hours": 4}])
    return [sul, comp("물", 2, 7, non_toxic=True)]


SKIN = [{"id": "S1", "category": "1", "when": 'sum("1") >= 5'},
        {"id": "S2", "category": "2", "when": 'sum("2") >= 10 or has("PH") and prop("PH") <= 2'},
        {"id": "S3", "category": "3", "when": 'sum("3") >= 1'}]


@pytest.mark.parametrize("comps, kw", [({"1": [7]}, {}), ({"1": [1], "2": [12]}, {}), ({}, {}),
                                       ({"3": [2]}, {"props": {"PH": 1.0}}), ({"1": [(30, 10)]}, {"m": 2})])
def test_trace와_evaluate_rules는_같은_판정(comps, kw):
    assert evaluate_rules_trace(SKIN, comps, **kw)["category"] == evaluate_rules(SKIN, comps, **kw)


def test_trace는_처음_참인_규칙까지만_담음():
    t = evaluate_rules_trace(SKIN, {"1": [1], "2": [12]})
    assert t["rule_id"] == "S2" and [r["id"] for r in t["checked"]] == ["S1", "S2"]
    assert [r["result"] for r in t["checked"]] == [False, True]
    assert t["checked"][1]["values"] == {'sum("2")': 12, 'has("PH")': False, 'prop("PH")': None}  # PH 없음 → None


def test_trace_분류안됨과_근거부족():
    t = evaluate_rules_trace(SKIN, {})
    assert (t["category"], t["rule_id"], len(t["checked"])) == ("분류안됨", None, 3)
    asp = [{"id": "A", "category": "1", "when": 'sum("1") >= 10 and prop("VISCOSITY_40") <= 20.5'}]
    t = evaluate_rules_trace(asp, {"1": [40]})
    assert t["category"] == "근거부족(prop VISCOSITY_40)" == evaluate_rules(asp, {"1": [40]})
    assert t["checked"][0]["result"] == "근거부족" and t["checked"][0]["values"]['prop("VISCOSITY_40")'] is None


def test_황산_피부_눈_확정():
    for item in ("HH_SKIN_CORR", "HH_EYE_DMG"):
        r = classify_item(item, sulfuric(), {"PH": 1.0})
        assert r["result"] == {"low": "1", "high": "1", "status": "확정"}, item
        assert r["class_code"] == item and r["form"] is None
        assert r["knowledge_version"] == RULES["meta"]["version"] and r["rule"]["basis"] == RULES["meta"]["source"]


def test_피부_부식성_결과_모양():
    r = classify_item("HH_SKIN_CORR", sulfuric(), {"PH": 1.0})
    assert r["rule"]["id"] == "SKIN-PH" and "prop(\"PH\")" in r["rule"]["formula"]
    sul, water = r["inputs"]
    assert (sul["used_as"], sul["excluded"]) == (["1"], None)
    assert (water["used_as"], water["excluded"]) == ([], "분류 정보 없음")
    assert r["calc"]["values"]["low"]['prop("PH")'] == 1.0 and r["calc"]["include_min"] == 1.0
    assert r["thresholds"][0] == {"side": "low", "category": "1", "rule_id": "SKIN-PH",
                                  "when": RULES["classes"]["HH_SKIN_CORR"]["rules"][0]["when"], "result": True}


def test_경계_하한_상한에서_구분이_갈림():
    r = classify_item("HH_SKIN_CORR", [comp("A", 4, 6, ("HH_SKIN_CORR", "1A"))], {})
    assert r["result"] == {"low": "2", "high": "1A", "status": "경계"}
    assert r["rule"]["id"] == {"low": "SKIN-2", "high": "SKIN-1A"}


def test_근거부족_점도_없음():
    r = classify_item("HH_ASPIRATION", [comp("A", 40, 40, ("HH_ASPIRATION", "1"))], {})
    assert r["result"]["status"] == "근거부족" and r["result"]["low"] is None and r["result"]["high"] is None
    assert r["result"]["reason"] == "근거부족(prop VISCOSITY_40)"
    ok = classify_item("HH_ASPIRATION", [comp("A", 40, 40, ("HH_ASPIRATION", "1"))], {"VISCOSITY_40": 5})
    assert ok["result"] == {"low": "1", "high": "1", "status": "확정"}


def test_분류안됨은_확정():
    r = classify_item("HH_CARCINOGEN", [comp("A", 50, 50, ("HH_SKIN_CORR", "1"))], {})
    assert r["result"] == {"low": "분류안됨", "high": "분류안됨", "status": "확정"}
    assert r["rule"]["id"] is None and r["rule"]["formula"] is None
    assert r["inputs"][0]["excluded"] == "해당 분류 없음"


def test_한계농도_미만_성분과_함량_없음():
    r = classify_item("HH_SKIN_CORR", [comp("A", 0.5, 0.5, ("HH_SKIN_CORR", "1A")),
                                       comp("B", None, None, ("HH_SKIN_CORR", "1"))], {})
    assert r["result"]["status"] == "확정"
    a, b = r["inputs"]
    assert a["excluded"] == "한계농도 미만" and b["excluded"] == "함량 없음"


def test_효과_구분은_extra로():
    r = classify_item("HH_STOT_SE", [comp("A", 25, 25, ("HH_STOT_SE", "3", "호흡기자극"))], {})
    assert r["result"]["low"] == "분류안됨" and r["extra"]["low"][0]["id"] == "STSE-3R"


def test_ate_transport_compare는_건너뜀():
    assert classify_item("HH_ACUTE_ORAL", [], {}) == {"class_code": "HH_ACUTE_ORAL", "skipped": "ate"}
    assert classify_item("PH_FLAM_LIQ", [], {}) == {"class_code": "PH_FLAM_LIQ", "skipped": "transport"}
    assert classify_item("PH_AEROSOL", [], {}) == {"class_code": "PH_AEROSOL", "skipped": "compare"}


def test_전체_항목이_빠짐없이_나옴():
    out = classify_mixture_all(sulfuric(), {"PH": 1.0}, state="액체")
    codes = [r["class_code"] for r in out]
    assert set(codes) == set(RULES["classes"]) and len(RULES["classes"]) == 32
    methods = {n: i["method"] for n, i in RULES["classes"].items()}
    skipped = {r["class_code"]: r["skipped"] for r in out if "skipped" in r}
    assert skipped == {n: m for n, m in methods.items() if m in ("transport", "compare")}
    acute = [r for r in out if r["class_code"].startswith("HH_ACUTE")]
    assert {r["class_code"] for r in acute} == {"HH_ACUTE_ORAL", "HH_ACUTE_DERMAL", "HH_ACUTE_INHAL"}
    mist = next(r for r in acute if r["form"] == "분진·미스트")
    assert mist["result"] == {"low": "2", "high": "2", "status": "확정"}
    evaluated = [r for r in out if "result" in r and not r["class_code"].startswith("HH_ACUTE")]
    assert len(evaluated) + len(skipped) + len({r["class_code"] for r in acute}) == 32
