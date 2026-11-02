"""제품 성상 → 흡입 형태 선택 시험 (설계서 D-06·D-22, 11/02 F 수정).

실제 HTODB로 silver 전체를 돌려 보니, 가스 제품(M002 천연가스)과 '액상'으로 적은 액체 제품(T21-039)에서
흡입 형태 셋(가스·증기·분진/미스트)을 모두 계산해 성상에 맞지 않는 줄이 판정에 섞였다.
"""
import pytest

from msds.compliance.mixture.ate_source import inhal_forms
from msds.compliance.mixture.build_components import _state


def item(*texts):
    return {"physchem": [{"prop_code": "APPEARANCE_STATE", "comp_ref": "MIX", "text_value": t} for t in texts]}


@pytest.mark.parametrize("text, state", [("액체", "액체"), ("액상", "액체"), ("기체", "가스"), ("액체가스", "가스"),
                                         ("고체(분말)", "고체"), ("분말", "고체")])
def test_성상_표기를_규칙표_값으로_맞춘다(text, state):
    assert _state(item(text), []) == state


def test_가스_제품은_가스_형태만_계산한다():
    assert inhal_forms("가스") == inhal_forms("기체") == ["gas"]
    assert inhal_forms("액체") == ["vapour", "mist"]
