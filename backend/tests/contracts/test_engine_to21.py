"""TO21이 준 수락 시험(Msds-test v0.4 test_to21_v6.py)의 P02~P05 기대값을 우리 엔진으로 확인한다.

TO21 패키지와 다른 점은 시험마다 이유를 적었다. 입력값은 그 패키지의 products.csv·product_components.csv 다.
"""
import pytest

from msds.compliance.consistency import run_consistency
from msds.compliance.htodb.csv_repo import CsvRepo
from msds.compliance.judge import judge
from msds.compliance.mixture.build_components import build_components
from msds.compliance.mixture.class_lookup_db import make_db_class_lookup, make_db_info_lookup, make_db_tox_lookup
from msds.compliance.mixture.classify_mixture import classify_mixture_all
from msds.compliance.mixture.physical import physical_inputs


def _q(value, unit=None):
    return {"raw": str(value), "approx": None, "value": value, "lower_op": None, "lower": None, "upper_op": None, "upper": None,
            "unit": unit, "dp": 0, "status": "값있음", "note": None}


def _prop(code, value, unit=None, text=None, cond=None):
    return {"prop_code": code, "comp_ref": "MIX", "q": None if text else _q(value, unit), "text_value": text, "cond": cond, "seq": None,
            "data_source": None}


class VirtualRepo(CsvRepo):
    """TO21 시험 패키지의 가상 물질 (data/virtual). 지식DB에 없는 시험 전용 값이다."""
    VIRTUAL = {"TEST-X": ("VIRTUAL-X", ["GHS030101", "GHS030201"], [("GHS0311", "LC50 0.05 ㎎/ℓ 96 hr Oncorhynchus mykiss"),
                                                                     ("GHS0328", "어류 만성독성시험 NOEC=0.005 mg/L"),
                                                                     ("GHS0331", "15 % 28 day (난분해성)")])}

    def chemicals(self, *, cas, limit=50):
        if cas in self.VIRTUAL:
            return {"rows": [{"chem_id": self.VIRTUAL[cas][0], "cas_no": cas, "molecular_weight": None}], "total": 1}
        return super().chemicals(cas=cas, limit=limit)

    def _virtual(self, chem_id):
        return next((v for v in self.VIRTUAL.values() if v[0] == chem_id), None)

    def classifications(self, chem_id):
        v = self._virtual(chem_id)
        if not v:
            return super().classifications(chem_id)
        return {"rows": [{"class_source_db_code": "KR02", "class_result_code": code, "chem_id": chem_id, "hcode_seq": "H"} for code in v[1]]}

    def toxicity(self, chem_id):
        v = self._virtual(chem_id)
        if not v:
            return super().toxicity(chem_id)
        return {"rows": [{"chem_id": chem_id, "experiment_div_code": "GHS03", "div_code": d, "toxicity_seq": 1, "lang_code": "ko", "toxicity_source_db": "KR03",
                          "primary_value_text": t, "primary_value": None, "note": None} for d, t in v[2]]}


@pytest.fixture(scope="module")
def repo():
    r = VirtualRepo()
    if not r.available():
        pytest.skip("TO21 샘플 CSV 없음")
    return r


def _run(repo, comps, props=(), transport=()):
    item = {"components": [{"seq": i + 1, "cas_no": c, "name": c, "content": _q(v, "%"), "content_note": None, "trade_secret": False}
                           for i, (c, v) in enumerate(comps)],
            "physchem": [_prop("APPEARANCE_STATE", None, text="액체"), *props], "transport": list(transport), "toxicity": [], "ecotox": [],
            "hazard": {"classes": []}}
    b = build_components(item, make_db_class_lookup(repo), make_db_tox_lookup(repo), make_db_info_lookup(repo))
    res = classify_mixture_all(b["components"], b["mixture_props"], state=b["mixture_props"].get("STATE"), physical=physical_inputs(item))
    return {(r["class_code"], r.get("form")): r for r in res}


def _cat(r):
    assert r["result"]["low"] == r["result"]["high"], r["result"]
    return r["result"]["low"]


