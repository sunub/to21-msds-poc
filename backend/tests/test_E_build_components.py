"""build_components 시험: 가상 msds_item + 25번 황산 실데이터(있으면)."""
import json
from pathlib import Path

import pytest

from msds.compliance.mixture.build_components import build_components
from msds.compliance.mixture.classify_mixture import classify_mixture_all
from msds.compliance.mixture.rules_loader import load_class_map

ROOT = Path(__file__).resolve().parents[2]
SILVER = ROOT / "data" / "silver" / "claude" / "T21-025.json"
MAP = load_class_map()["rows"]


def code(class_code, category, effect="", form=""):
    return next(r["to21_result_code"] for r in MAP
                if (r["class_code"], r["category"], r["effect"], r["form"]) == (class_code, category, effect, form))


def q(raw=None, value=None, lower=None, upper=None, lower_op=None, upper_op=None, unit=None, status="값있음"):
    return {"raw": raw, "value": value, "lower": lower, "lower_op": lower_op, "upper": upper, "upper_op": upper_op,
            "unit": unit, "status": status}


def comp(seq, name, cas, content=None, **kw):
    return {"seq": seq, "name": name, "cas_no": cas, "content": content, "content_note": None, "trade_secret": False, **kw}


def phys(code_, qv=None, text=None, cond=None, ref="MIX"):
    return {"prop_code": code_, "comp_ref": ref, "q": qv, "text_value": text, "cond": cond}


def item(components, physchem=(), toxicity=()):
    return {"components": components, "physchem": list(physchem), "toxicity": list(toxicity)}


def lookup_none(cas):
    return []


RANGE = q("93~98", lower=93, upper=98, lower_op=">=", upper_op="<=", unit="%")


def gap_fields(r):
    return [g["field"] for g in r["gaps"]]


def test_함량_범위():
    r = build_components(item([comp(1, "A", "1-1-1", RANGE)]), lookup_none)
    c = r["components"][0]
    assert (c["low"], c["high"]) == (93, 98)


def test_함량_단일값():
    r = build_components(item([comp(1, "A", "1-1-1", q("50", value=50, unit="%"))]), lookup_none)
    assert (r["components"][0]["low"], r["components"][0]["high"]) == (50, 50)


def test_함량_없음은_None이고_gap():
    r = build_components(item([comp(1, "A", "1-1-1", None)]), lookup_none)
    c = r["components"][0]
    assert c["low"] is None and c["high"] is None
    assert "components[A].content" in gap_fields(r)


def test_CAS_없으면_조회_안하고_빈_class_rows():
    called = []
    r = build_components(item([comp(1, "A", None, RANGE)]), lambda cas: called.append(cas) or [{"result_code": "X", "source": "KR02"}])
    assert r["components"][0]["class_rows"] == [] and called == []
    assert any("CAS 없음" in g["reason"] for g in r["gaps"])


def test_조회_결과_없으면_gap():
    r = build_components(item([comp(1, "A", "1-1-1", RANGE)]), lookup_none)
    assert any("조회 결과 없음" in g["reason"] for g in r["gaps"])


def test_class_rows_는_조회_결과_그대로():
    rows = [{"result_code": code("HH_SKIN_CORR", "1"), "source": "KR03"}]
    r = build_components(item([comp(1, "A", "1-1-1", RANGE)]), lambda cas: rows)
    assert r["components"][0]["class_rows"] == rows


def test_pH_제품값_있음과_없음():
    with_ph = item([comp(1, "A", "1-1-1", RANGE)], [phys("PH", q("2.0", value=2.0))])
    assert build_components(with_ph, lookup_none)["mixture_props"]["PH"] == 2.0
    r = build_components(item([comp(1, "A", "1-1-1", RANGE)]), lookup_none)
    assert "PH" not in r["mixture_props"] and "mixture_props.PH" in gap_fields(r)


def test_pH_농도조건_붙은_값은_제품_pH가_아니다():
    ph = phys("PH", q("1.2(0.1N)", value=1.2), cond={"conc_value": 0.1, "conc_unit": "N"})
    r = build_components(item([comp(1, "A", "1-1-1", RANGE)], [ph]), lookup_none)
    assert "PH" not in r["mixture_props"] and "mixture_props.PH" in gap_fields(r)


def test_점도_동점도만_담고_mPas는_gap():
    base = [comp(1, "A", "1-1-1", RANGE)]
    cond40 = {"temp": 40, "temp_unit": "C"}
    kin = build_components(item(base, [phys("VISCOSITY_KIN", q("12 mm2/s", value=12, unit="mm2/s"), cond=cond40)]), lookup_none)
    assert kin["mixture_props"]["VISCOSITY_40"] == 12
    dyn = build_components(item(base, [phys("VISCOSITY", q("21 cP", value=21, unit="cP"), cond={"temp": 25, "temp_unit": "C"})]),
                           lookup_none)
    assert "VISCOSITY_40" not in dyn["mixture_props"] and "mixture_props.VISCOSITY_40" in gap_fields(dyn)
    mpas = build_components(item(base, [phys("VISCOSITY", q("5 mPa·s", value=5, unit="mPa·s"), cond=cond40)]), lookup_none)
    assert "VISCOSITY_40" not in mpas["mixture_props"]


