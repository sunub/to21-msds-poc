"""형태 불일치 시험 (설계서 18·24장, 규칙표 v0.3 severity.yaml SV-03).

흡입 급성독성처럼 형태(가스·증기·분진/미스트)가 있는 항목에서, 구분은 같고 형태 표기만 다르면
'불일치·형태·세부 표기·중간' 한 줄로 낸다. 25번 황산(우리 분진·미스트 2, MSDS 증기 2)이 대표 사례다.
"""
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
INHAL = "HH_ACUTE_INHAL"
VAP, MIST, GAS = "증기", "분진·미스트", "가스"


def res(low, high=None, status=None, form=None):
    high = low if high is None else high
    status = status or ("확정" if low == high else "경계")
    return {"class_code": INHAL, "form": form, "result": {"low": low, "high": high, "status": status}}


def lack(form):
    return res(None, None, "근거부족", form=form)


def msds(cat, form):
    return [{"class_code": INHAL, "category": cat, "route_form": form, "effect": None}]


def inhal(out):
    return [v for v in out["verdicts"] if v["class_code"] == INHAL]


def test_구분같고_형태만_다르면_한줄_형태세부표기_중간():
    rows = inhal(aggregate_verdicts([lack(VAP), res("2", form=MIST)], msds("2", VAP)))
    assert len(rows) == 1
    v = rows[0]
    assert (v["verdict"], v["type"], v["severity"], v["rule_id"]) == ("불일치", "형태·세부 표기", "중간", "VRD-8")
    assert (v["form"], v["msds_form"], v["msds_value"], v["our_value"]) == (MIST, VAP, ["2"], {"low": "2", "high": "2"})
    assert V.FORM_ASSUMPTION in v["assumptions"]


def test_MSDS_형태가_우리_결과에_없어도_묶는다():
    # 액체 제품이라 우리는 증기·분진/미스트만 계산했는데 MSDS가 가스로 적은 경우
    rows = inhal(aggregate_verdicts([lack(VAP), res("2", form=MIST)], msds("2", GAS)))
    merged = [v for v in rows if v["msds_form"] == GAS]
    assert len(merged) == 1 and merged[0]["type"] == "형태·세부 표기" and merged[0]["form"] == MIST
    assert not [v for v in rows if v["form"] == GAS]  # 가스 줄('우리 결과에 같은 항목 없음')은 묶여서 사라짐


def test_우리가_다른형태를_분류안됨으로_확정해도_묶는다():
    rows = inhal(aggregate_verdicts([res("분류안됨", form=VAP), res("2", form=MIST)], msds("2", VAP)))
    assert len(rows) == 1 and rows[0]["type"] == "형태·세부 표기"


def test_구분도_다르면_구분_방향으로_정하고_이유에_형태를_적는다():
    rows = inhal(aggregate_verdicts([lack(VAP), res("2", form=MIST)], msds("3", VAP)))
    assert len(rows) == 1
    v = rows[0]
    assert (v["type"], v["severity"]) == ("과소분류", "높음")  # MSDS 3이 우리 2보다 약함
    assert "형태" in v["reason"] and v["msds_form"] == VAP
    rows = inhal(aggregate_verdicts([lack(VAP), res("3", form=MIST)], msds("2", VAP)))
    assert (rows[0]["type"], rows[0]["severity"]) == ("과대분류", "낮음")


def test_MSDS가_같은_형태로_맞게_적었으면_묶지_않는다():
    rows = inhal(aggregate_verdicts([res("2", form=VAP), res("2", form=MIST)], msds("2", VAP)))
    by = {v["form"]: v for v in rows}
    assert by[VAP]["verdict"] == "일치" and by[MIST]["type"] == "과소분류"  # 미스트는 정말로 빠뜨린 것


def test_우리_결과가_범위면_묶지_않는다():
    rows = inhal(aggregate_verdicts([lack(VAP), res("3", "2", form=MIST)], msds("2", VAP)))
    assert {v["form"] for v in rows} == {VAP, MIST}


def test_같은_입력이면_같은_결과():
    args = ([lack(VAP), res("2", form=MIST)], msds("2", VAP))
    assert aggregate_verdicts(*args) == aggregate_verdicts(*args)


@pytest.mark.skipif(not SILVER.exists(), reason="T21-025.json 없음")
def test_25번_황산_흡입은_형태불일치_한줄():
    item = json.loads(SILVER.read_text(encoding="utf-8"))["msds"][0]
    MAP = load_class_map()["rows"]
    code = lambda c, cat, form="": next(r["to21_result_code"] for r in MAP
                                       if (r["class_code"], r["category"], r["effect"], r["form"]) == (c, cat, "", form))
    rows = [{"result_code": code(*x), "source": "KR03"} for x in
            (("HH_SKIN_CORR", "1"), ("HH_EYE_DMG", "1"), ("HH_ACUTE_INHAL", "2", "mist"), ("PH_METAL_CORR", "1"))]
    b = build_components(item, lambda cas: rows if cas == "7664-93-9" else [])
    results = classify_mixture_all(b["components"], b["mixture_props"], state="액체", physical=physical_inputs(item))
    out = inhal(aggregate_verdicts(results, item["hazard"]["classes"]))
    assert len(out) == 1
    v = out[0]
    assert (v["verdict"], v["type"], v["severity"]) == ("불일치", "형태·세부 표기", "중간")  # 설계서 24장 예제 2
    assert (v["form"], v["msds_form"]) == (MIST, VAP)
