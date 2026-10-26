"""지식 제공자 인터페이스 — 역할 D (TO21 정합성 설계서 v0.2, 2단계).

판정에 쓰는 기준 정보(기준 분류, ATE, 규제)를 함수 3개로만 꺼낸다.
PoC에서는 TO21 엑셀을 적재한 DB가 이 함수를 구현하고, 운영에서는 TO21 API로 바꾼다.
TO21 지식DB 엑셀이 오기 전이라 1주차에는 입출력 형태만 정한다.
"""
from __future__ import annotations

from typing import Protocol


class KnowledgeProvider(Protocol):
    knowledge_version: str   # 응답마다 지식 버전을 남긴다 (설계서 메시지 명세)

    def get_reference(self, cas_no: str, as_of: str) -> dict:
        """성분의 기준 정보: 기준 분류, ATE, 노출기준, UN번호 등. 입력: CAS, 기준일"""
        ...

    def classify_mixture(self, components: list[dict], as_of: str) -> dict:
        """혼합물 분류 계산에 필요한 기준값 묶음 (한계농도, 가산 규칙 등)"""
        ...

    def get_regulation(self, cas_no: str, as_of: str) -> list[dict]:
        """15항 국내 규제: 법령·항목·기준 농도. 입력: CAS, 기준일"""
        ...


class EmptyProvider:
    """데이터가 오기 전 개발용. 모든 조회에 '근거부족'이 나오도록 빈 값을 돌려준다."""
    knowledge_version = "empty-0"

    def get_reference(self, cas_no: str, as_of: str) -> dict:
        return {}

    def classify_mixture(self, components: list[dict], as_of: str) -> dict:
        return {}

    def get_regulation(self, cas_no: str, as_of: str) -> list[dict]:
        return []
