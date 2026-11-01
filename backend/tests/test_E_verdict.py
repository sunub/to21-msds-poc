"""verdict.aggregate_verdicts 시험: 판정 4종, 불일치 4유형, 경계, 근거부족, 해당 없음·대조 분리, 결정성."""
import copy
import json
from pathlib import Path

import pytest

from msds.compliance.mixture import verdict as V
from msds.compliance.mixture.build_components import build_components
from msds.compliance.mixture.classify_mixture import classify_mixture_all
from msds.compliance.mixture.physical import physical_inputs
from msds.compliance.mixture.rules_loader import load_class_map
from msds.compliance.mixture.verdict import aggregate_verdicts

SILVER = Path(__file__).resolve().parents[2] / "data" / "silver" / "claude" / "T21-025.json"
ORAL = "HH_ACUTE_ORAL"  # 구분 순서가 acute_tox_ate.csv 에 정의됨 (1이 가장 위험)


def res(low, high=None, status=None, cc=ORAL, form=None, **kw):
    high = low if high is None else high
    status = status or ("확정" if low == high else "경계")
    return {"class_code": cc, "form": form, "result": {"low": low, "high": high, "status": status, **kw}}


def msds(*cats, cc=ORAL, form=None):
    return [{"class_code": cc, "category": c, "route_form": form, "effect": None} for c in cats]


def one(result, classes):
    out = aggregate_verdicts([result], classes)
    assert len(out["verdicts"]) == 1 and not out["excluded"]
    return out["verdicts"][0]


def test_일치():
    v = one(res("3"), msds("3"))
    assert (v["verdict"], v["type"], v["severity"], v["rule_id"]) == ("일치", None, None, V.RULE_IDS["match"])
    assert v["msds_value"] == ["3"] and v["our_value"] == {"low": "3", "high": "3"}


def test_일치_세부구분과_분류없음_양쪽():
    assert one(res("1", cc="HH_SKIN_CORR"), msds("1B", cc="HH_SKIN_CORR"))["verdict"] == "일치"
    assert one(res("분류안됨"), [])["verdict"] == "일치"


@pytest.mark.parametrize("ours, stated, case, typ, sev", [
    ("2", ["4"], V.UNDER, "과소분류", "높음"),       # MSDS가 더 약함
    ("4", ["2"], V.OVER, "과대분류", "낮음"),        # MSDS가 더 강함
    ("3", [], V.MISSING, "과소분류", "높음"),        # MSDS에 항목 없음 (설계서 18장: 미기재도 과소분류)
    ("분류안됨", ["4"], V.EXTRA, "과대분류", "낮음"),  # 우리는 분류 없음 (설계서 18장: 추가 기재는 과대분류)
])
def test_불일치_4유형(ours, stated, case, typ, sev):
    v = one(res(ours), msds(*stated))
    assert (v["verdict"], v["type"], v["severity"]) == ("불일치", typ, sev)
    assert v["rule_id"] == V.RULE_IDS["type"][case]


def test_경계_MSDS가_범위_안():
    for stated in (["4"], ["2"], ["3"], []):  # 범위 끝값, 사이값, 미기재(분류안됨이 끝값)
        v = one(res("분류안됨" if not stated else "4", "2"), msds(*stated))
        assert v["verdict"] == "경계", stated
    assert one(res("4", "2"), msds("3"))["verdict"] == "경계"  # 순서로 범위 안


def test_경계인데_MSDS가_범위_밖이면_불일치():
    assert one(res("4", "3"), msds("1"))["type"] == "과대분류"
    assert one(res("3", "2"), msds("5"))["type"] == "과소분류"
    assert one(res("3", "2"), [])["type"] == "과소분류"


def test_근거부족():
    v = one(res(None, None, "근거부족", reason="함량 없음"), msds("3"))
    assert v["verdict"] == "근거부족" and v["reason"] == "함량 없음" and v["type"] is None


def test_위험_순서_정의_없으면_근거부족():
    v = one(res("1", cc="PH_METAL_CORR"), msds("2", cc="PH_METAL_CORR"))  # PH_* 는 rules 가 없어 순서 정의 없음
    assert v["verdict"] == "근거부족" and "순서" in v["reason"]
    assert one(res("1", cc="PH_METAL_CORR"), msds("1", cc="PH_METAL_CORR"))["verdict"] == "일치"  # 같으면 순서 불필요
    assert one(res("분류안됨", cc="PH_METAL_CORR"), msds("1", cc="PH_METAL_CORR"))["type"] == "과대분류"