THINNER = [("108-88-3", 50), ("1330-20-7", 30), ("111-76-2", 20)]
THINNER_PROPS = (_prop("FLASH_POINT", 5, "℃"), _prop("BOILING", 110, "℃"), _prop("VISCOSITY_KIN", 0.7, "mm²/s", cond={"temp": 40}))
UN1263 = ({"mode": "공통", "regulated": True, "un_no": "1263", "hazard_class": "3", "packing_group": "II"},)


def test_P02_액체_제품의_흡입_증기_구분4(repo):
    # 2-부톡시에탄올의 환경부 '흡입:가스 구분3'은 다른 출처에 증기가 있어 증기로 재지정한다 (D-22). 재지정이 빠지면 고용노동부 구분4를 써서 분류안됨이 된다
    r = _run(repo, THINNER, THINNER_PROPS, UN1263)
    vapour = r[("HH_ACUTE_INHAL", "증기")]
    assert _cat(vapour) == "4" and vapour["calc"]["ate_mix_low"] == pytest.approx(12.76, abs=0.01)
    assert ("HH_ACUTE_INHAL", "가스") not in r  # 액체 제품은 가스 형태를 계산하지 않는다


def test_P02_경구는_구분5를_고시_밖으로_두어_분류안됨이다(repo):
    # TO21 패키지 기대값은 '5'다. 설계서 22장 표와 고시에 구분5가 없어 분류안됨 + 참고 표시(ref_cat5)로 낸다
    oral = _run(repo, THINNER, THINNER_PROPS, UN1263)[("HH_ACUTE_ORAL", None)]
    assert _cat(oral) == "분류안됨" and oral["calc"]["ate_mix_low"] == pytest.approx(3162.52, abs=0.01) and oral["calc"]["ref_cat5"]["low"]


def test_P02_표적장기_1회_구분3_효과별(repo):
    extra = _run(repo, THINNER, THINNER_PROPS, UN1263)[("HH_STOT_SE", None)]["extra"]["low"]
    assert {(e["category"], e["effect"]) for e in extra} == {("3", "마취"), ("3", "호흡기자극")}


def test_P02_흡인_유해성_구분1(repo):
    assert _cat(_run(repo, THINNER, THINNER_PROPS, UN1263)[("HH_ASPIRATION", None)]) == "1"


def test_P03_한계농도_벤젠(repo):
    r = _run(repo, [("108-88-3", 70), ("1330-20-7", 29.85), ("71-43-2", 0.15)], (_prop("FLASH_POINT", 4, "℃"), _prop("BOILING", 80, "℃")))
    assert _cat(r[("HH_CARCINOGEN", None)]) == "1A"  # 벤젠 0.15% >= 0.1%
    assert _cat(r[("HH_STOT_RE", None)]) == "2"  # 벤젠(구분1) 0.15% < 1% 라 제외
    assert _cat(r[("ENV_AQ_CHRONIC", None)]) == "분류안됨"


def test_P05_수생_M계수(repo):
    r = _run(repo, [("TEST-X", 2), ("7732-18-5", 98)])
    assert _cat(r[("ENV_AQ_ACUTE", None)]) == "분류안됨"  # 2% x M10 = 20 < 25
    assert _cat(r[("ENV_AQ_CHRONIC", None)]) == "2"  # 10 x 20 = 200 >= 25


def _toluene_with_benzene(content, cat="1A"):
    benzene = {"seq": 2, "cas_no": "71-43-2", "name": "벤젠", "content": content, "content_note": "불순물", "trade_secret": False}
    return {"msds": [{"composition": {"type": "단일물질"}, "hazard": {"classes": [{"class_code": "HH_CARCINOGEN", "category": cat}]},
                      "components": [{"seq": 1, "cas_no": "108-88-3", "name": "톨루엔", "content": _q(99.5, "%"), "trade_secret": False}, benzene],
                      "physchem": [_prop("APPEARANCE_STATE", None, text="액체")]}]}


def _carcinogen(repo, doc):
    c = run_consistency(doc, repo)["consistency"]
    assert c["product_type"]["value"] == "단일물질"
    return next(f for f in c["findings"] if f["class_code"] == "HH_CARCINOGEN")


def test_불순물이_한계농도_미만이면_적용하지_않는다(repo):  # 설계서 17장 톨루엔 99.5% + 벤젠 0.05%
    assert _carcinogen(repo, _toluene_with_benzene(_q(0.05, "%")))["our_value"]["low"] != "1A"


