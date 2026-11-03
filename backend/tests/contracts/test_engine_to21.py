"""TO21이 준 수락 시험(Msds-test v0.4 test_to21_v6.py)의 P02~P05 기대값을 우리 엔진으로 확인한다.

입력값은 그 패키지의 products.csv·product_components.csv 다. 패키지와 다른 결과와 이유는 docs/backend/b/decisions.md 에 있다.
"""
import json
from pathlib import Path

import pytest

from msds.compliance.consistency import run_consistency
from msds.compliance.htodb.csv_repo import CsvRepo
from msds.compliance.judge import judge
from msds.compliance.mixture.build_components import build_components
from msds.compliance.mixture.class_lookup_db import make_db_class_lookup, make_db_info_lookup, make_db_tox_lookup
from msds.compliance.mixture.classify_mixture import classify_item, classify_mixture_all
from msds.compliance.mixture.physical import physical_inputs
from msds.compliance.sec15_judge import _dg


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


def _dg_inputs(row, flash=47, kind="혼합물"):
    prop = {"FLASH_POINT": [{"comp_ref": "MIX", "q": _q(flash, "℃")}], "APPEARANCE_STATE": [{"comp_ref": "MIX", "text_value": "액체", "q": None}]} if flash is not None else {"APPEARANCE_STATE": [{"comp_ref": "MIX", "text_value": "액체", "q": None}]}
    return {"physchem": prop, "dangerous_goods": [{"comp_ref": "MIX", "class": "제4류", **row}], "composition": {"type": kind}, "as_of_date": "2026-11-03"}


def _dg_know(group, db_class="제4류"):
    return [{"rows": [{"kind": "dg", "regulate_item_id": "KR004001004", "db_item_name": db_class, "group_name": group}], "knowledge_version": "v"}]


def test_위험물_품명이_다르면_기준_불일치다():  # 설계서 29장 5단계
    v = _dg(_dg_inputs({"item": "제1석유류"}), {}, _dg_know("제2석유류 비수용성액체"))
    assert (v["verdict"], v["type"]) == ("불일치", "기준 불일치") and "품명" in v["reason"]


def test_위험물_품명_수용성_지정수량이_맞으면_일치다():
    row = {"item": "제2석유류", "water_soluble": "비수용성", "designated_qty": _q(1000, "L")}
    assert _dg(_dg_inputs(row), {}, _dg_know("제2석유류 비수용성액체"))["verdict"] == "일치"


def test_위험물_수용성이_DB와_다르면_기준_불일치다():
    v = _dg(_dg_inputs({"item": "제2석유류", "water_soluble": "수용성"}, kind="단일물질"), {}, _dg_know("제2석유류 비수용성액체"))
    assert v["verdict"] == "불일치" and "수용성" in v["reason"]


def test_위험물_지정수량이_시행령과_다르면_기준_불일치다():
    v = _dg(_dg_inputs({"item": "제2석유류", "water_soluble": "비수용성", "designated_qty": _q(2000, "L")}), {}, _dg_know("제2석유류 비수용성액체"))
    assert v["verdict"] == "불일치" and "지정수량" in v["reason"]


def test_인화점이_없으면_DB_품명으로_비교한다():  # 설계서 29장 6단계
    v = _dg(_dg_inputs({"item": "제1석유류"}, flash=None, kind="단일물질"), {}, _dg_know("제2석유류 비수용성액체"))
    assert v["verdict"] == "불일치" and v["db_threshold"] == "제2석유류"


def test_단일물질의_9항_품명과_DB_품명이_다르면_경고다():  # 설계서 29장 4단계
    v = _dg(_dg_inputs({"item": "제2석유류"}, kind="단일물질"), {}, _dg_know("제3석유류 비수용성액체"))
    assert v["verdict"] == "경고" and "지식DB 품명" in v["reason"]


def test_혼합물은_성분_DB_품명이_제품과_달라도_경고가_아니다():
    assert _dg(_dg_inputs({"item": "제2석유류"}), {}, _dg_know("제3석유류 비수용성액체"))["verdict"] == "일치"


@pytest.mark.parametrize("item,flash,group", [("알코올류", 13, "알코올류"), ("동식물유류", 240, "동식물유류"), ("특수인화물", -30, "특수인화물")])
def test_9항만으로_못_정하는_품명은_DB_품명으로만_비교한다(item, flash, group):
    assert _dg(_dg_inputs({"item": item}, flash=flash, kind="단일물질"), {}, _dg_know(group))["verdict"] == "일치"


