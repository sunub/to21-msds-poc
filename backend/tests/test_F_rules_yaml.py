"""코드 밖으로 뺀 규칙 파일 시험 (설계서 45장 '엔진 코드에 숫자 기준을 직접 쓰지 않음', 11/02 F).

rules/flam_liquid.yaml, dg_class4.yaml 은 규칙표 v0.3 을 그대로 가져온 것이다. 파일에 적힌 예제(examples)가
엔진에서도 같은 답을 내는지 확인한다.
"""
import pytest
import yaml

from msds.compliance.mixture.params import RULES_DIR
from msds.compliance.mixture.physical import _flam_liquid
from msds.compliance.sec15_judge import _class4


def table(name):
    with open(RULES_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.mark.parametrize("ex", table("flam_liquid.yaml")["examples"], ids=lambda e: e["name"])
def test_flam_liquid_예제(ex):
    p = ex["in"]["props"]
    low, high, status, _ = _flam_liquid({"flash_point": [{"value": p["FLASH_POINT"]}], "boiling": [{"value": p["BOILING"]}]})
    assert (low, high, status) == (ex["out"], ex["out"], "확정")


@pytest.mark.parametrize("ex", table("dg_class4.yaml")["examples"], ids=lambda e: e["name"])
def test_dg_class4_예제(ex):
    p = ex["in"]["props"]
    phys = {"APPEARANCE_STATE": [{"text_value": p["STATE"]}],
            **{code: [{"comp_ref": "MIX", "q": {"value": p[code]}}] for code in ("FLASH_POINT", "BOILING", "AUTOIGNITION")}}
    item, edge = _class4(phys)[:2]
    assert item == ex["out"] and edge is False


def test_규칙_파일에_머리_정보와_반입_기록이_있다():
    for name in ("flam_liquid.yaml", "dg_class4.yaml", "un_class_map.csv"):
        head = (RULES_DIR / name).read_text(encoding="utf-8").splitlines()[:8]
        assert any(l.startswith("# version:") for l in head) and any("저장소 반입" in l for l in head), name
