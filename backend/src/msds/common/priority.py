"""칸별 우선순위 (결정기록 D-32).

1순위: 합격 관문(필수 17개) + CAS·성분 + 2차가 쓰는 비채점 칸
2순위: 2차가 쓰는 중요 항목 (9항 기타 물성, 11항 급성 외 독성, 12항 생태독성)
3순위: 11항 CMR, 15항 해외 규제, 서술형, 그 밖의 칸

목록 항목의 순위는 항목 내용(물성 코드, 독성 지표, 법령)에 따라 달라지므로
align.keyed_flatten이 만든 '키가 든 경로'로 판단한다.
"""
from __future__ import annotations

from .align import generic

# TO21 채점기와 같은 정의
MUST_PHYSCHEM = {"APPEARANCE_STATE", "PH", "BOILING", "FLASH_POINT", "UEL", "LEL",
                 "VAPOR_PRESSURE", "RELATIVE_DENSITY", "AUTOIGNITION"}
ACUTE = {"TX_ORAL", "TX_DERMAL", "TX_INHAL"}
DOMESTIC_LAWS = {"OSH", "KREACH", "CCA", "DG", "WASTE"}

_P1_TOP = {"meta", "product", "companies", "hazard", "composition", "components",
           "exposure_limits", "transport", "dangerous_goods"}


def _key_of(path: str, list_name: str) -> list[str]:
    """경로에서 list_name[k=...]의 키 부분을 꺼낸다."""
    start = path.find(f"{list_name}[k=")
    if start < 0:
        return []
    s = path[start + len(list_name) + 3:]
    s = s[: s.find("]")]
    return s.split("#")[0].split("|")


def priority_of(keyed_path: str) -> int:
    top = generic(keyed_path).split(".")[0].split("[")[0]
    if top in _P1_TOP:
        return 1
    if top == "physchem":
        k = _key_of(keyed_path, "physchem")
        return 1 if len(k) > 1 and k[1] in MUST_PHYSCHEM else 2
    if top == "toxicity":
        k = _key_of(keyed_path, "toxicity")
        return 1 if len(k) > 1 and k[1] in ACUTE else 2
    if top == "ecotox":
        return 2
    if top == "regulations":
        k = _key_of(keyed_path, "regulations")
        return 1 if len(k) > 1 and k[1] in DOMESTIC_LAWS else 3
    return 3   # cmr, intl_class, waste, narratives, extras 등
