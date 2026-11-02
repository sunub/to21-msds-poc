"""판정 근거(trace)와 차이 원인 코드(causes) 시험 (11/02 F, 설계서 41장 반환 규격·44장 traces, D-13).

- 판정 줄마다 trace_id 가 consistency.traces 를 가리키고, 일치가 아닌 줄에는 원인 코드가 하나 이상 붙는다.
- 코드별 규칙: 과소·과대, 형태·세부 표기, 함량 범위·물성 경계, 주원인 성분, MSDS ATEmix 차이, 출처 차이, 가정값.
- 판정 값은 바꾸지 않는다(오류 주입·25번 정답본 시험이 그대로 통과하는지로 함께 확인).
앞쪽은 가짜 입력만 쓰고, 뒤쪽 25번·silver 시험은 로컬에 샘플 CSV·silver 추출본이 있을 때만 돈다(D-47).
"""
import json
from pathlib import Path

import pytest

from msds.compliance.consistency import run_consistency
from msds.compliance.htodb.csv_repo import CsvRepo
from msds.compliance.trace import CAUSE_TEXT, label_causes, mixture_causes

SILVER = Path(__file__).resolve().parents[2] / "data" / "silver" / "claude"


def row(verdict="불일치", type_=None, low="1", high=None, msds=("2",), form=None, msds_form=None, cc="HH_SKIN_CORR",
        reason="r"):
    return {"class_code": cc, "form": form, "verdict": verdict, "type": type_, "msds_value": list(msds) if msds else None,
            "msds_form": msds_form if msds_form is not None else form, "our_value": {"low": low, "high": high or low},
            "reason": reason}


def codes(cs):
    return [c["code"] for c in cs]


def test_일치_줄에는_원인이_없다():
    assert mixture_causes(row("일치", msds=("1",)), {"inputs": []}, [], {}) == []


def test_과소분류와_주원인_성분():
    tr = {"inputs": [{"name": "A", "cas": "1", "content": {"low": 3, "high": 7}, "used_as": ["1"], "excluded": None},
                     {"name": "B", "cas": "2", "content": {"low": 1, "high": 3}, "used_as": ["1"], "excluded": None},
                     {"name": "물", "content": {"low": 90, "high": 96}, "used_as": [], "excluded": "분류 정보 없음"}]}
    cs = mixture_causes(row(type_="과소분류"), tr, [], {})
    assert codes(cs) == ["CAT_LOWER", "MAIN_COMPONENT"]
    main = cs[1]
    assert (main["name"], main["share"], main["basis"]) == ("A", 0.7, "함량 상한 비율")


def test_계산_결과가_분류안됨이면_성분_제외_사유를_붙인다():
    tr = {"inputs": [{"name": "황산", "excluded": "해당 분류 없음", "used_as": []}, {"name": "물", "excluded": "분류 정보 없음"}]}
    c = mixture_causes(row(type_="과대분류", low="분류안됨", msds=("3",)), tr, [], {})[0]
    assert c["code"] == "CAT_HIGHER" and "황산(해당 분류 없음)" in c["text"] and len(c["components"]) == 2


def test_형태_차이와_세부_표기():
    assert "FORM_DIFF" in codes(mixture_causes(row(type_="형태·세부 표기", low="2", msds=("2",), form="분진·미스트",
                                                   msds_form="증기", cc="HH_ACUTE_INHAL"), {"inputs": []}, [], {}))
    assert codes(mixture_causes(row(type_="형태·세부 표기", low="압축가스", msds=("냉동액화가스",), cc="PH_PRESS_GAS"),
                                {"inputs": []}, [], {})) == ["DETAIL_DIFF"]


def test_경계는_함량_범위와_물성_결측을_구분한다():
    assert "RANGE_EDGE" in codes(mixture_causes(row("경계", low="2", high="1"), {"inputs": []}, [], {}))
    tr = {"inputs": [{"role": "물성", "flash_point": [], "boiling": []}]}
    assert "PROP_EDGE" in codes(mixture_causes(row("경계", low="2", high="1", cc="PH_FLAM_LIQ"), tr, [], {}))


def test_MSDS_ATEmix가_계산값과_떨어져_있으면():
    tr = {"inputs": [], "calc": {"ate_mix_low": 0.403, "ate_mix_high": 0.383}}
    item = {"toxicity": [{"comp_ref": "MIX", "endpoint": "TX_INHAL", "q": {"raw": "0.5mg/L < ATEmix <= 2.0mg/L",
                                                                          "lower": 0.5, "upper": 2.0, "unit": "mg/L"}}]}
    v = row(type_="형태·세부 표기", low="2", msds=("2",), form="분진·미스트", msds_form="증기", cc="HH_ACUTE_INHAL")
    c = next(c for c in mixture_causes(v, tr, [], item) if c["code"] == "ATE_VALUE_DIFF")
    assert c["unit"] == "mg/L" and c["ours"] == {"low": 0.383, "high": 0.403}
    item["toxicity"][0]["q"].update(lower=0.4, raw="0.4 < ATEmix")                 # 5% 안쪽(0.403 ≥ 0.38)이면 같은 값
    assert "ATE_VALUE_DIFF" not in codes(mixture_causes(v, tr, [], item))
    item["toxicity"][0]["q"].update(unit="ppm")                                      # 단위가 다르면 비교하지 않음
    assert "ATE_VALUE_DIFF" not in codes(mixture_causes(v, tr, [], item))