def test_위험물_류가_다르면_기준_불일치다():
    v = _dg(_dg_inputs({"item": "제2석유류", "class": "제3류"}, kind="단일물질"), {}, _dg_know("제2석유류 비수용성액체"))
    assert v["verdict"] == "불일치" and "류:" in v["reason"]


def test_지정수량_단위가_리터가_아니면_비교하지_않는다():
    row = {"item": "제2석유류", "water_soluble": "비수용성", "designated_qty": _q(200, "kg")}
    assert _dg(_dg_inputs(row), {}, _dg_know("제2석유류 비수용성액체"))["verdict"] == "일치"


def test_기체_물질의_흡입_가스는_재지정하지_않는다(repo):  # 설계서 D-22 "액체·고체 물질이면"
    from msds.compliance.mixture.classify_mixture import _real_inhal_form
    rows = [{"result_code": "GHS020303", "source": "KR02"}, {"result_code": "GHS020403", "source": "KR03"}]
    assert _real_inhal_form({"state": "기체", "class_rows": rows, "db": []}) is None
    assert _real_inhal_form({"state": None, "class_rows": rows, "db": []}) is None
    assert _real_inhal_form({"state": "액체", "class_rows": [rows[0]], "db": []}) == "vapour"  # 근거가 없으면 성상 기본값
    assert _real_inhal_form({"state": "고체", "class_rows": [rows[0]], "db": []}) == "mist"


def test_코드_없이_문구만_있으면_없는_것이_아니라_근거부족이다(repo):  # T21-S001
    doc = _single([{"class_code": "PH_PRESS_GAS", "category": "압축가스"}])
    doc["msds"][0]["hazard"]["h_statements"] = [{"seq": 1, "code": None, "text": "고압가스 포함"}]
    c = run_consistency(doc, repo)["consistency"]
    h = [f for f in c["findings"] if f.get("class_code") == "LABEL_H_CODES"]
    assert h and all(f["verdict"] == "근거부족" and "문구만" in f["reason"] for f in h)


def test_불순물_ppm과_이하_표기를_읽는다(repo):
    assert _carcinogen(repo, _toluene_with_benzene(_q(2000, "ppm")))["our_value"]["low"] == "1A"  # 0.2%
    upper = {**_q(None, "%"), "raw": "<= 0.05", "upper": 0.05, "upper_op": "<="}
    assert "불순물 함량" not in _carcinogen(repo, _toluene_with_benzene(upper))["reason"]  # 함량을 읽어 0.1% 미만으로 판단


def test_불순물_미만_표기가_기준이면_닿지_않는다(repo):
    below = {**_q(None, "%"), "raw": "< 0.1", "upper": 0.1, "upper_op": "<"}
    assert _carcinogen(repo, _toluene_with_benzene(below))["verdict"] != "경계"


def test_불순물_CAS가_없으면_참고로_남는다(repo):
    doc = _toluene_with_benzene(_q(0.2, "%"))
    doc["msds"][0]["components"][1]["cas_no"] = None
    excluded = run_consistency(doc, repo)["consistency"]["excluded"]
    assert any("불순물 벤젠" in (e.get("reason") or "") for e in excluded)


def test_불순물은_제품_위험물_품명을_정하지_않는다(repo):
    doc = _toluene_with_benzene(_q(0.01, "%"))
    doc["msds"][0]["components"][0]["cas_no"] = "7732-18-5"  # 물
    c = run_consistency(doc, repo)["consistency"]
    dg = next(f for f in c["findings"] if f.get("item_code") == "DG_HAZMAT")
    assert dg["type"] != "규제 누락"


def test_교차_확인은_LD50_LC50만_쓴다(repo, contract_errors):
    doc = _single([{"class_code": "HH_ACUTE_ORAL", "category": "4"}], [_tox("TX_ORAL", 3000, "mg/kg", descriptor="TDLo")])
    assert _cross(repo, doc, contract_errors) == {}


def test_교차_확인은_구분5와_분류안됨을_다르게_보지_않는다(repo, contract_errors):
    assert _cross(repo, _single([{"class_code": "HH_ACUTE_ORAL", "category": "5"}], [_tox("TX_ORAL", 3000, "mg/kg")]), contract_errors) == {}


def test_교차_확인은_30분_값을_4시간_값으로_쓰지_않는다(repo, contract_errors):
    row = _tox("TX_INHAL", 8.3, "mg/L", descriptor="LC50", physical_form="분진·미스트", duration_value=30, duration_unit="min")
    assert _cross(repo, _single([{"class_code": "HH_ACUTE_INHAL", "category": "4", "route_form": "분진·미스트"}], [row]), contract_errors) == {}


