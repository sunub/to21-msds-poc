"""함량 범위 처리 시험 (설계서 26장 표)."""
import pytest

from msds.common.models import Component
from msds.compliance.mixture.acute_classify import classify_acute
from msds.compliance.mixture.ranges import content_range, with_ranges


def comp(seq=1, *, value=None, lower=None, lower_op=None, upper=None, upper_op=None, unit="%",
         note=None, secret=False, cas="1-1-1", content=True):
    q = {"raw": "x", "status": "값있음", "value": value, "lower": lower, "lower_op": lower_op,
         "upper": upper, "upper_op": upper_op, "unit": unit}
    return Component.model_validate({"seq": seq, "name": f"C{seq}", "cas_no": cas, "content": q if content else None,
                                     "content_note": note, "trade_secret": secret})


def rng(lo, hi, seq=1):
    return comp(seq, lower=lo, lower_op=">=", upper=hi, upper_op="<=")


def lh(r):
    return r["low"], r["high"]


def test_범위와_단일값():
    r = content_range([rng(93, 98, 1), rng(2, 7, 2)])
    assert [lh(x) for x in r] == [(93, 98), (2, 7)]
    assert lh(content_range([comp(value=5)])[0]) == (5, 5)


def test_이상은_100에서_다른_하한을_뺌():
    r = content_range([comp(1, lower=10, lower_op=">="), rng(20, 30, 2), comp(3, value=5)])
    assert lh(r[0]) == (10, 75)
    assert "상한 계산(100−다른 성분 하한)" in r[0]["flags"]


def test_이상_cap_100():
    assert lh(content_range([comp(lower=95, lower_op=">=")])[0]) == (95, 100)


def test_이상이_다른_성분과_100_초과():
    r = content_range([comp(1, lower=50, lower_op=">="), rng(60, 70, 2)])
    assert lh(r[0]) == (50, 50) and "합계 100 초과" in r[0]["flags"]
    assert lh(r[1]) == (60, 70)  # 계산은 막지 않는다


def test_미만():
    r = content_range([comp(upper=1, upper_op="<")])[0]
    assert (r["low"], r["high"], r["high_exclusive"]) == (0, 1, True)


def test_영업비밀_범위():
    r = content_range([comp(lower=10, lower_op=">=", upper=30, upper_op="<=", secret=True, cas=None)])[0]
    assert lh(r) == (10, 30) and "영업비밀" in r["flags"]


@pytest.mark.parametrize("note", ["미검출", "극미량"])
def test_극미량(note):
    r = content_range([comp(content=False, note=note)])[0]
    assert lh(r) == (0, 0.1) and "극미량(가정)" in r["flags"]


def test_함량_없음():
    r = content_range([comp(content=False)])[0]
    assert lh(r) == (None, None) and r["flags"] == ["함량 없음"]


def test_단위():
    assert "단위 참고(vol%)" in content_range([comp(value=5, unit="vol%")])[0]["flags"]
    r = content_range([comp(value=500, unit="ppm")])[0]
    assert lh(r) == (None, None) and "단위 미지원(ppm)" in r["flags"]


def test_하한_상한만_있는_이하는_지원하지_않음():
    r = content_range([comp(upper=1, upper_op="<=")])[0]
    assert lh(r) == (None, None) and "표기 미지원(상한만, 이하)" in r["flags"]


def test_with_ranges로_황산_분류():
    sul = {**rng(93, 98, 1).model_dump(), "db": [{"route": "inhal", "form": "mist", "value": 0.375, "unit": "mg/L",
                                                  "op": "=", "hours": 4}], "classes": [], "msds": []}
    water = {**rng(2, 7, 2).model_dump(), "non_toxic": True, "db": [], "classes": [], "msds": []}
    comps = with_ranges([sul, water])
    assert comps[0]["content"] == {"low": 93, "high": 98} and comps[0]["content_flags"] == []
    mist = next(r for r in classify_acute(comps, "액체") if r["form"] == "분진·미스트")
    assert mist["result"] == {"low": "2", "high": "2", "status": "확정"}
