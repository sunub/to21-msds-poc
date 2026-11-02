"""물리적 위험성 보완 시험 (설계서 31·33장, D-17, 미결 6 · 11/02 F 수정).

실제 HTODB로 silver 전체를 돌려 보니 두 가지로 물리적 위험성이 통째로 근거부족이 되었다.
- 대표성분: 함량 최대 성분을 분류와 상관없이 골라 물(T21-023 염산 20%)이나 CAS 없는 'Other ingredient'(T21-006)가 뽑혔다.
  설계서 52장 미결 6의 현재 가정('분류 있는 성분 중 함량 최대')대로 고친다.
- 인화성 액체 9항 단계: 규칙표 flam_liquid.yaml 이 저장소에 없다며 계산하지 않았다. 규칙표 v0.3 값을 옮긴다.
"""
import pytest

from msds.compliance.mixture.physical import _flam_liquid, _representative


def comp(name, high, classes=()):
    return {"name": name, "high": high, "class_rows": list(classes)}


def test_대표성분은_분류가_있는_성분_중_함량_최대():
    water, hcl = comp("물", 80.5), comp("염산", 20.5, [{"class_code": "PH_METAL_CORR"}])
    assert _representative([hcl, water])["name"] == "염산"
    assert _representative([water, comp("기타", 60)])["name"] == "물"  # 분류 있는 성분이 없으면 함량 최대


def phys(fp=None, bp=None, status=None):
    return {"flash_point": [{"value": fp, "status": status or ("값있음" if fp is not None else "자료없음")}],
            "boiling": [{"value": bp}] if bp is not None else []}


@pytest.mark.parametrize("fp, bp, cat", [(22, 30, "1"), (22, 80, "2"), (47, None, "3"), (61, 150, "4"), (100, 200, "분류안됨")])
def test_인화성액체_9항_단계는_flam_liquid_yaml_기준(fp, bp, cat):  # yaml examples + T21-006(인화점 47)
    low, high, status, _ = _flam_liquid(phys(fp, bp))
    assert (low, high, status) == (cat, cat, "확정")


def test_인화점_자료없음은_근거부족_불연성은_분류안됨():
    assert _flam_liquid(phys(status="자료없음"))[2] == "근거부족"
    assert _flam_liquid(phys(status="해당없음(불연성)"))[:3] == ("분류안됨", "분류안됨", "확정")
    assert _flam_liquid(phys(10))[:3] == ("2", "1", "경계")  # 초기끓는점이 없으면 1·2 사이


# ── 11/02 F 결정 12: UN(운송 규제)이 없는 제품 ─────────────────────────────
from msds.compliance.mixture.physical import classify_physical  # noqa: E402
from msds.compliance.mixture.rules_loader import load_mixture_rules  # noqa: E402


def _run(item_id, fp=None, status=None, transport=()):
    rules = load_mixture_rules()
    ethanol = comp("에탄올", 5, [{"class_code": "PH_FLAM_LIQ", "category": "2", "source": "KR02"}])
    physical = {"transport": list(transport), "msds_classes": [], **phys(fp, None, status)}
    return classify_physical(item_id, rules["classes"][item_id], [ethanol, comp("물", 95)], {"STATE": "액체"}, physical,
                             rules=rules)


def test_결정12_UN이_없어도_인화성_액체는_9항_인화점으로_판정():
    r = _run("PH_FLAM_LIQ", fp=47)
    assert (r["result"]["low"], r["result"]["status"], r["rule"]["id"]) == ("3", "확정", "PHY-FLQ")
    assert any("결정 12" in a for a in r["assumptions"])
    r = _run("PH_FLAM_LIQ", fp=100)  # 에탄올 5% 수용액처럼 인화점이 높으면 대표성분(에탄올 구분2)을 쓰지 않고 분류안됨
    assert r["result"]["low"] == "분류안됨"


def test_결정12_인화점도_없거나_다른_항목이면_전처럼_판정_대상_아님():
    r = _run("PH_FLAM_LIQ", status="자료없음")
    assert (r["result"]["status"], r["rule"]["id"]) == ("해당 없음", "PHY-UN")
    r = _run("PH_OXID_LIQ", fp=47)
    assert r["result"]["status"] == "해당 없음"
