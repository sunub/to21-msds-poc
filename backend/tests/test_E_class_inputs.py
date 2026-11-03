"""성분별 분류결과코드 → evaluate_rules 입력 조립 시험."""
import pytest

from msds.compliance.mixture.class_inputs import build_class_inputs, check_category_coverage
from msds.compliance.mixture.rule_eval import evaluate_rules
from msds.compliance.mixture.rules_loader import load_class_map, load_mixture_rules, lookup_class

MAP = load_class_map()["rows"]


def code(class_code, category, effect=""):
    return next(r["to21_result_code"] for r in MAP
                if (r["class_code"], r["category"], r["effect"]) == (class_code, category, effect))


def comp(cas, low, high, *rows):
    return {"cas": cas, "name": cas, "low": low, "high": high,
            "class_rows": [{"result_code": c, "source": s} for c, s in rows]}


def test_실제_코드가_연결됨():
    assert lookup_class(code("HH_SKIN_CORR", "1A"))[:2] == ("HH_SKIN_CORR", "1A")
    assert lookup_class(code("HH_STOT_SE", "3", "호흡기자극"))[2:] == (None, "호흡기자극")
    assert lookup_class(code("HH_RESP_SENS", "1B"))[:2] == ("HH_RESP_SENS", "1B")


def test_같은_구분은_함량이_모인다():
    r = build_class_inputs([comp("A", 3, 4, (code("HH_SKIN_CORR", "1A"), "KR02")),
                            comp("B", 2, 5, (code("HH_SKIN_CORR", "1A"), "KR02"))], mode="low")
    assert r["by_class"] == {"HH_SKIN_CORR": {"1A": [3, 2]}}
    assert len(r["used"]) == 2 and r["dropped"] == []


def test_효과_구분은_category_effect_키():
    r = build_class_inputs([comp("A", 25, 25, (code("HH_STOT_SE", "3", "호흡기자극"), "KR03"),
                                 (code("HH_STOT_SE", "1"), "KR03"))], mode="high")
    assert r["by_class"] == {"HH_STOT_SE": {"3:호흡기자극": [25], "1": [25]}}


def test_출처가_겹치면_우선순위_높은_출처만():
    skin = comp("A", 6, 6, (code("HH_SKIN_CORR", "1A"), "KR03"), (code("HH_SKIN_CORR", "1B"), "KR02"))
    r = build_class_inputs([skin], mode="low")
    assert r["by_class"] == {"HH_SKIN_CORR": {"1B": [6]}}  # 기본값: 환경부(KR02) → 고용노동부(KR03)
    assert any("우선순위가 낮은 출처" in d["reason"] for d in r["dropped"])
    assert any("환경부; 고용노동부" in a and "기본값" in a for a in r["assumptions"])
    r2 = build_class_inputs([skin], mode="low", source_order=["고용노동부", "환경부"])
    assert r2["by_class"] == {"HH_SKIN_CORR": {"1A": [6]}}
    assert not any("기본값" in a for a in r2["assumptions"])


def test_NONE과_없는_코드는_제외():
    r = build_class_inputs([comp("A", 5, 5, ("GHS999999", "KR02"), ("GHS123456", "KR02"),
                                 (code("HH_CARCINOGEN", "1A"), "KR02"))], mode="low")
    assert r["by_class"] == {"HH_CARCINOGEN": {"1A": [5]}}
    reasons = " | ".join(d["reason"] for d in r["dropped"])
    assert "NONE" in reasons and "class_map에 없는" in reasons


def test_low와_high는_함량이_다름():
    comps = [comp("A", 3, 8, (code("HH_SKIN_CORR", "1"), "KR02"))]
    assert build_class_inputs(comps, mode="low")["by_class"]["HH_SKIN_CORR"]["1"] == [3]
    assert build_class_inputs(comps, mode="high")["by_class"]["HH_SKIN_CORR"]["1"] == [8]


def test_함량_None은_목록에서_빠짐():
    r = build_class_inputs([comp("A", None, 5, (code("HH_SKIN_CORR", "1"), "KR02")),
                            comp("B", 4, 4, (code("HH_SKIN_CORR", "1"), "KR02"))], mode="low")
    assert r["by_class"] == {"HH_SKIN_CORR": {"1": [4]}}
    assert r["dropped"] == [{"cas": "A", "name": "A", "reason": "함량(low) 없음"}]


def test_mode가_잘못되면_오류():
    with pytest.raises(ValueError):
        build_class_inputs([], mode="mid")


def test_실제_규칙표_피부부식성_판정():
    rules = load_mixture_rules()["classes"]["HH_SKIN_CORR"]
    comps = [comp("A", 3, 3, (code("HH_SKIN_CORR", "1A"), "KR02")),
             comp("B", 3, 3, (code("HH_SKIN_CORR", "1B"), "KR02")),
             comp("C", 90, 90, ("GHS999999", "KR02"))]
    by = build_class_inputs(comps, mode="low")["by_class"]
    got = evaluate_rules(rules["rules"], by.get("HH_SKIN_CORR", {}), other=by, include_min=rules["include_min"])
    assert got == "1B"  # 1A 3% + 1B 3% = 6% ≥ 5 → 1B (규칙표 예제와 같음)


def test_실제_규칙표_눈손상은_피부_구분을_other로_받음():
    rules = load_mixture_rules()["classes"]["HH_EYE_DMG"]
    comps = [comp("A", 2, 2, (code("HH_SKIN_CORR", "1"), "KR02")),
             comp("B", 1.5, 1.5, (code("HH_EYE_DMG", "1"), "KR02"))]
    by = build_class_inputs(comps, mode="low")["by_class"]
    assert evaluate_rules(rules["rules"], by["HH_EYE_DMG"], other=by, include_min=rules["include_min"]) == "1"


def test_구분_범위_점검은_목록만_돌려줌():
    cov = check_category_coverage()
    assert cov and all(set(v) == {"in_map_unused", "used_not_in_map"} for v in cov.values())
    assert "HH_ACUTE_ORAL" not in cov  # when이 없는 항목은 건너뜀