def test_12항_마이크로그램_단위를_환산한다(repo, contract_errors):
    fish = _tox("ECO_FISH", 500, "µg/L", descriptor="LC50")
    assert "m0/F2:CROSS:ENV_AQ_ACUTE:-" in _cross(repo, _single([{"class_code": "ENV_AQ_ACUTE", "category": "3"}], ecotox=[fish]), contract_errors)


def test_제4류가_아닌_위험물은_인화점_품명과_비교하지_않는다():  # MEKP 인화점 50, 제5류
    row = {"item": "유기과산화물", "class": "제5류"}
    assert _dg(_dg_inputs(row, flash=50, kind="단일물질"), {}, _dg_know("유기과산화물(2종)", "제5류"))["verdict"] == "일치"
    assert _dg(_dg_inputs(row, flash=50), {}, _dg_know("유기과산화물(2종)", "제5류"))["verdict"] == "일치"


def test_성분_위험물_행은_제품_품명과_비교하지_않는다():
    inputs = _dg_inputs({"item": "제1석유류"}, flash=35)
    inputs["dangerous_goods"][0]["comp_ref"] = "1"
    assert _dg(inputs, {}, _dg_know("제1석유류 비수용성액체"))["verdict"] == "일치"


def test_제품_위험물_행이_여럿이면_하나라도_맞으면_된다():
    inputs = _dg_inputs({"item": "제3석유류"}, flash=30)
    inputs["dangerous_goods"].append({"comp_ref": "MIX", "class": "제4류", "item": "제2석유류"})
    assert _dg(inputs, {}, _dg_know("제2석유류 비수용성액체"))["verdict"] == "일치"


@pytest.mark.parametrize("written,group,flash", [("제1석유류", "알코올류", 13), ("제1석유류", "특수인화물", None), ("제4석유류", "동식물유류", 240)])
def test_9항으로_못_정하는_DB_품명과_다르면_불일치다(written, group, flash):  # 에탄올을 제1석유류로 적은 경우
    v = _dg(_dg_inputs({"item": written}, flash=flash, kind="단일물질"), {}, _dg_know(group))
    assert v["verdict"] == "불일치" and group in v["reason"]


@pytest.mark.parametrize("written", ["제 2 석유류", "제2석유류 비수용성액체"])
def test_품명_표기_변형을_같게_본다(written):
    assert _dg(_dg_inputs({"item": written}), {}, _dg_know("제2석유류 비수용성액체"))["verdict"] == "일치"


def test_불순물_규칙을_적용_못하면_judge_결과에_남는다(repo):
    doc = _toluene_with_benzene(_q(0.2, "%"))
    doc["doc"] = {"doc_id": "X"}
    doc["msds"][0]["components"][1]["cas_no"] = None
    assert any("불순물 벤젠" in x["text"] for x in judge(doc, "2026-11-03", repo)["results"][0]["limitations"])


def test_수생이_아닌_12항_값은_교차_확인에_쓰지_않는다(repo, contract_errors):
    soil = _tox("ECO_SOIL", 0.5, "mg/L", descriptor="EC50")
    assert _cross(repo, _single([{"class_code": "ENV_AQ_ACUTE", "category": "3"}], ecotox=[soil]), contract_errors) == {}


def test_하루_노출_값은_교차_확인에_쓰지_않는다(repo, contract_errors):
    row = _tox("TX_INHAL", 30, "mg/L", descriptor="LC50", physical_form="증기", duration_value=1, duration_unit="day")
    assert _cross(repo, _single([{"class_code": "HH_ACUTE_INHAL", "category": "4", "route_form": "증기"}], [row]), contract_errors) == {}


def _thinner_doc(classes):
    return {"doc": {"doc_id": "X"}, "msds": [{"composition": {"type": "혼합물"}, "hazard": {"classes": classes}, "toxicity": [],
                                               "components": [{"seq": i + 1, "cas_no": c, "name": c, "content": _q(v, "%"), "trade_secret": False} for i, (c, v) in enumerate(THINNER)],
                                               "physchem": [_prop("APPEARANCE_STATE", None, text="액체")]}]}


def _stot(repo, classes):
    c = run_consistency(_thinner_doc(classes), repo)["consistency"]
    return next(f for f in c["findings"] if f.get("class_code") == "HH_STOT_SE")


def test_표적장기_구분3_효과가_같으면_일치다(repo):  # P02. 전에는 분류안됨으로 판정해 거짓 불일치
    f = _stot(repo, [{"class_code": "HH_STOT_SE", "category": "3", "effect": "마취"}, {"class_code": "HH_STOT_SE", "category": "3", "effect": "호흡기계 자극"}])
    assert f["verdict"] == "일치" and "3:마취" in f["our_value"]["low"]


