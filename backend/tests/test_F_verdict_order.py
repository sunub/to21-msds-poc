"""2항 구분 순서 보완 시험 (11/02 F, 실제 HTODB로 silver 전체를 돌려 찾은 빈틈).

규칙표 mixture_rules 에 구분 순서가 없는 항목(물리적 위험성, 표적장기 1회 구분3)에서 MSDS와 우리 구분이 다르면
'위험 순서가 정의되지 않은 구분 → 근거부족'이 나왔다. class_map 결과코드 순서(위험한 구분부터)로 보완한다.
"""
from msds.compliance.mixture.verdict import aggregate_verdicts


def res(cc, low, high=None):
    high = low if high is None else high
    return {"class_code": cc, "form": None, "result": {"low": low, "high": high, "status": "확정" if low == high else "경계"}}


def msds(cc, *cats):
    out = []
    for c in cats:
        cat, _, effect = c.partition(":")
        out.append({"class_code": cc, "category": cat, "route_form": None, "effect": effect or None})
    return out


def one(results, classes):
    rows = aggregate_verdicts(results, classes)["verdicts"]
    assert len(rows) == 1
    return rows[0]


def test_인화성액체는_구분_순서로_과대·과소를_가른다():
    v = one([res("PH_FLAM_LIQ", "2")], msds("PH_FLAM_LIQ", "1"))      # T21-043: MSDS 1, 우리 2
    assert (v["verdict"], v["type"], v["severity"]) == ("불일치", "과대분류", "낮음")
    v = one([res("PH_FLAM_LIQ", "3")], msds("PH_FLAM_LIQ", "4"))      # MSDS가 더 약함
    assert (v["verdict"], v["type"]) == ("불일치", "과소분류")


def test_표적장기_구분3은_앞의_구분으로_순위를_정한다():
    v = one([res("HH_STOT_SE", "2")], msds("HH_STOT_SE", "3:마취"))   # M004: MSDS 3(마취), 우리 2
    assert (v["verdict"], v["type"], v["severity"]) == ("불일치", "과소분류", "높음")


def test_표적장기_구분3_효과_문구만_다르면_일치():
    v = one([res("HH_STOT_SE", "3:마취")], msds("HH_STOT_SE", "3:마취작용", "3:호흡기계 자극"))
    assert v["verdict"] == "일치"
    v = one([res("HH_STOT_SE", "3:호흡기자극")], msds("HH_STOT_SE", "3:마취"))  # 같은 구분3, 다른 효과
    assert (v["verdict"], v["type"], v["severity"]) == ("불일치", "형태·세부 표기", "중간")


def test_고압가스_종류_차이는_세부_표기():
    v = one([res("PH_PRESS_GAS", "압축가스")], msds("PH_PRESS_GAS", "냉동액화가스"))  # S003
    assert (v["verdict"], v["type"], v["severity"]) == ("불일치", "형태·세부 표기", "중간")
