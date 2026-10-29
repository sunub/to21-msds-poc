"""급성독성 조립 classify_acute 시험 (설계서 24·41장)."""
import pytest

from msds.compliance.mixture.acute_classify import classify_acute


def comp(name, low, high=None, cas=None, **kw):
    return {"name": name, "cas": cas, "content": {"low": low, "high": low if high is None else high},
            "non_toxic": False, "db": [], "classes": [], "msds": [], **kw}


def row(route="oral", value=100, op="=", unit="mg/kg", form=None, **kw):
    return {"route": route, "form": form, "value": value, "unit": unit, "op": op, **kw}


def sulfuric():
    s = comp("황산", 93, 98, "7664-93-9", db=[row(value=2140), row("inhal", 0.375, unit="mg/L", form="mist", hours=4)])
    return [s, comp("물", 2, 7, "7732-18-5", non_toxic=True)]


def pick(res, code, form=None):
    return next(r for r in res if r["class_code"] == code and r["form"] == form)


def test_황산_전체():
    res = classify_acute(sulfuric(), "액체", knowledge_version="v1")
    assert [(r["class_code"], r["form"]) for r in res] == [
        ("HH_ACUTE_ORAL", None), ("HH_ACUTE_DERMAL", None), ("HH_ACUTE_INHAL", "증기"), ("HH_ACUTE_INHAL", "분진·미스트")]
    oral = pick(res, "HH_ACUTE_ORAL")
    assert oral["result"] == {"low": "분류안됨", "high": "분류안됨", "status": "확정"}
    assert "ref_cat5" in oral["inputs"][0]["flags"]
    mist = pick(res, "HH_ACUTE_INHAL", "분진·미스트")
    assert mist["result"] == {"low": "2", "high": "2", "status": "확정"}
    assert mist["knowledge_version"] == "v1"
    c = mist["calc"]
    assert c["sum_low"] == pytest.approx(248.0, rel=1e-3) and c["sum_high"] == pytest.approx(261.3, rel=1e-3)
    assert c["ate_mix_low"] == pytest.approx(0.403, rel=1e-3) and c["ate_mix_high"] == pytest.approx(0.383, rel=1e-3)
    a, w = mist["inputs"]
    assert (a["cas"], a["ate_used"], a["source"], a["step"], a["share"]) == ("7664-93-9", 0.375, "TO21 독성DB", 1, 1.0)
    assert (w["excluded"], w["step"]) == ("무독성", 5)
    assert mist["thresholds"][0] == {"category": "2", "range": "0.05 < x ≤ 0.5", "rule_id": "ATE-INHAL-MIST"}
    assert mist["assumptions"] == ["흡입 형태: 제품 성상으로 선택(D-06)"]
    assert pick(res, "HH_ACUTE_DERMAL")["result"]["status"] == "근거부족"
    assert pick(res, "HH_ACUTE_INHAL", "증기")["result"]["status"] == "근거부족"


@pytest.mark.parametrize("state, forms", [("기체", ["가스"]), ("고체", ["분진·미스트"])])
def test_성상별_흡입_형태(state, forms):
    res = classify_acute(sulfuric(), state)
    assert [r["form"] for r in res if r["class_code"] == "HH_ACUTE_INHAL"] == forms


def test_성상_미상은_흡입_세_형태():
    for state in (None, "플라즈마"):
        res = classify_acute(sulfuric(), state)
        inhal = [r for r in res if r["class_code"] == "HH_ACUTE_INHAL"]
        assert [r["form"] for r in inhal] == ["가스", "증기", "분진·미스트"]
        assert all(r["assumptions"] == ["제품 성상 미상 — 흡입 형태 전체 계산"] for r in inhal)
        assert pick(res, "HH_ACUTE_ORAL")["assumptions"] == []


def test_예제3_공식2():
    parts = [comp("A", 10, db=[row(value=352)]),
             comp("B", 5, classes=[{"class_code": "HH_ACUTE_ORAL", "category": "3", "source": "환경부"}]),
             comp("C", 50, db=[row(value=3000)]), comp("D", 5, db=[row(value=2000, op=">")]),
             comp("E", 20), comp("F", 10, db=[row(value=250)])]
    r = pick(classify_acute(parts, "액체"), "HH_ACUTE_ORAL")
    assert r["calc"]["formula_used"] == "공식2" and r["calc"]["unknown_pct"] == 20
    assert r["calc"]["ate_mix_low"] == pytest.approx(592.3, rel=1e-3)
    assert r["result"]["low"] == r["result"]["high"] == "4"
    assert r["rule"]["formula"].startswith("(100 − 이용불가)")
    by = {i["name"]: i for i in r["inputs"]}
    assert by["D"]["excluded"] == "부등호 값" and by["E"]["excluded"] == "자료 없음"
    assert by["B"]["ate_used"] == 100 and "share" in by["B"]


def test_경계_판정():
    r = pick(classify_acute([comp("A", 40, 60, db=[row(value=150)])], "액체"), "HH_ACUTE_ORAL")
    assert r["result"] == {"low": "4", "high": "3", "status": "경계"}
    assert [t["category"] for t in r["thresholds"]] == ["4", "3"]


def test_결정론():
    assert classify_acute(sulfuric(), "액체") == classify_acute(sulfuric(), "액체")