def test_표적장기_구분3을_안_적으면_과소가_아니라_누락으로_잡는다(repo):
    f = _stot(repo, [])
    assert f["verdict"] == "불일치" and "3:" in f["reason"]


def test_표적장기_구분3_효과가_하나_빠지면_불일치다(repo):
    f = _stot(repo, [{"class_code": "HH_STOT_SE", "category": "3", "effect": "마취"}])
    assert f["verdict"] == "불일치" and "호흡기" in f["reason"]


def test_표적장기_효과_없이_구분3만_적어도_일치다(repo):  # 세부 표기 차이
    assert _stot(repo, [{"class_code": "HH_STOT_SE", "category": "3"}])["verdict"] == "일치"


def test_수유독성은_표적장기_구분3_비교로_가지_않는다():  # 회귀 방지
    from msds.compliance.mixture.verdict import aggregate_verdicts
    results = [{"class_code": "HH_REPRO", "form": None, "result": {"low": "1A", "high": "1A", "status": "확정"},
                "extra": {"low": [{"category": "수유독성", "effect": None}], "high": [{"category": "수유독성", "effect": None}]}}]
    v = aggregate_verdicts(results, [{"class_code": "HH_REPRO", "category": "1A"}])["verdicts"][0]
    assert v["verdict"] == "일치" and "None" not in (v["reason"] or "")


def test_혼합물의_류와_품명이_어긋나면_불일치다():
    v = _dg(_dg_inputs({"item": "제1석유류", "class": "제3류"}, flash=11.8), {}, _dg_know("제1석유류 비수용성액체"))
    assert v["verdict"] == "불일치" and "류:" in v["reason"]


@pytest.mark.parametrize("written", ["제 4 류", "제4류 위험물"])
def test_류_표기_변형을_같게_본다(written):
    v = _dg(_dg_inputs({"item": "제2석유류", "class": written}, kind="단일물질"), {}, _dg_know("제2석유류 비수용성액체"))
    assert v["verdict"] == "일치"


def test_제4류가_아닌_물질의_품명_표시는_인화점_품명이_아니다():
    v = _dg(_dg_inputs({"item": "유기과산화물", "class": "제5류"}, flash=50, kind="단일물질"), {}, _dg_know("유기과산화물(2종)", "제5류"))
    assert v["db_threshold"] is None


def test_표적장기_효과를_한_칸에_더_적으면_과대다():
    from msds.compliance.mixture.verdict import aggregate_verdicts
    results = [{"class_code": "HH_STOT_SE", "form": None, "result": {"low": "분류안됨", "high": "분류안됨", "status": "확정"},
                "extra": {"low": [{"category": "3", "effect": "호흡기자극"}], "high": [{"category": "3", "effect": "호흡기자극"}]}}]
    v = aggregate_verdicts(results, [{"class_code": "HH_STOT_SE", "category": "3", "effect": "호흡기도자극성, 마취영향"}])["verdicts"][0]
    assert (v["verdict"], v["type"]) == ("불일치", "과대분류")


@pytest.mark.parametrize("written,ours", [("졸음 또는 현기증", "마취"), ("기도 자극", "호흡기자극")])
def test_표적장기_효과_동의어를_같게_본다(written, ours):
    from msds.compliance.mixture.verdict import aggregate_verdicts
    results = [{"class_code": "HH_STOT_SE", "form": None, "result": {"low": "분류안됨", "high": "분류안됨", "status": "확정"},
                "extra": {"low": [{"category": "3", "effect": ours}], "high": [{"category": "3", "effect": ours}]}}]
    assert aggregate_verdicts(results, [{"class_code": "HH_STOT_SE", "category": "3", "effect": written}])["verdicts"][0]["verdict"] == "일치"


def test_표적장기_구분2_누락_문구가_사실과_맞다():
    from msds.compliance.mixture.verdict import aggregate_verdicts
    results = [{"class_code": "HH_STOT_SE", "form": None, "result": {"low": "2", "high": "2", "status": "확정"},
                "extra": {"low": [{"category": "3", "effect": "마취"}], "high": [{"category": "3", "effect": "마취"}]}}]
    v = aggregate_verdicts(results, [{"class_code": "HH_STOT_SE", "category": "3", "effect": "마취"}])["verdicts"][0]
    assert v["type"] == "과소분류" and "항목 없음" not in v["reason"] and "3:마취" in v["reason"]


def test_12항_만성_시험값은_급성_교차_확인에_쓰지_않는다(repo, contract_errors):
    fish = _tox("ECO_FISH", 0.5, "mg/L", descriptor="LC50", duration_value=28, duration_unit="day")
    assert _cross(repo, _single([{"class_code": "ENV_AQ_ACUTE", "category": "3"}], ecotox=[fish]), contract_errors) == {}


