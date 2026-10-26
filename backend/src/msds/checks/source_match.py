"""원문 대조 — 역할 C가 채운다 (D-14, D-33, D-36).

모델이 적은 원문 조각이 실제 문서(해당 쪽 텍스트층)에 있는지 확인한다.
모델이 근거를 지어냈는지 걸러 내는 장치다. 검수표(A)와 2주차 다수결(D-38)이 이 결과를 쓴다.

완료 확인: pytest tests/test_C_checks.py
"""
from __future__ import annotations

import re
import unicodedata

_EXTRA = str.maketrans({"‐": "-", "–": "-", "—": "-", "−": "-", "〜": "~"})   # NFKC가 바꾸지 않는 줄표·물결


def normalize(text: str) -> str:
    """비교용으로 글자를 맞춘다.

    - 공백·줄바꿈을 모두 지운다 (표에서 꺼낸 글자는 줄이 끊겨 있다)
    - 전각·반각 기호를 맞춘다 (예: '（' → '(', '～' → '~', '－' → '-')
    - 표 칸 구분으로 모델이 넣은 ' | '는 지운다
    대소문자는 바꾸지 않는다 (D-9).
    """
    s = unicodedata.normalize("NFKC", text or "")
    s = s.translate(_EXTRA)
    s = s.replace("|", "")
    return re.sub(r"\s+", "", s)


def match(source_text: str | None, page: int | None, page_texts: dict[int, str],
          page_states: dict[int, str]) -> dict:
    """원문 조각을 문서에서 찾는다.

    돌려주는 값: {"result": "일치" | "불일치" | "대조불가", "found_page": int | None, "reason": str}

    규칙
    - source_text가 비어 있으면 "대조불가" (reason: 원문 조각 없음)
    - page 쪽의 텍스트층 상태(page_states)가 '정상'이 아니면 "대조불가" (텍스트층을 믿을 수 없음)
    - 정규화한 조각이 정규화한 해당 쪽 텍스트에 들어 있으면 "일치", found_page=page
    - 해당 쪽에 없으면 다른 쪽도 찾아본다. 다른 쪽에 있으면 "일치"이고 found_page는 그 쪽 (reason에 쪽 번호가 다름을 적는다)
    - 표에서 읽은 조각은 칸 순서가 텍스트층과 다를 수 있다. ' | '로 나뉜 조각은 조각마다 같은 쪽에 모두 있으면 "일치"로 본다
    - 어디에도 없으면 "불일치"
    """
    if source_text is None or not str(source_text).strip():
        return {"result": "대조불가", "found_page": None, "reason": "원문 조각 없음"}
    if page is not None and page_states.get(page, "정상") != "정상":
        return {"result": "대조불가", "found_page": None, "reason": f"{page}쪽 텍스트층 {page_states.get(page)}"}
    pieces = [p for p in (normalize(x) for x in str(source_text).split("|")) if p]
    whole = "".join(pieces)
    usable = {p: normalize(t) for p, t in page_texts.items() if page_states.get(p, "정상") == "정상"}

    def found(t: str) -> bool:
        return whole in t or (len(pieces) > 1 and all(x in t for x in pieces))

    order = ([page] if page in usable else []) + [p for p in sorted(usable) if p != page]
    for p in order:
        if found(usable[p]):
            return {"result": "일치", "found_page": p, "reason": "" if p == page else f"적힌 쪽 {page}, 찾은 쪽 {p}"}
    return {"result": "불일치", "found_page": None, "reason": "문서 텍스트층에서 찾지 못함"}