def test_환경부와_고용노동부_분류가_다르면():
    comps = [{"name": "황산", "cas": "7664-93-9", "class_rows": [
        {"class_code": "HH_ACUTE_INHAL", "category": "2", "form": "gas", "source": "KR02"},
        {"class_code": "HH_ACUTE_INHAL", "category": "2", "form": "mist", "source": "KR03"},
        {"class_code": "HH_SKIN_CORR", "category": "1", "source": "KR02"}]}]
    c = next(c for c in mixture_causes(row(type_="과소분류", cc="HH_ACUTE_INHAL"), {"inputs": []}, comps, {})
             if c["code"] == "SOURCE_DIFF")
    assert c["by_source"] == {"고용노동부": ["2(분진·미스트)"], "환경부": ["2(가스)"]}
    assert "SOURCE_DIFF" not in codes(mixture_causes(row(type_="과소분류"), {"inputs": []}, comps, {}))  # 피부는 한 출처뿐


def test_가정값_사용():
    tr = {"inputs": [], "assumptions": ["M 계수 없음 → 규칙표 m_factor_default(1) 사용: X (지식DB 급성 L(E)C50 쓸 값 없음)"]}
    assert "ASSUMED" in codes(mixture_causes(row(type_="과소분류", cc="ENV_AQ_CHRONIC"), tr, [], {}))


def test_표시_요소_원인은_어느_분류에서_나왔는지():
    f = {"item": "pictograms", "derived": ["GHS05", "GHS06"], "msds": ["GHS05"], "missing": ["GHS06"], "extra": []}
    c = label_causes("불일치", f, "그림문자", {"GHS06": ["HH_ACUTE_ORAL 3"]})[0]
    assert c["code"] == "LABEL_MISSING" and c["from_classes"] == ["HH_ACUTE_ORAL 3"]


# ── 25번 황산·silver (샘플 CSV) ─────────────────────────────────────────

@pytest.fixture(scope="module")
def c25():
    repo, path = CsvRepo(), SILVER / "T21-025.json"
    if not (repo.available() and path.exists()):
        pytest.skip("to21_sample CSV 또는 25번 추출본 없음")
    return run_consistency(json.loads(path.read_text(encoding="utf-8")), repo)["consistency"]


def test_25번_흡입은_형태_차이와_주원인_ATEmix_차이_출처_차이(c25):
    f = next(f for f in c25["findings"] if f.get("class_code") == "HH_ACUTE_INHAL" and f["verdict"] == "불일치")
    assert codes(f["causes"]) == ["FORM_DIFF", "MAIN_COMPONENT", "ATE_VALUE_DIFF", "SOURCE_DIFF"]
    tr = c25["traces"][f["trace_id"]]
    assert tr["kind"] == "mixture" and tr["rule"]["id"] == "ATE-MIX-01" and tr["result"]["low"] == "2"
    assert next(i for i in tr["inputs"] if i["name"] == "황산")["share"] == 1.0


def test_25번_15항_원인_코드(c25):
    by = {f["item_code"]: f for f in c25["findings"] if f["section"] == "15" and f["comp_ref"] == "1"}  # 1 = 황산
    assert codes(by["OSH_MANAGED"]["causes"]) == ["THRESHOLD_DIFF"]
    assert codes(by["OSH_SPECIAL"]["causes"]) == ["REG_MISSING"]
    tr = c25["traces"][by["OSH_SPECIAL"]["trace_id"]]
    assert tr["kind"] == "regulation" and tr["inputs"][0]["content"] == {"raw": "93 ~ 98", "low": 93, "high": 98}


def test_silver_전체_판정_줄은_trace를_가리키고_일치가_아니면_원인이_있다():
    repo = CsvRepo()
    if not repo.available() or not SILVER.exists():
        pytest.skip("to21_sample CSV 또는 silver 추출본 없음")
    n = 0
    for path in sorted(SILVER.glob("*.json")):
        if path.name.endswith(".review.json"):
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        for i in range(len(doc.get("msds") or [])):
            c = run_consistency(doc, repo, i)["consistency"]
            for f in c["findings"]:
                n += 1
                assert f["trace_id"] is None or f["trace_id"] in c["traces"], (path.stem, f["id"])
                assert all(x["code"] in CAUSE_TEXT and x["text"] for x in f["causes"]), (path.stem, f["id"])
                assert (f["verdict"] == "일치") == (not f["causes"]), (path.stem, f["id"])
    assert n > 500
