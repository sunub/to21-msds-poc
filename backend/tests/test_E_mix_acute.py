"""혼합물 급성독성 mix_acute 시험 (설계서 24장 예제 포함)."""
import pytest

from msds.compliance.mixture.acute import mix_acute


def comp(name, low, high, kind, value=None):
    return {"name": name, "cas": None, "content": {"low": low, "high": high},
            "ate": {"kind": kind, "value": value, "src": "시험", "step": None}}


def one(pct, ate, route="oral", form=None):
    return mix_acute([comp("A", pct, pct, "value", ate)], route, form)["low"]


def test_예제1_경구_황산():
    r = mix_acute([comp("황산", 93, 98, "value", 2140), comp("물", 2, 7, "non_toxic")], "oral")
    assert r["low"]["ate_mix"] == pytest.approx(2301.1, rel=1e-3)
    assert r["high"]["ate_mix"] == pytest.approx(2183.7, rel=1e-3)
    assert r["low"]["category"] == r["high"]["category"] == "분류안됨"
    assert r["low"]["ref_cat5"] and r["high"]["ref_cat5"]
    assert r["status"] == "확정"


def test_예제2_흡입_미스트():
    r = mix_acute([comp("황산", 93, 98, "value", 0.375), comp("물", 2, 7, "non_toxic")], "inhal", "mist")
    assert r["low"]["ate_mix"] == pytest.approx(0.403, rel=1e-3)
    assert r["high"]["ate_mix"] == pytest.approx(0.383, rel=1e-3)
    assert r["low"]["category"] == r["high"]["category"] == "2"
    assert r["status"] == "확정"


def test_예제3_공식2():
    parts = [comp("A", 10, 10, "value", 352), comp("B", 5, 5, "conversion", 100), comp("C", 50, 50, "value", 3000),
             comp("D", 5, 5, "inequality"), comp("E", 20, 20, "unknown"), comp("F", 10, 10, "value", 250)]
    r = mix_acute(parts, "oral")
    assert r["low"]["formula"] == "공식2"
    assert r["low"]["ate_mix"] == pytest.approx(592.3, rel=1e-3)
    assert r["low"]["category"] == "4"


@pytest.mark.parametrize("ate, cat", [(300, "3"), (300.1, "4"), (2000, "4"), (2000.1, "분류안됨")])
def test_경계값(ate, cat):
    assert one(100, ate)["category"] == cat


def test_한계농도_미만은_건너뜀():
    base = mix_acute([comp("A", 100, 100, "value", 300)], "oral")
    r = mix_acute([comp("A", 100, 100, "value", 300), comp("B", 0.5, 0.5, "value", 1)], "oral")
    assert r["low"] == base["low"]
    assert r["terms"][1]["사용여부"]["low"] == "한계농도미만"


def test_경계_판정():
    r = mix_acute([comp("A", 40, 60, "value", 150)], "oral")
    assert r["low"]["ate_mix"] == pytest.approx(375) and r["low"]["category"] == "4"
    assert r["high"]["ate_mix"] == pytest.approx(250) and r["high"]["category"] == "3"
    assert r["status"] == "경계"


@pytest.mark.parametrize("unknown, formula", [(10, "공식1"), (10.1, "공식2")])
def test_공식_선택(unknown, formula):
    r = mix_acute([comp("U", unknown, unknown, "unknown"), comp("A", 100 - unknown, 100 - unknown, "value", 100)], "oral")
    assert r["low"]["formula"] == formula


def test_근거부족과_자료없음():
    r = mix_acute([comp("U", 20, 20, "unknown"), comp("W", 80, 80, "non_toxic")], "oral")
    assert r["low"]["ate_mix"] is None and r["low"]["category"] == "분류안됨" and r["status"] == "근거부족"
    assert mix_acute([comp("W", 100, 100, "non_toxic")], "oral")["status"] == "확정"
