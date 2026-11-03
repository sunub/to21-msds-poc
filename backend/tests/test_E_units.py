"""단위·노출시간 환산 to_target 시험과 get_ate 연결."""
import pytest

from msds.compliance.mixture.ate_source import get_ate
from msds.compliance.mixture.units import to_target


def val(*a, **k):
    r = to_target(*a, **k)
    return r and r["value"]


@pytest.mark.parametrize("value, unit, route, form, kw, want", [
    (2, "g/kg", "oral", None, {}, 2000),
    (5000, "µg/kg", "oral", None, {}, 5),
    (5000, "μg/kg", "dermal", None, {}, 5),
    (375, "mg/m3", "inhal", "mist", {}, 0.375),
    (1.2, "g/m3", "inhal", "mist", {}, 1.2),
    (10, "mmol/kg", "oral", None, {"mw": 100}, 1000),
    (2, "mL/kg", "oral", None, {"density": 0.8}, 1600),
])
def test_단위_환산(value, unit, route, form, kw, want):
    assert val(value, unit, route, form, **kw) == pytest.approx(want)


def test_필요한_입력이_없으면_None():
    assert to_target(10, "mmol/kg", "oral") is None
    assert to_target(2, "mL/kg", "oral") is None


def test_ppm_증기는_참고():
    r = to_target(100, "ppm", "inhal", "vapour", mw=92.14)
    assert r["value"] == pytest.approx(100 * 92.14 / 24450) and r["value"] == pytest.approx(0.3768, rel=1e-3)
    assert "참고" in r["note"] and r["unit"] == "mg/L"


def test_ppm은_미스트에_못_씀_gas는_그대로():
    assert to_target(100, "ppm", "inhal", "mist", mw=92.14) is None
    for u in ("ppm", "ppmV"):
        r = to_target(1000, u, "inhal", "gas")
        assert (r["value"], r["unit"]) == (1000, "ppmV")


@pytest.mark.parametrize("value, form, unit, hours, want", [
    (10, "vapour", "mg/L", 1, 5), (1.0, "mist", "mg/L", 1, 0.25), (1000, "gas", "ppm", 1, 500),
    (10, "vapour", "mg/L", 4, 10), (10, "vapour", "mg/L", None, 10), (10, "vapour", "mg/L", 7, 10),
])
def test_노출시간(value, form, unit, hours, want):
    assert val(value, unit, "inhal", form, hours=hours) == pytest.approx(want)


def test_4시간_밖은_참고():
    assert "참고" in to_target(10, "mg/L", "inhal", "vapour", hours=7)["note"]
    assert to_target(10, "mg/L", "inhal", "vapour", hours=4)["note"] == ""


def test_별칭과_모르는_단위():
    assert to_target(1, "㎎/ℓ", "inhal", "vapour")["value"] == 1
    assert to_target(1, "MG/KG bw", "oral")["value"] == 1
    assert to_target(1, "foo", "oral") is None
    assert to_target(1, None, "oral") is None
    assert to_target(1, "mg/L", "inhal", "gas") is None  # 환산 규칙 없음


def comp(**kw):
    return {"name": "X", "cas": None, "non_toxic": False, "db": [], "classes": [], "msds": [], **kw}


def row(route="inhal", value=1.0, op="=", unit="mg/L", form="mist", **kw):
    return {"route": route, "form": form, "value": value, "unit": unit, "op": op, **kw}


def test_get_ate_msds_mg_m3_환산():
    r = get_ate(comp(msds=[row(value=375, unit="mg/m3")]), "inhal", "mist")
    assert (r["kind"], r["step"]) == ("value", 3)
    assert r["value"] == pytest.approx(0.375) and "U-03" in r["src"] and r["note"]


def test_get_ate_db_gas_1시간():
    r = get_ate(comp(db=[row(value=1000, unit="ppm", form="gas", hours=1)]), "inhal", "gas")
    assert (r["value"], r["step"]) == (500, 1)


def test_get_ate_mmol은_mw_있을_때만():
    c = {"route": "oral", "form": None, "value": 10, "unit": "mmol/kg", "op": "="}
    assert get_ate(comp(db=[c]), "oral")["kind"] == "unknown"
    r = get_ate(comp(db=[c], mw=100), "oral")
    assert (r["kind"], r["value"]) == ("value", 1000)
