"""물리적 위험성(transport·compare) 판정 시험. physical 입력을 주지 않으면 기존대로 건너뛴다."""
import json
from pathlib import Path

import pytest

from msds.compliance.mixture.build_components import build_components
from msds.compliance.mixture.classify_mixture import classify_mixture_all
from msds.compliance.mixture.physical import classify_physical, physical_inputs
from msds.compliance.mixture.rules_loader import load_class_map, load_mixture_rules

MAP = load_class_map()["rows"]
RULES = load_mixture_rules()
SILVER = Path(__file__).resolve().parents[2] / "data" / "silver" / "claude" / "T21-025.json"


def code(class_code, category):
    return next(r["to21_result_code"] for r in MAP if (r["class_code"], r["category"], r["effect"]) == (class_code, category, ""))


def comp(name, high, *classes, low=None):
    rows = [{"result_code": code(*c), "source": "KR02"} for c in classes]
    return {"cas": name, "name": name, "low": high if low is None else low, "high": high, "class_rows": rows, "flags": [], "m": None}


UN = [{"mode": "공통", "regulated": True, "un_no": "1830", "hazard_class": "8", "packing_group": "II"}]


def run(item_id, comps, *, transport=UN, props=None, msds_classes=(), state=None):
    phys = {"transport": transport, "msds_classes": list(msds_classes)}
    return classify_physical(item_id, RULES["classes"][item_id], comps, props or {}, phys, state=state, rules=RULES)


def test_정상_판정_대표성분_분류를_채택():
    r = run("PH_METAL_CORR", [comp("황산", 98, ("PH_METAL_CORR", "1")), comp("물", 2)], props={"STATE": "액체"})
    assert r["result"] == {"low": "1", "high": "1", "status": "확정"}
    assert r["inputs"][0]["un_no"] == "1830" and r["inputs"][1]["name"] == "황산" and r["inputs"][1]["role"] == "대표성분"
    assert any("대표성분" in a for a in r["assumptions"]) and any("un_class_map" in a for a in r["assumptions"])


def test_대표성분은_상한이_가장_큰_성분이고_다른_성분_분류는_안_쓴다():
    r = run("PH_METAL_CORR", [comp("A", 30, ("PH_METAL_CORR", "1")), comp("B", 70, ("HH_SKIN_CORR", "1"))])
    assert r["inputs"][1]["name"] == "B" and r["result"]["high"] == _NO and r["result"]["status"] == "확정"


_NO = "분류안됨"


def test_UN_번호_없음은_해당_없음():
    for transport in ([], [{"mode": "공통", "regulated": True, "un_no": None}]):
        r = run("PH_METAL_CORR", [comp("A", 100, ("PH_METAL_CORR", "1"))], transport=transport)
        assert r["result"]["status"] == "해당 없음" and r["result"]["reason"]


def test_비위험물은_해당_없음():
    r = run("PH_METAL_CORR", [comp("A", 100, ("PH_METAL_CORR", "1"))], transport=[{"regulated": False, "un_no": "1830"}])
    assert r["result"]["status"] == "해당 없음" and "비위험물" in r["result"]["reason"]


def test_성상이_안_맞으면_해당_없음():
    r = run("PH_FLAM_GAS", [comp("A", 100)], props={"STATE": "액체"})
    assert r["result"]["status"] == "해당 없음" and "성상" in r["result"]["reason"]


def test_대표성분_분류정보_없으면_근거부족():
    r = run("PH_METAL_CORR", [comp("A", 100)])
    assert r["result"]["status"] == "근거부족" and "class_rows" in r["result"]["reason"]


def test_대표성분을_정할_함량이_없으면_근거부족():
    c = comp("A", None)
    r = run("PH_METAL_CORR", [c])
    assert r["result"]["status"] == "근거부족" and "함량" in r["result"]["reason"]