def test_불순물이_한계농도_이상이면_그_항목만_혼합물_규칙이다(repo):
    f = _carcinogen(repo, _toluene_with_benzene(_q(0.2, "%")))
    assert (f["verdict"], f["our_value"]["low"]) == ("일치", "1A") and "불순물 벤젠" in f["reason"]


def test_불순물_함량이_기준을_걸치면_경계다(repo):
    rng = {**_q(None, "%"), "raw": "0.05~0.2", "lower": 0.05, "lower_op": ">=", "upper": 0.2, "upper_op": "<="}
    assert _carcinogen(repo, _toluene_with_benzene(rng))["verdict"] == "경계"


def test_불순물_함량이_없으면_근거부족이다(repo):
    f = _carcinogen(repo, _toluene_with_benzene({"raw": None, "status": "자료없음"}))
    assert f["verdict"] == "근거부족" and "불순물 함량" in f["reason"]


def _tox(endpoint, value, unit, **kw):
    return {"comp_ref": "1", "endpoint": endpoint, "descriptor": kw.pop("descriptor", "LD50"), "q": _q(value, unit), "physical_form": None, "duration_value": None, "duration_unit": None, **kw}


def _single(classes, toxicity=(), ecotox=()):
    return {"doc": {"doc_id": "X-1"}, "msds": [{"composition": {"type": "단일물질"}, "hazard": {"classes": classes}, "toxicity": list(toxicity), "ecotox": list(ecotox),
                                                 "components": [{"seq": 1, "cas_no": "108-88-3", "name": "톨루엔", "content": _q(99.5, "%"), "trade_secret": False}],
                                                 "physchem": [_prop("APPEARANCE_STATE", None, text="액체")]}]}


def _cross(repo, doc, contract_errors):
    out = judge(doc, "2026-11-03", repo)
    assert contract_errors("3-consistency.schema.json", out) == []
    return {f["id"]: f for f in out["results"][0]["findings"] if ":CROSS:" in f["id"]}


def test_11항_값과_2항_구분이_다르면_내부_불일치_경고다(repo, contract_errors):  # 설계서 19장 예: LD50 2,140 인데 구분4
    doc = _single([{"class_code": "HH_ACUTE_ORAL", "category": "4"}], [_tox("TX_ORAL", 2140, "mg/kg")])
    f = _cross(repo, doc, contract_errors)["m0/F2:CROSS:HH_ACUTE_ORAL:-"]
    assert (f["verdict"], f["type"], f["expected"]["low"], f["msds"]["category"]) == ("경고", "내부 불일치", "분류안됨", "4")
    assert f["needs_explanation"] is False


def test_11항_값과_2항_구분이_같으면_경고가_없다(repo, contract_errors):
    assert _cross(repo, _single([{"class_code": "HH_ACUTE_ORAL", "category": "4"}], [_tox("TX_ORAL", 1500, "mg/kg")]), contract_errors) == {}


def test_여러_값이면_가장_낮은_값으로_본다(repo, contract_errors):  # D-04
    doc = _single([{"class_code": "HH_ACUTE_ORAL", "category": "4"}], [_tox("TX_ORAL", 3000, "mg/kg"), _tox("TX_ORAL", 1500, "mg/kg")])
    assert _cross(repo, doc, contract_errors) == {}


def test_부등호_값으로는_교차_확인하지_않는다(repo, contract_errors):
    row = {"comp_ref": "1", "endpoint": "TX_ORAL", "descriptor": "LD50", "q": {**_q(None, "mg/kg"), "lower": 2000, "lower_op": ">"}, "physical_form": None}
    assert _cross(repo, _single([{"class_code": "HH_ACUTE_ORAL", "category": "4"}], [row]), contract_errors) == {}


def test_12항_값이_구분1_기준과_맞지_않으면_경고다(repo, contract_errors):
    fish = _tox("ECO_FISH", 0.5, "mg/L", descriptor="LC50")
    assert "m0/F2:CROSS:ENV_AQ_ACUTE:-" in _cross(repo, _single([{"class_code": "ENV_AQ_ACUTE", "category": "3"}], ecotox=[fish]), contract_errors)
    assert _cross(repo, _single([{"class_code": "ENV_AQ_ACUTE", "category": "1"}], ecotox=[fish]), contract_errors) == {}
