"""규칙표 항목 하나의 판정 입력 조립과 evaluate_rules 호출 시험."""
import pytest

from msds.compliance.mixture.evaluate_item import (build_flags, build_props, check_include_min, evaluate_item,
                                                   evaluate_item_range, include_min_for, rule_names)
from msds.compliance.mixture.rules_loader import load_class_map

MAP = load_class_map()["rows"]


def code(class_code, category, effect=""):
    return next(r["to21_result_code"] for r in MAP
                if (r["class_code"], r["category"], r["effect"]) == (class_code, category, effect))


def comp(name, low, high, *classes, flags=None, m=None):
    rows = [{"result_code": code(*c), "source": "KR02"} for c in classes]
    return {"cas": name, "name": name, "low": low, "high": high, "class_rows": rows, "flags": flags or [], "m": m}


def cat(item, comps, props=None, mode="low"):
    return evaluate_item(item, comps, props or {}, mode=mode)["category"]


def test_규칙표에서_뽑은_이름():
    n = rule_names()
    assert {"ph_extreme", "non_additive_1", "non_additive_2"} <= n["flag"]
    assert {"PH", "VISCOSITY_40", "STATE"} <= n["prop"]


def test_피부부식성_가산():
    comps = [comp("A", 3, 3, ("HH_SKIN_CORR", "1A")), comp("B", 3, 3, ("HH_SKIN_CORR", "1B"))]
    assert cat("HH_SKIN_CORR", comps) == "1B"
    assert cat("HH_SKIN_CORR", [comp("A", 0.5, 0.5, ("HH_SKIN_CORR", "1A"))]) == "분류안됨"  # 한계농도 1% 미만


def test_눈손상_ph_극단_표시로_구분1():
    comps = [comp("산", 2, 2, flags=["ph_extreme"])]
    r = evaluate_item("HH_EYE_DMG", comps, {}, mode="low")
    assert r["category"] == "1" and r["inputs"]["flags"] == {"ph_extreme": 2}


def test_눈손상은_피부_구분을_other로_받음():
    comps = [comp("A", 2, 2, ("HH_SKIN_CORR", "1")), comp("B", 1.5, 1.5, ("HH_EYE_DMG", "1"))]
    assert cat("HH_EYE_DMG", comps) == "1"
    low_skin = [comp("A", 0.5, 0.5, ("HH_SKIN_CORR", "1")), comp("B", 1.5, 1.5, ("HH_EYE_DMG", "1"))]
    assert cat("HH_EYE_DMG", low_skin) == "2"  # other()의 0.5%는 피부 한계농도 1% 미만이라 빠진다


def test_호흡기자극_효과_구분은_extra_규칙():
    r = evaluate_item("HH_STOT_SE", [comp("A", 25, 25, ("HH_STOT_SE", "3", "호흡기자극"))], {}, mode="low")
    assert r["category"] == "분류안됨"
    assert r["extra"] == [{"id": "STSE-3R", "category": "3", "effect": "호흡기자극"}]
    assert r["inputs"]["comps"] == {"3:호흡기자극": [25]}


def test_수생_급성_M_계수():
    one = [comp("A", 3, 3, ("ENV_AQ_ACUTE", "1"), m=10)]
    r = evaluate_item("ENV_AQ_ACUTE", one, {}, mode="low")
    assert (r["category"], r["inputs"]["m"]) == ("1", 10)
    assert cat("ENV_AQ_ACUTE", [comp("A", 3, 3, ("ENV_AQ_ACUTE", "1"))]) == "분류안됨"  # M 기본값 1 → 3 < 25


def test_수생_M이_성분마다_다르면_먼저_곱함():
    comps = [comp("A", 2, 2, ("ENV_AQ_ACUTE", "1"), m=10), comp("B", 5, 5, ("ENV_AQ_ACUTE", "1"), m=1)]
    r = evaluate_item("ENV_AQ_ACUTE", comps, {}, mode="low")
    assert r["category"] == "1" and r["inputs"]["m"] == 1  # 2×10 + 5×1 = 25
    assert any("M 계수가 달라" in a for a in r["assumptions"])


def test_흡인_점도_있음_없음():
    comps = [comp("A", 40, 40, ("HH_ASPIRATION", "1"))]
    assert cat("HH_ASPIRATION", comps, {"VISCOSITY_40": 5}) == "1"
    assert cat("HH_ASPIRATION", comps, {"VISCOSITY_40": 30}) == "분류안됨"
    r = evaluate_item("HH_ASPIRATION", comps, {"VISCOSITY_40": None}, mode="low")
    assert r["category"] == "근거부족(prop VISCOSITY_40)" and "VISCOSITY_40" not in r["inputs"]["props"]


def test_생식독성_cutoff():
    comps = [comp("A", 0.2, 0.2, ("HH_REPRO", "1A")), comp("B", 0.2, 0.2, ("HH_REPRO", "1B"))]
    assert cat("HH_REPRO", comps) == "1B"


def test_25번_황산_피부_눈_구분1():
    sul = comp("황산", 93, 98, ("HH_SKIN_CORR", "1"), ("HH_EYE_DMG", "1"))
    water = comp("물", 2, 7)
    for item in ("HH_SKIN_CORR", "HH_EYE_DMG"):
        for props in ({"PH": 1.0}, {}):
            assert cat(item, [sul, water], props) == "1"
    assert evaluate_item("HH_SKIN_CORR", [sul, water], {"PH": 1.0}, mode="low")["inputs"]["props"] == {"PH": 1.0}


def test_ph_없으면_prop은_비고_나머지_규칙으로_판정():
    r = evaluate_item("HH_SKIN_CORR", [comp("A", 3, 3, ("HH_SKIN_CORR", "1A"))], {}, mode="low")
    assert r["inputs"]["props"] == {} and r["inputs"]["flags"] == {} and r["category"] == "2"


def test_ate_transport_compare는_처리하지_않음():
    assert evaluate_item("HH_ACUTE_ORAL", [], {}, mode="low") == {"item": "HH_ACUTE_ORAL", "mode": "low",
                                                                 "category": None, "skipped": "ate"}
    assert evaluate_item("PH_FLAM_LIQ", [], {}, mode="low")["skipped"] == "transport"
    assert evaluate_item("PH_AEROSOL", [], {}, mode="low")["skipped"] == "compare"


def test_low_high가_다르면_agree_False():
    comps = [comp("A", 4, 6, ("HH_SKIN_CORR", "1A"))]
    r = evaluate_item_range("HH_SKIN_CORR", comps, {})
    assert (r["low"]["category"], r["high"]["category"], r["agree"]) == ("2", "1A", False)
    assert evaluate_item_range("HH_SKIN_CORR", [comp("A", 6, 7, ("HH_SKIN_CORR", "1A"))], {})["agree"] is True


def test_build_props와_build_flags():
    assert build_props({"PH": 2, "VISCOSITY_40": None, "ETC": 1}) == {"PH": 2}
    comps = [comp("A", 2, 3, flags=["non_additive_2", "모르는표시"]), comp("B", 0.5, 0.5, flags=["non_additive_2"])]
    assert build_flags(comps, {}, mode="high", include_min=1.0) == {"non_additive_2": 3}


def test_include_min_은_규칙표_우선이고_cut_off와_비교():
    assert include_min_for("HH_RESP_SENS") == 0.1
    chk = check_include_min()
    assert isinstance(chk["not_in_cut_off"], list) and isinstance(chk["differs"], dict)
