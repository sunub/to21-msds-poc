"""성분별 ATE 선택 get_ate 시험."""
import pytest

from msds.compliance.mixture.acute import mix_acute
from msds.compliance.mixture.ate_source import get_ate, inhal_forms


def comp(**kw):
    return {"name": "X", "cas": None, "non_toxic": False, "db": [], "classes": [], "msds": [], **kw}


def row(route="oral", value=100, op="=", unit="mg/kg", form=None, **kw):
    return {"route": route, "form": form, "value": value, "unit": unit, "op": op, **kw}


def cls(category, source="환경부", code="HH_ACUTE_ORAL", route_form=None):
    return {"class_code": code, "category": category, "route_form": route_form, "source": source}


@pytest.mark.parametrize("state, forms", [("기체", ["gas"]), ("액체", ["vapour", "mist"]), ("고체", ["mist"]), ("플라즈마", [])])
def test_inhal_forms(state, forms):
    assert inhal_forms(state) == forms


def test_무독성_우선():
    r = get_ate(comp(non_toxic=True, db=[row(value=90000)]), "oral")
    assert (r["kind"], r["step"]) == ("non_toxic", 5)


def test_최저값():
    r = get_ate(comp(db=[row(value=100), row(value=50)]), "oral")
    assert (r["kind"], r["value"], r["step"]) == ("value", 50, 1)


def test_db_부등호만_있으면_분류_환산이_먼저():
    r = get_ate(comp(db=[row(value=2000, op=">")], classes=[cls("4")]), "oral")
    assert (r["kind"], r["value"], r["step"]) == ("conversion", 500, 2)


def test_출처_우선순위():
    r = get_ate(comp(classes=[cls("2", "고용노동부"), cls("3", "환경부")]), "oral")
    assert r["value"] == 100
    assert get_ate(comp(classes=[cls("2", "고용노동부")]), "oral")["value"] == 5


def test_구분5는_참고():
    r = get_ate(comp(classes=[cls("5")]), "oral")
    assert (r["kind"], r["value"], r["ref_cat5"]) == ("conversion", 2500, True)
    assert get_ate(comp(classes=[cls("4")]), "oral")["ref_cat5"] is False


def test_msds만_있는_경우():
    r = get_ate(comp(msds=[row("inhal", 0.375, unit="mg/L", form="mist")]), "inhal", "mist")
    assert (r["kind"], r["value"], r["step"]) == ("value", 0.375, 3)


def test_form_없는_msds_흡입값은_무시():
    assert get_ate(comp(msds=[row("inhal", 0.375, unit="mg/L")]), "inhal", "mist")["kind"] == "unknown"


def test_부등호():
    r = get_ate(comp(db=[row("dermal", 5000, ">")]), "dermal")
    assert (r["kind"], r["step"]) == ("inequality", 4)


def test_자료없음():
    r = get_ate(comp(), "oral")
    assert (r["kind"], r["step"]) == ("unknown", 6)


def test_물음표_op와_다른_단위는_무시():
    assert get_ate(comp(db=[row(op="?"), row(unit="mmol/kg")]), "oral")["kind"] == "unknown"


def test_흡입_형태_구분():
    c = comp(db=[row("inhal", 1.0, unit="mg/L", form="vapour")])
    assert get_ate(c, "inhal", "mist")["kind"] == "unknown"
    assert get_ate(c, "inhal", "vapour")["value"] == 1.0


def test_한글_표기도_받는다():
    c = comp(db=[row("흡입", 0.375, unit="mg/L", form="분진·미스트")])
    assert get_ate(c, "inhal", "mist")["value"] == 0.375


def _황산(route, form, db):
    s, w = comp(name="황산", db=db), comp(name="물", non_toxic=True)
    return mix_acute([{"name": "황산", "cas": None, "content": {"low": 93, "high": 98}, "ate": get_ate(s, route, form)},
                      {"name": "물", "cas": None, "content": {"low": 2, "high": 7}, "ate": get_ate(w, route, form)}],
                     route, form)


def test_연결_황산_경구():
    r = _황산("oral", None, [row(value=2140)])
    assert r["low"]["ate_mix"] == pytest.approx(2301.1, rel=1e-3)
    assert r["high"]["ate_mix"] == pytest.approx(2183.7, rel=1e-3)
    assert r["low"]["category"] == r["high"]["category"] == "분류안됨"
    assert r["status"] == "확정"


def test_연결_황산_흡입_미스트():
    r = _황산("inhal", "mist", [row("inhal", 0.375, unit="mg/L", form="mist")])
    assert r["low"]["ate_mix"] == pytest.approx(0.403, rel=1e-3)
    assert r["high"]["ate_mix"] == pytest.approx(0.383, rel=1e-3)
    assert r["low"]["category"] == r["high"]["category"] == "2"
    assert r["status"] == "확정"
