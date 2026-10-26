"""단일물질/혼합물 판별기 — 역할 D가 채운다 (TO21 정합성 설계서 v0.2, 1단계).

판별 결과에 따라 2항 검증 경로가 갈린다.
- 단일물질: 기준 분류(환경부 → 고용노동부 순)와 비교
- 혼합물: 성분 정보로 계산 (ATEmix, 가산법, 한계농도 등 — 2주차 이후)
"""
from __future__ import annotations


def product_type(inputs: dict) -> dict:
    """{"type": "단일물질" | "혼합물" | "판단불가", "basis": 판단 근거 문장}  TODO(D)

    판단 순서 (설계서 기준으로 D가 확정)
    1. composition.type이 적혀 있으면 그 값
    2. 없으면 성분 수와 함유량으로 판단 (예: 성분 1개, 함유량 하한 ≥ 80 이면 단일물질 후보)
    3. 판단할 수 없으면 '판단불가'로 두고 근거부족 판정으로 넘긴다
    """
    raise NotImplementedError("TODO(D): product_type")