def _q3_result(excluded, *, low="분류안됨", high=None, name="황산", content=95.0, non_toxic_also=True):
    inputs = [{"cas": "7664-93-9", "name": name, "content": {"low": content, "high": content}, "used_as": [], "flags": [], "excluded": excluded}]
    if non_toxic_also:
        inputs.append({"cas": "7732-18-5", "name": "물", "content": {"low": 5.0, "high": 5.0}, "used_as": [], "flags": [], "excluded": "무독성"})
    return {"class_code": "ENV_AQ_CHRONIC", "form": None, "result": {"low": low, "high": high or low, "status": "확정"}, "inputs": inputs, "calc": {"include_min": 1.0}}


@pytest.mark.parametrize("excluded", ["해당 분류 없음", "분류 정보 없음"])
def test_기준_분류가_없는_성분이_있으면_MSDS를_과대분류라_하지_않는다(excluded):
    # 지식DB에는 "분류 안 됨" 행이 없다. 빈칸은 자료 없음이라 MSDS가 틀렸다는 증거가 못 된다 (멘토링 3번, 설계서 38장)
    from msds.compliance.mixture.verdict import aggregate_verdicts

    msds = [{"class_code": "ENV_AQ_CHRONIC", "category": "3"}]
    row = aggregate_verdicts([_q3_result(excluded)], msds)["verdicts"][0]
    assert (row["verdict"], row["type"]) == ("근거부족", None)
    assert "황산" in row["reason"]


def test_기준_분류가_없는_성분이_있어도_양쪽_다_분류없음이면_일치다():
    from msds.compliance.mixture.verdict import aggregate_verdicts

    assert aggregate_verdicts([_q3_result("해당 분류 없음")], [])["verdicts"][0]["verdict"] == "일치"


def test_물과_한계농도_미만_성분만_빈칸이면_과대분류를_유지한다():
    from msds.compliance.mixture.verdict import aggregate_verdicts

    msds = [{"class_code": "ENV_AQ_CHRONIC", "category": "3"}]
    row = aggregate_verdicts([_q3_result("무독성")], msds)["verdicts"][0]
    assert row["type"] == "과대분류"
    row = aggregate_verdicts([_q3_result("해당 분류 없음", content=0.5)], msds)["verdicts"][0]
    assert row["type"] == "과대분류"




def test_합산_때문에_분류되면_TO21_기준으로_표시한다():
    # 고시는 성분 하나, TO21은 같은 구분 합산이다 (D-16, 설계서 35장). 합산으로만 분류되면 그 사실을 알린다
    from msds.compliance.mixture.classify_mixture import classify_item
    from msds.compliance.mixture.verdict import aggregate_verdicts
    from msds.compliance.mixture.rules_loader import load_mixture_rules

    code = next(k for k, v in load_mixture_rules()["classes"].items() if v.get("aggregate") == "sum" and k == "HH_CARCINOGEN")
    comps = lambda a, b: [{"cas": n, "name": n, "low": p, "high": p, "flags": [], "m": None,
                           "class_rows": [{"result_code": "GHS021003", "source": "KR03"}]} for n, p in (("가", a), ("나", b))]
    both = classify_item(code, comps(0.6, 0.6), {})
    assert both["result"]["low"] == "2" and both["result"]["to21_sum"] is True
    row = aggregate_verdicts([both], [{"class_code": code, "category": "2"}])["verdicts"][0]
    assert row["verdict"] == "일치" and "TO21 기준" in row["reason"]
    alone = classify_item(code, comps(1.5, 0.6), {})
    assert not alone["result"].get("to21_sum")


# ── 혼합물 위험물은 제품 기준 (고시 제11조⑪ "혼합물 전체로서", 멘토링 10-1) ──────────
def test_혼합물은_성분_지정만으로_위험물_해당을_확정하지_않는다():
    # 톨루엔 소량 + 물처럼 제품 인화점이 없는데 성분만 지정된 경우. T21-050은 MSDS '비위험물'을 규제 누락으로 냈다
    row = {"item": None, "class": "해당없음"}
    v = _dg(_dg_inputs(row, flash=None), {}, _dg_know("제1석유류 비수용성액체"))
    assert (v["verdict"], v["type"]) == ("경계", None)
    assert "성분" in v["reason"]


def test_혼합물이_해당으로_적었고_성분이_지정이면_일치다():
    v = _dg(_dg_inputs({"item": "제1석유류"}, flash=None), {}, _dg_know("제1석유류 비수용성액체"))
    assert v["verdict"] == "일치"


