"""무독성 성분(물) 시험 (설계서 21장 ATE 수집 5단계, 24장 예제 1·2, D-12).

물은 독성DB나 MSDS 11항에 값이 있어도 급성독성 Σ에 넣지 않고 '이용 가능 성분'으로만 센다.
물을 '자료 없는 성분'으로 세면, 물이 10%를 넘는 수용액에서 공식 2로 넘어가 구분이 뒤집힌다.
"""
import json
from pathlib import Path

import pytest

from msds.compliance.mixture.acute_classify import classify_acute
from msds.compliance.mixture.build_components import build_components
from msds.compliance.mixture.params import param_list

SILVER = Path(__file__).resolve().parents[2] / "data" / "silver" / "claude" / "T21-025.json"
WATER = "7732-18-5"


def comp(name, pct, cas, **kw):
    return {"cas": cas, "name": name, "content": {"low": pct, "high": pct}, "non_toxic": False,
            "db": [], "classes": [], "msds": [], **kw}


def mist(results):
    return next(r for r in results if r["class_code"] == "HH_ACUTE_INHAL" and r.get("form") == "분진·미스트")


def test_물은_무독성_목록에_있다():
    assert WATER in param_list("non_toxic_cas")


def test_물_70퍼센트_수용액_흡입_구분이_뒤집히지_않는다():
    acid = comp("황산", 30, "7664-93-9", db=[{"route": "inhal", "form": "mist", "op": "=", "value": 0.375, "unit": "mg/L"}])
    # 물을 무독성으로 볼 때: 공식 1, 100 / (30 / 0.375) = 1.25 → 구분 4
    good = mist(classify_acute([acid, comp("물", 70, WATER, non_toxic=True)], "액체"))
    assert good["result"]["low"] == "4" and good["calc"]["formula_used"] == "공식1"
    # 물을 자료 없는 성분으로 셀 때(이전 동작): 70% > 10% → 공식 2, (100 - 70) / 80 = 0.375 → 구분 2
    bad = mist(classify_acute([acid, comp("물", 70, WATER)], "액체"))
    assert bad["result"]["low"] == "2" and bad["calc"]["formula_used"] == "공식2"


@pytest.mark.skipif(not SILVER.exists(), reason="T21-025.json 없음")
def test_build_components는_물만_무독성으로_표시한다():
    item = json.loads(SILVER.read_text(encoding="utf-8"))["msds"][0]
    by = {c["cas"]: c for c in build_components(item, lambda cas: [])["components"]}
    assert by[WATER]["non_toxic"] is True and by["7664-93-9"]["non_toxic"] is False
