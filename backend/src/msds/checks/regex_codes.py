"""정규식 검사: CAS·H코드·P코드를 원문에서 직접 찾아 모델 결과와 비교 — 역할 C, 2주차 (D-40).

정규식은 투표에 넣지 않고 형식 검사로 쓴다. 정규식이 찾은 코드 목록과 모델 결과가 다르면 사람 검토로 보낸다.
1주차에는 만들지 않아도 된다.
"""
from __future__ import annotations

CAS_PATTERN = r"\b\d{2,7}-\d{2}-\d\b"
H_PATTERN = r"\bH\d{3}[A-Za-z]{0,2}\b|\bEUH\d{3}\b"
P_PATTERN = r"\bP\d{3}(?:\+P\d{3})*\b"


def find_codes(page_texts: dict[int, str]) -> dict[str, set[str]]:
    """{"cas": {...}, "h": {...}, "p": {...}} TODO(C, 2주차)"""
    raise NotImplementedError("TODO(C, 2주차): find_codes")


def compare(doc: dict, found: dict[str, set[str]]) -> list[dict]:
    """모델 결과와 정규식 결과의 차이 목록. TODO(C, 2주차)"""
    raise NotImplementedError("TODO(C, 2주차): compare")