def test_order_덮어쓰기():
    out = aggregate_verdicts([res("1", cc="PH_METAL_CORR")], msds("2", cc="PH_METAL_CORR"), order={"PH_METAL_CORR": ["1", "2"]})
    assert out["verdicts"][0]["type"] == "과소분류"


def test_MSDS에만_있는_항목은_근거부족():
    out = aggregate_verdicts([], msds("2"))
    assert out["verdicts"][0]["verdict"] == "근거부족" and "우리 결과에 같은 항목이 없음" in out["verdicts"][0]["reason"]


def test_흡입은_형태별로_비교():
    results = [res("2", cc="HH_ACUTE_INHAL", form="증기"), res("2", cc="HH_ACUTE_INHAL", form="분진·미스트")]
    out = aggregate_verdicts(results, msds("2", cc="HH_ACUTE_INHAL", form="증기"))
    by = {v["form"]: v for v in out["verdicts"]}
    assert by["증기"]["verdict"] == "일치" and by["분진·미스트"]["type"] == "과소분류"


def test_해당없음_대조_건너뜀은_따로():
    results = [res("분류안됨", status="해당 없음", cc="PH_FLAM_GAS", reason="성상 불일치"),
               {"class_code": "PH_AEROSOL", "form": None, "result": {"low": None, "high": None, "status": "대조"},
                "calc": {"compare": {"msds": [{"category": "2"}], "ours": None}}},
               {"class_code": "PH_X", "skipped": "transport"}, res("3")]
    out = aggregate_verdicts(results, msds("3"))
    assert [v["class_code"] for v in out["verdicts"]] == [ORAL]
    ex = {e["class_code"]: e for e in out["excluded"]}
    assert set(ex) == {"PH_FLAM_GAS", "PH_AEROSOL", "PH_X"} and ex["PH_AEROSOL"]["status"] == "대조"
    assert ex["PH_AEROSOL"]["our_value"] is None and ex["PH_FLAM_GAS"]["reason"] == "성상 불일치"


def test_같은_입력은_항상_같고_입력_순서와_무관():
    results = [res("2"), res("1", cc="HH_SKIN_CORR"), res("3", cc="HH_EYE_DMG")]
    classes = msds("3") + msds("1", cc="HH_EYE_DMG")
    snapshot = copy.deepcopy((results, classes))
    a = aggregate_verdicts(results, classes)
    assert a == aggregate_verdicts(results, classes) == aggregate_verdicts(results[::-1], classes[::-1])
    assert (results, classes) == snapshot  # 입력을 바꾸지 않는다
    assert [v["class_code"] for v in a["verdicts"]] == sorted(v["class_code"] for v in a["verdicts"])


def test_필드_이름은_2항_전용이_아니다():
    v = one(res("3"), msds("3"))
    assert set(v) == {"class_code", "form", "verdict", "type", "severity", "msds_value", "our_value", "reason", "rule_id", "assumptions"}
    assert v["assumptions"]


@pytest.mark.skipif(not SILVER.exists(), reason="T21-025.json 없음")
def test_25번_황산_전체_집계():
    item = json.loads(SILVER.read_text(encoding="utf-8"))["msds"][0]
    MAP = load_class_map()["rows"]
    code = lambda c, cat, form="": next(r["to21_result_code"] for r in MAP if (r["class_code"], r["category"], r["effect"], r["form"]) == (c, cat, "", form))
    rows = [{"result_code": code(*x), "source": "KR03"} for x in
            (("HH_SKIN_CORR", "1"), ("HH_EYE_DMG", "1"), ("HH_ACUTE_INHAL", "2", "mist"), ("PH_METAL_CORR", "1"))]  # 가짜 class_lookup
    b = build_components(item, lambda cas: rows if cas == "7664-93-9" else [])
    results = classify_mixture_all(b["components"], b["mixture_props"], state="액체", physical=physical_inputs(item))
    out = aggregate_verdicts(results, item["hazard"]["classes"])
    by = {(v["class_code"], v["form"]): v for v in out["verdicts"]}
    assert by[("HH_SKIN_CORR", None)]["verdict"] == "일치" and by[("HH_EYE_DMG", None)]["verdict"] == "일치"
    assert by[("PH_METAL_CORR", None)]["verdict"] == "일치"
    assert by[("HH_ACUTE_INHAL", "증기")]["verdict"] == "근거부족"
    assert out == aggregate_verdicts(results, item["hazard"]["classes"])
