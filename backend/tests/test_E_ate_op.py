"""급성독성 값의 부등호·범위가 판정까지 보존되는지 시험 (intervals=True). 기본(False)은 기존 규칙 D-12 그대로."""
import json
from pathlib import Path

import pytest

from msds.compliance.mixture.acute_classify import classify_acute
from msds.compliance.mixture.adapter import to_acute_components
from msds.compliance.mixture.ate_source import get_ate
from msds.compliance.mixture.build_components import build_components
from msds.compliance.mixture.classify_mixture import classify_mixture_all

SILVER = Path(__file__).resolve().parents[2] / "data" / "silver" / "claude" / "T21-025.json"


def row(op, value, **kw):
    return {"route": "경구", "op": op, "value": value, "unit": "mg/kg", **kw}


def comp(*msds, low=100, high=100, name="A"):
    return {"cas": name, "name": name, "content": {"low": low, "high": high}, "non_toxic": False,
            "db": [], "classes": [], "msds": list(msds), "mw": None, "density": None}


def oral(c, intervals=True):
    return classify_acute([c], "액체", intervals=intervals)[0]


def res(r):
    return (r["result"]["low"], r["result"]["high"], r["result"]["status"])


def test_초과는_하한만_있는_구간_구분이_갈리면_경계():
    r = oral(comp(row(">", 300)))
    assert res(r) == ("분류안됨", "4", "경계")  # 300 초과 → 구분4 부터 (고시 밖)까지
    assert r["inputs"][0]["ate_range"]["hi"] is None and r["inputs"][0]["ate_range"]["lo"] > 300
    assert any("구간" in a for a in r["assumptions"])


def test_초과가_구분_밖에_있으면_확정():
    assert res(oral(comp(row(">", 2000)))) == ("분류안됨", "분류안됨", "확정")


def test_미만은_0부터_상한까지_구분이_갈리면_경계():
    r = oral(comp(row("<", 50)))
    assert res(r) == ("2", "1", "경계")  # 0 < ATE < 50 → 구분1~2
    assert r["inputs"][0]["ate_range"]["lo"] is None


def test_범위가_한_구분_안이면_확정():
    assert res(oral(comp(row(">=", 500, op_hi="<=", value_hi=1000)))) == ("4", "4", "확정")


def test_범위가_구분_경계를_걸치면_경계():
    r = oral(comp(row(">=", 200, op_hi="<=", value_hi=1000)))
    assert res(r) == ("4", "3", "경계")
    assert r["calc"]["ate_mix_low"] == pytest.approx(1000) and r["calc"]["ate_mix_high"] == pytest.approx(200)


def test_점값은_옵션과_상관없이_같다():
    c = comp(row("=", 2140), low=93, high=98)
    assert oral(c, True) == oral(c, False)
    assert oral(comp(row("<=", 100)), True) == oral(comp(row("<=", 100)), False)


def test_값_없으면_근거부족():
    assert oral(comp(), True)["result"]["status"] == "근거부족" == oral(comp(), False)["result"]["status"]


def test_함량_없으면_구간도_근거부족():
    r = oral(comp(row(">", 300), low=None, high=None))
    assert r["result"]["status"] == "근거부족"


def test_기본값은_기존_규칙_부등호는_제외_범위는_최소값():
    assert get_ate(comp(row(">", 300)), "oral")["kind"] == "inequality"
    assert res(oral(comp(row(">", 300)), False)) == ("분류안됨", "분류안됨", "확정")
    assert get_ate(comp(row(">=", 500, op_hi="<=", value_hi=1000)), "oral")["value"] == 500


def test_단위_환산_못하면_구간_대신_기존_부등호():
    a = get_ate(comp(row(">", 300, unit="ppm")), "oral", intervals=True)
    assert a["kind"] == "inequality"


def test_어댑터는_범위의_상한을_보존():
    from types import SimpleNamespace as N
    q = {"value": None, "lower_op": ">=", "lower": 500, "upper_op": "<=", "upper": 1000, "unit": "mg/kg"}
    shim = N(components=[N(seq=1, name="A", cas_no="1-1-1", content=N(value=None, lower=None, upper=None))],
             toxicity=[{"comp_ref": "1", "endpoint": "TX_ORAL", "q": q}])
    t = to_acute_components(shim)[0]["tox"][0]
    assert (t["op"], t["value"], t["op_hi"], t["value_hi"]) == (">=", 500, "<=", 1000)
    q2 = {"value": None, "lower_op": ">", "lower": 2000, "upper_op": None, "upper": None, "unit": "mg/kg"}
    shim.toxicity = [{"comp_ref": "1", "endpoint": "TX_ORAL", "q": q2}]
    assert "op_hi" not in to_acute_components(shim)[0]["tox"][0]


@pytest.mark.skipif(not SILVER.exists(), reason="T21-025.json 없음")
def test_25번_황산_결과는_같다():
    built = build_components(json.loads(SILVER.read_text(encoding="utf-8"))["msds"][0], lambda cas: [])
    kw = dict(state="액체")
    base = classify_mixture_all(built["components"], built["mixture_props"], **kw)
    ivl = classify_mixture_all(built["components"], built["mixture_props"], ate_intervals=True, **kw)
    assert base == classify_mixture_all(built["components"], built["mixture_props"], ate_intervals=False, **kw)
    # 구분·상태는 같다 (물의 "> 90000 mg/kg" 이 구간으로 바뀌어도 구분이 안 바뀜). ATEmix 숫자만 미세하게 달라질 수 있다.
    assert [(r["class_code"], r.get("result")) for r in base] == [(r["class_code"], r.get("result")) for r in ivl]