def test_혼합물의_제품_인화점으로_품명이_정해지면_해당이다():
    v = _dg(_dg_inputs({"item": None, "class": "해당없음"}, flash=10), {}, _dg_know("제1석유류 비수용성액체"))
    assert v["type"] == "규제 누락"


def test_함량_제외_규정이_있는_품명은_DB_행이_있어도_혼합물은_경계다():
    # 시행령 별표 1 비고: 제3·4석유류 가연성 액체량 40중량% 이하 제외 등 (문제 목록 25번)
    v = _dg(_dg_inputs({"item": None, "class": "해당없음"}, flash=220), {}, _dg_know("제4석유류 비수용성액체"))
    assert v["verdict"] == "경계"
    assert _dg(_dg_inputs({"item": "제4석유류"}, flash=220), {}, _dg_know("제4석유류 비수용성액체"))["verdict"] == "일치"
    single = _dg(_dg_inputs({"item": "제4석유류"}, flash=220, kind="단일물질"), {}, _dg_know("제4석유류 비수용성액체"))
    assert single["verdict"] == "일치"


def test_액상도_제4류_액체로_본다():
    from msds.compliance.sec15_judge import _class4

    phys = {"APPEARANCE_STATE": [{"text_value": "액상도료"}], "FLASH_POINT": [{"comp_ref": "MIX", "q": {"value": 30}}]}
    assert _class4(phys)[0] == "제2석유류"


def test_제2석유류_제외_규정은_인화점_40도_이상일_때만_적용한다():
    none = {"item": None, "class": "해당없음"}
    assert _dg(_dg_inputs(none, flash=30), {}, [])["type"] == "규제 누락"
    assert _dg(_dg_inputs(none, flash=40), {}, [])["verdict"] == "경계"


def test_화평법_항목_누락이_계약을_지킨다(contract_errors):
    from msds.judge.display import finding_display

    path = Path(__file__).resolve().parents[3] / "data" / "silver" / "claude" / "T21-025.json"
    if not path.exists():
        pytest.skip("실버 없음")
    doc = json.loads(path.read_text(encoding="utf-8"))
    m = doc["msds"][0]
    m["meta"]["last_revision_date"] = "2026-01-01"
    m["regulations"] = [r for r in m["regulations"] if r.get("law") != "KREACH"]
    out = judge(doc, "2026-11-03", CsvRepo())
    assert contract_errors("3-consistency.schema.json", out) == []
    f = next(x for r in out["results"] for x in r["findings"] if "KREACH_SECTION" in x["id"])
    assert (f["verdict"], f["type"], f["severity"]) == ("불일치", "화평법 항목 누락", "중간")
    d = finding_display(f, None)
    assert d["expected"] and d["component"] == "제품"


def _alcohol(pct, water=True, row=None, flash=25):
    comps = [{"seq": 1, "cas_no": "64-17-5", "content": {"lower": pct - 1, "upper": pct, "unit": "%"}}]
    if water:
        comps.append({"seq": 2, "cas_no": "7732-18-5", "content": {"lower": 100 - pct, "upper": 101 - pct, "unit": "%"}})
    return {**_dg_inputs(row or {"item": None, "class": "해당없음"}, flash=flash), "components": comps}


def test_알코올_60중량퍼센트_미만_수용액은_규제_누락이_아니라_경계다():
    # 시행령 별표 1 비고 14호 가목. 하이콜 59 같은 소독제가 인화점만으로 위험물 누락이 되면 안 된다
    know = _dg_know("알코올류 수용성액체")
    assert _dg(_alcohol(59), {}, know)["verdict"] == "경계"
    assert _dg(_alcohol(59), {}, [])["verdict"] == "경계"


@pytest.mark.parametrize("pct,water", [(70, True), (59, False)])
def test_알코올_제외_조건을_벗어나면_인화점대로_해당이다(pct, water):
    assert _dg(_alcohol(pct, water), {}, [])["type"] == "규제 누락"


# ── 알코올 수용액·인화점 표기 (재현 기반 검토) ──────────────────────
def _mix(comps, row=None, flash=25):
    return {**_dg_inputs(row or {"item": None, "class": "해당없음"}, flash=flash), "components": comps}


def _c(cas, lower=None, upper=None, value=None, name=None):
    return {"cas_no": cas, "name": name, "content": {"lower": lower, "upper": upper, "value": value, "unit": "%"}}


