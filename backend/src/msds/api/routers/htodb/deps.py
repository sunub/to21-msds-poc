"""지식DB 라우터들이 함께 쓰는 접속 풀·버전·13_TO21DB매핑과 응답 감싸기.

state는 htodb_app의 lifespan이 채운다: pool(읽기 전용 접속 풀), versions(적재 버전), map(Map13).
"""

from __future__ import annotations

state: dict = {}


def wrap(data) -> dict:
    """모든 응답에 적재 버전을 붙인다."""
    return {**state["versions"], "data": data}


def conn():
    return state["pool"].connection()