def test_물성_없으면_근거부족_있으면_판정():
    comps = [comp("A", 100, ("HH_SKIN_CORR", "1"))]  # 대표성분에 인화성 가스 분류가 없어 9항 물성 단계로
    lack = run("PH_FLAM_GAS", comps, props={"STATE": "가스"})
    assert lack["result"]["status"] == "근거부족" and "LEL" in lack["result"]["reason"]
    ok = run("PH_FLAM_GAS", comps, props={"STATE": "가스", "LEL": 15, "UEL": 20})
    assert ok["result"] == {"low": "2", "high": "2", "status": "확정"} and ok["rule"]["id"] == "FGAS-2"
    ok1 = run("PH_FLAM_GAS", comps, props={"STATE": "가스", "LEL": 5, "UEL": 15})
    assert ok1["result"]["high"] == "1"


def test_pH_극단이면_금속부식성에_표시만():
    r = run("PH_METAL_CORR", [comp("A", 100, ("PH_METAL_CORR", "1"))], props={"PH": 1.0})
    assert r["extra"]["hit"] is True and r["result"]["high"] == "1"
    assert "extra" not in run("PH_METAL_CORR", [comp("A", 100, ("PH_METAL_CORR", "1"))], props={"PH": 7})


def test_compare_기재값_있음():
    r = run("PH_AEROSOL", [comp("A", 100, ("PH_AEROSOL", "1"))],
            msds_classes=[{"class_code": "PH_AEROSOL", "category": "2", "raw": "에어로졸 구분2"}])
    cmp_ = r["calc"]["compare"]
    assert r["result"]["status"] == "대조" and cmp_["msds"][0]["category"] == "2" and cmp_["ours"][0]["category"] == "1"
    assert "verdict" not in json.dumps(r)  # 일치·불일치 판정은 하지 않는다


def test_compare_기재값_없음():
    r = run("PH_PRESS_GAS", [comp("A", 100)], props={"STATE": "액체"})
    assert r["result"]["status"] == "대조"
    assert r["calc"]["compare"] == {"msds": None, "ours": None} and r["inputs"][0]["state"] == "액체"


def test_physical_없으면_기존처럼_건너뜀():
    out = classify_mixture_all([comp("A", 100)], {}, state="액체")
    assert {r["class_code"]: r["skipped"] for r in out if "skipped" in r}["PH_AEROSOL"] == "compare"


def test_physical_주면_16항목_모두_결과():
    out = classify_mixture_all([comp("A", 100)], {}, state="액체", physical={"transport": UN, "msds_classes": []})
    ph = [r for r in out if r["class_code"].startswith("PH_")]
    assert len(ph) == 16 and not any("skipped" in r for r in ph)
    assert all({"class_code", "result", "rule", "inputs", "assumptions"} <= set(r) for r in ph)


@pytest.mark.skipif(not SILVER.exists(), reason="T21-025.json 없음")
def test_25번_황산():
    msds = json.loads(SILVER.read_text(encoding="utf-8"))["msds"][0]
    skin = [("HH_SKIN_CORR", "1"), ("PH_METAL_CORR", "1")]
    rows = lambda cas: [{"result_code": code(*c), "source": "KR03"} for c in skin] if cas == "7664-93-9" else []
    b = build_components(msds, rows)
    out = classify_mixture_all(b["components"], b["mixture_props"], state="액체", physical=physical_inputs(msds))
    by = {r["class_code"]: r for r in out if r["class_code"].startswith("PH_")}
    assert by["PH_METAL_CORR"]["result"] == {"low": "1", "high": "1", "status": "확정"}
    assert by["PH_FLAM_GAS"]["result"]["status"] == "해당 없음"  # 액체라 가스 항목 제외
    assert by["PH_PRESS_GAS"]["result"]["status"] == "대조" and by["PH_AEROSOL"]["calc"]["compare"] == {"msds": None, "ours": None}
    assert by["PH_EXPLOSIVE"]["result"]["status"] == "확정" and by["PH_EXPLOSIVE"]["result"]["high"] == "분류안됨"