@pytest.mark.parametrize("comps", [
    [_c("64-17-5", value=59), _c("7732-18-5", value=41)],
    [_c("64-17-5", 50, 70), _c("7732-18-5", 30, 50)],
    [_c("64-17-5", 58, 59), _c(None, 41, 42, name="정제수")],
])
def test_알코올_수용액_표기가_달라도_같게_경계다(comps):
    assert _dg(_mix(comps), {}, [])["verdict"] == "경계"


def test_물이_조금_든_용제는_알코올_수용액이_아니다():
    comps = [_c("108-88-3", 90, 94), _c("67-56-1", 1, 5), _c("7732-18-5", 0, 1)]
    assert _dg(_mix(comps, flash=5), {}, [])["type"] == "규제 누락"


def _phys(state="액체", **q):
    return {"APPEARANCE_STATE": [{"comp_ref": "MIX", "text_value": state}], "FLASH_POINT": [{"comp_ref": "MIX", "q": q}]}


def test_화씨_인화점을_섭씨로_바꾼다():
    from msds.compliance.sec15_judge import _class4

    assert _class4(_phys(value=100, unit="°F"))[0] == "제2석유류"
    assert _class4(_phys(value=100, unit="℃"))[0] == "제3석유류"


@pytest.mark.parametrize("q,edge", [({"upper": 23, "upper_op": "<", "raw": "<23℃"}, True), ({"lower": 93, "lower_op": ">", "raw": ">93℃"}, True),
                                    ({"lower": 250, "lower_op": ">", "raw": ">250℃"}, False)])
def test_인화점_범위_표기는_품명을_정하지_않고_경계다(q, edge):
    from msds.compliance.sec15_judge import _class4

    item, got = _class4(_phys(**q))[:2]
    assert (item, got) == (None, edge)
    v = _dg({**_dg_inputs({"item": None, "class": "해당없음"}), "physchem": _phys(**q)}, {}, [])
    assert v["verdict"] == ("경계" if edge else "일치")


@pytest.mark.parametrize("state", ["Liquid", "용액", "수용액", "오일"])
def test_액체를_뜻하는_성상을_알아본다(state):
    from msds.compliance.sec15_judge import _class4

    assert _class4(_phys(state, value=10))[:2] == ("제1석유류", False)


@pytest.mark.parametrize("state", ["", "페이스트", "겔상"])
def test_액체인지_모르는_성상에_인화점이_있으면_경계다(state):
    from msds.compliance.sec15_judge import _class4

    assert _class4(_phys(state, value=10))[:2] == ("제1석유류", True)


def test_고체는_인화점이_있어도_제4류가_아니다():
    from msds.compliance.sec15_judge import _class4

    assert _class4(_phys("백색 분말", value=10))[0] is None


def test_인화점이_없는데_MSDS만_위험물이면_과기재가_아니라_근거부족이다():
    v = _dg(_dg_inputs({"item": "제1석유류"}, flash=None), {}, [])
    assert (v["verdict"], v["type"]) == ("근거부족", None)


def test_물은_함량이_없어도_빈칸_성분으로_세지_않는다():
    item = classify_item("HH_CARCINOGEN", [{"cas": "7732-18-5", "name": "물", "low": None, "high": None, "flags": [], "m": None, "class_rows": [], "non_toxic": True}], {})
    assert item["inputs"][0]["excluded"] == "무독성"


def test_화평법_줄은_사람이_읽는_이름과_문장을_쓴다():
    from msds.compliance.explain import _summary, item_names

    assert item_names()["KREACH_SECTION"] == "화평법 규제현황 기재"
    text = _summary({"finding": {"section": "15", "item_name": "규제현황 기재", "type": "화평법 항목 누락", "verdict": "불일치", "component": "MIX"}})
    assert "화평법" in text and "판정하지 못했" not in text


# ── 재검증 2차 (위험물) ───────────────────────────────────────
@pytest.mark.parametrize("states", [["입자가 없는 투명 액체"], ["액체(저온에서 결정 석출)"], ["고체", "액체"]])
def test_고체_낱말이_함께_있어도_액체를_놓치지_않는다(states):
    from msds.compliance.sec15_judge import _class4

    phys = {"APPEARANCE_STATE": [{"comp_ref": "MIX", "text_value": t} for t in states], "FLASH_POINT": [{"comp_ref": "MIX", "q": {"value": 15}}]}
    assert _class4(phys)[0] == "제1석유류"


def test_성분_1개_문서의_인화점_행을_쓴다():
    inp = _dg_inputs({"item": None, "class": "해당없음"}, flash=None)
    inp["physchem"]["FLASH_POINT"] = [{"comp_ref": "1", "q": _q(15, "℃")}]
    assert _dg(inp, {}, [])["type"] == "규제 누락"