def test_동점도_40도_아니면_담지_않는다():
    row = phys("VISCOSITY_KIN", q("12", value=12, unit="mm2/s"), cond={"temp": 20, "temp_unit": "C"})
    r = build_components(item([comp(1, "A", "1-1-1", RANGE)], [row]), lookup_none)
    assert "VISCOSITY_40" not in r["mixture_props"]


def test_성상_LEL_UEL():
    rows = [phys("APPEARANCE_STATE", text="기체"), phys("LEL", q("1.5", value=1.5, unit="%")),
            phys("UEL", q("해당없음", status="해당없음"))]
    r = build_components(item([comp(1, "A", "1-1-1", RANGE)], rows), lookup_none)
    assert r["mixture_props"] == {"STATE": "가스", "LEL": 1.5}


def test_값이_None인_prop은_키가_없다():
    r = build_components(item([comp(1, "A", "1-1-1", RANGE)]), lookup_none)
    assert r["mixture_props"] == {}


def test_독성_성분_행만_msds로_op_보존():
    tox = [{"comp_ref": "1", "endpoint": "TX_ORAL", "q": q("2140", value=2140, unit="mg/kg")},
           {"comp_ref": "1", "endpoint": "TX_DERMAL", "q": q("> 2000", lower=2000, lower_op=">", unit="mg/kg")},
           {"comp_ref": "MIX", "endpoint": "TX_ORAL", "q": q("x", value=1, unit="mg/kg")}]
    r = build_components(item([comp(1, "A", "1-1-1", RANGE)], toxicity=tox), lookup_none)
    assert [(t["route"], t["op"], t["value"]) for t in r["components"][0]["msds"]] == [("경구", "=", 2140), ("경피", ">", 2000)]


def test_독성_부등호_없으면_gap():
    tox = [{"comp_ref": "1", "endpoint": "TX_ORAL", "q": q("2000 초과", lower=2000, unit="mg/kg")}]
    r = build_components(item([comp(1, "A", "1-1-1", RANGE)], toxicity=tox), lookup_none)
    assert r["components"][0]["msds"] == []
    assert any("부등호" in g["reason"] for g in r["gaps"])


def test_분자량_밀도_성분번호_일치만():
    rows = [phys("MOL_WEIGHT", q("98", value=98), ref="1"), phys("RELATIVE_DENSITY", q("1.8", value=1.8), ref="1")]
    r = build_components(item([comp(1, "A", "1-1-1", RANGE), comp(2, "B", "2-2-2", RANGE)], rows), lookup_none)
    a, b = r["components"]
    assert (a["mw"], a["density"]) == (98, 1.8) and (b["mw"], b["density"]) == (None, None)
    assert "components[B].mw" in gap_fields(r) and "components[A].mw" not in gap_fields(r)


def test_MIX_분자량은_성분이_여럿이면_쓰지_않고_하나면_쓴다():
    rows = [phys("MOL_WEIGHT", q("98", value=98))]
    two = build_components(item([comp(1, "A", "1-1-1", RANGE), comp(2, "B", "2-2-2", RANGE)], rows), lookup_none)
    assert two["components"][0]["mw"] is None
    one = build_components(item([comp(1, "A", "1-1-1", RANGE)], rows), lookup_none)
    assert one["components"][0]["mw"] == 98


def test_flags_근거없음_gap():
    r = build_components(item([comp(1, "A", "1-1-1", RANGE)]), lookup_none)
    assert r["components"][0]["flags"] == []
    assert any(g["field"] == "components[*].flags" and "근거 없음" in g["reason"] for g in r["gaps"])


def test_반환_모양():
    r = build_components(item([comp(1, "A", "1-1-1", RANGE)]), lookup_none)
    assert set(r) == {"components", "mixture_props", "gaps", "assumptions"}
    assert all(set(g) == {"field", "reason"} for g in r["gaps"]) and r["assumptions"]


# ── 25번 황산 실데이터 ──
def sulfuric_lookup(cas):
    if cas == "7664-93-9":
        return [{"result_code": code("HH_SKIN_CORR", "1"), "source": "KR03"},
                {"result_code": code("HH_EYE_DMG", "1"), "source": "KR03"},
                {"result_code": code("HH_ACUTE_INHAL", "2", form="mist"), "source": "KR03"}]
    return []


@pytest.fixture(scope="module")
def built25():
    if not SILVER.exists():
        pytest.skip("T21-025.json 없음")
    return build_components(json.loads(SILVER.read_text(encoding="utf-8"))["msds"][0], sulfuric_lookup)


def test_25번_성분과_물성(built25):
    sul, water = built25["components"]
    assert (sul["cas"], sul["low"], sul["high"]) == ("7664-93-9", 93, 98)
    assert (water["low"], water["high"], water["class_rows"]) == (2, 7, [])
    assert [(t["route"], t["op"], t["value"]) for t in sul["msds"] if t["route"] != "흡입"] == [("경구", "=", 2140)]
    assert built25["mixture_props"] == {"STATE": "액체"}  # pH는 희석액뿐, 점도는 cP, LEL/UEL은 해당없음


def test_25번_classify_mixture_all_실행(built25):
    out = classify_mixture_all(built25["components"], built25["mixture_props"], state="액체")
    by = {r["class_code"]: r for r in out if "result" in r}
    assert by["HH_SKIN_CORR"]["result"]["high"] == "1" and by["HH_EYE_DMG"]["result"]["high"] == "1"
    assert "HH_ACUTE_INHAL" in by
