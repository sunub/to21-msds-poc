"""함량이 없는 성분의 급성독성 처리: 계산에 쓰이는 성분이면 근거부족, 아니면 무시."""
import pytest

from msds.common.models import Component
from msds.compliance.mixture.acute import mix_acute
from msds.compliance.mixture.acute_classify import classify_acute
from msds.compliance.mixture.ranges import with_ranges

NONE = {"low": None, "high": None}


def row(route="oral", value=100, op="=", unit="mg/kg", form=None, **kw):
    return {"route": route, "form": form, "value": value, "unit": unit, "op": op, **kw}


def comp(name, content, cas=None, **kw):
    return {"name": name, "cas": cas, "content": content, "non_toxic": False, "db": [], "classes": [], "msds": [], **kw}


def sulfuric(sul=None, water=None):
    s = comp("황산", sul if sul is not None else {"low": 93, "high": 98}, "7664-93-9",
             db=[row(value=2140), row("inhal", 0.375, unit="mg/L", form="mist", hours=4)])
    return [s, comp("물", water if water is not None else {"low": 2, "high": 7}, "7732-18-5", non_toxic=True)]


def pick(res, code, form=None):
    return next(r for r in res if r["class_code"] == code and r["form"] == form)


def mist(comps):
    return pick(classify_acute(comps, "액체"), "HH_ACUTE_INHAL", "분진·미스트")


@pytest.mark.parametrize("content", [NONE, None, {"low": None, "high": 98}, {"low": 93, "high": None}])
def test_황산_함량_없음은_근거부족(content):
    comps = sulfuric()
    comps[0]["content"] = content
    res = classify_acute(comps, "액체")
    for r in (pick(res, "HH_ACUTE_ORAL"), pick(res, "HH_ACUTE_INHAL", "분진·미스트")):
        assert r["result"] == {"low": None, "high": None, "status": "근거부족"}
        assert r["thresholds"] == []
        assert r["calc"]["ate_mix_low"] is None and r["calc"]["sum_high"] is None
        sul = r["inputs"][0]
        assert sul["excluded"] == "함량 없음" and "함량 없음" in sul["flags"]
        assert "ate_used" not in sul


def test_황산_content_칸이_없어도_같다():
    comps = sulfuric()
    del comps[0]["content"]
    assert mist(comps)["result"]["status"] == "근거부족"


def test_mix_acute_근거부족_구조():
    comps = [{"name": "A", "cas": None, "content": None, "ate": {"kind": "value", "value": 100, "src": "s", "step": 1}}]
    r = mix_acute(comps, "oral")
    assert (r["status"], r["reason"]) == ("근거부족", "함량 없음")
    assert r["low"]["category"] is None and r["high"]["ate_mix"] is None and r["low"]["sigma"] is None
    assert r["terms"][0]["사용여부"] == {"low": "함량없음", "high": "함량없음"}


def test_물_함량_없음은_정상_결과():
    r = mist(sulfuric(water=NONE))
    assert r["result"] == {"low": "2", "high": "2", "status": "확정"}
    assert r["calc"]["ate_mix_low"] == pytest.approx(mist(sulfuric())["calc"]["ate_mix_low"])
    assert r["inputs"][1]["excluded"] == "무독성"


def test_부등호_성분_함량_없음은_영향_없음():
    comps = sulfuric()
    comps.append(comp("부등호", NONE, db=[row("inhal", 5, op=">", unit="mg/L", form="mist")]))
    r = mist(comps)
    assert r["result"] == {"low": "2", "high": "2", "status": "확정"}
    assert r["inputs"][2]["excluded"] == "부등호 값"


def test_자료없음_성분_함량_없음도_근거부족():
    comps = sulfuric()
    comps.append(comp("미상", NONE))
    assert mist(comps)["result"]["status"] == "근거부족"


def test_with_ranges의_함량없음을_그대로_넣어도_죽지_않음():
    sul = Component.model_validate({"seq": 1, "name": "황산", "cas_no": "7664-93-9", "content": None}).model_dump()
    sul.update(db=[row(value=2140)], classes=[], msds=[], non_toxic=False)
    comps = with_ranges([sul])
    assert comps[0]["content"] == NONE
    r = pick(classify_acute(comps, "액체"), "HH_ACUTE_ORAL")
    assert r["result"]["status"] == "근거부족"
    assert r["inputs"][0]["flags"].count("함량 없음") == 1


def test_결정론():
    comps = sulfuric(sul=NONE)
    assert classify_acute(comps, "액체") == classify_acute(comps, "액체")