def test_자료_없는_성분이_있으면_급성독성도_과대분류라_하지_않는다():
    from msds.compliance.mixture.verdict import aggregate_verdicts

    r = {"class_code": "HH_ACUTE_ORAL", "form": None, "result": {"low": "4", "high": "4", "status": "확정"},
         "inputs": [{"name": "A", "content": {"low": 50, "high": 50}, "excluded": None},
                    {"name": "B", "content": {"low": 50, "high": 50}, "excluded": "자료 없음"}], "calc": {}}
    row = aggregate_verdicts([r], [{"class_code": "HH_ACUTE_ORAL", "category": "3"}])["verdicts"][0]
    assert row["verdict"] == "근거부족"


def test_품명이_아닌_글은_품명으로_비교하지_않는다():
    assert _dg(_dg_inputs({"item": "인화성액체"}, flash=10), {}, [])["verdict"] == "일치"


def test_단일물질의_성분_위험물_행도_품명을_비교한다():
    inp = _dg_inputs({"item": "제2석유류"}, flash=10, kind="단일물질")
    inp["dangerous_goods"][0]["comp_ref"] = "1"
    assert _dg(inp, {}, [])["type"] == "기준 불일치"


def test_알코올_상한만_적혀도_수용액으로_본다():
    assert _dg(_mix([_c("64-17-5", upper=59), _c(None, 41, 45, name="탈이온수")]), {}, [])["verdict"] == "경계"


def test_알코올_60_이상_수용액은_알코올류다():
    v = _dg(_mix([_c("64-17-5", 70, 75), _c("7732-18-5", 25, 30)], row={"item": "제1석유류"}, flash=13), {}, [])
    assert v["type"] == "기준 불일치" and "알코올류" in v["reason"]


def test_화씨_범위_인화점():
    v = _dg({**_dg_inputs({"item": None, "class": "해당없음"}), "physchem": _phys(lower=400, lower_op=">", unit="°F", raw=">400°F")}, {}, [])
    assert v["verdict"] == "경계"
    from msds.compliance.sec15_judge import _class4

    assert _class4(_phys(value=50, unit="℉"))[0] == "제1석유류"


@pytest.mark.parametrize("state", ["Gas", "Liquefied gas", "Compressed gas"])
def test_영문_가스_성상(state):
    from msds.compliance.sec15_judge import _class4

    assert _class4(_phys(state, value=-60))[:2] == (None, False)


def test_제4류_밖_위험물_표기는_근거부족이다():
    v = _dg(_dg_inputs({"item": None, "class": "제6류"}, flash=None), {}, [])
    assert v["verdict"] == "근거부족"


def test_인화점_40도_미만_고체는_인화성고체일_수_있어_경계다():
    v = _dg({**_dg_inputs({"item": None, "class": "해당없음"}), "physchem": _phys("고체", value=30)}, {}, [])
    assert v["verdict"] == "경계"


def test_순물질_인화점_50도는_함량_제외_규정이_없어_해당이다():
    assert _dg(_dg_inputs({"item": None, "class": "해당없음"}, flash=50, kind="단일물질"), {}, [])["type"] == "규제 누락"


def test_자료없음_위험물_행과_인화점_자료없음은_근거부족이다():
    inp = _dg_inputs({"item": None, "class": "자료없음"}, flash=None)
    assert _dg(inp, {}, [])["verdict"] == "근거부족"


# ── 최종 검증 (PR 전) ─────────────────────────────────────────
def test_가스는_위험물_자료없음이어도_근거부족이_아니다():
    # T21-S003 질소: 가스는 시행령 별표 1의 어느 류도 아니다 (고체·액체)
    inp = {**_dg_inputs({"item": None, "class": "자료없음"}, flash=None)}
    inp["physchem"]["APPEARANCE_STATE"] = [{"comp_ref": "MIX", "text_value": "가스"}]
    assert _dg(inp, {}, [])["verdict"] == "일치"


def test_인화점_자료없음_행_뒤의_값을_읽는다():
    inp = _dg_inputs({"item": None, "class": "해당없음"}, flash=None)
    inp["physchem"]["FLASH_POINT"] = [{"comp_ref": "MIX", "q": {"value": None, "status": "자료없음"}}, {"comp_ref": "MIX", "q": _q(10, "℃")}]
    assert _dg(inp, {}, [])["type"] == "규제 누락"


@pytest.mark.parametrize("cls", ["위험물에 해당되지 않음", "규제되지 않음", "해당사항 없음"])
def test_위험물_류_칸의_부정_문구(cls):
    assert _dg(_dg_inputs({"item": None, "class": cls}, flash=10), {}, [])["type"] == "규제 누락"
