"""검수표 → 골드 JSON — 역할 A가 채운다 (D-33, D-36).

사람은 JSON을 고치지 않는다. 검수표만 고치고, 골드는 이 스크립트가 만든다.
같은 검수표로 다시 돌리면 같은 골드가 나와야 한다.

이미 있는 도구
- common.align.unflatten_keyed(pairs)  키 경로와 값 목록 → msds 항목
- common.jsonpath.from_cell(text)      사람이 적은 수정값 → 값 (JSON이면 JSON)
- common.schema.validate_to21(doc)     TO21 스키마 검증
- checks.validator.run_to21_validator  TO21 검증기

완료 확인: pytest tests/test_A_review.py
"""
from __future__ import annotations

from pathlib import Path

from .sheet_spec import DEFAULT_MODEL, RESULT_OPTIONS  # noqa: F401


def read_sheet(path: Path) -> tuple[list[dict], dict]:
    """검수표를 읽어 (행 목록, 문서 정보)를 돌려준다. TODO(A)"""
    raise NotImplementedError("TODO(A): read_sheet")


def build_gold(rows: list[dict], base_doc: dict) -> tuple[dict, list[str]]:
    """행 목록으로 골드 문서를 만든다. 돌려주는 값: (골드 문서, 미검수 칸 경로 목록)

    해야 할 일 (TODO A)
    1. 행마다 최종 값을 정한다.
       GPT 채택 → GPT 값 / Claude 채택 → Claude 값 / 수정·누락 추가 → from_cell(수정값) / 삭제 → 칸을 넣지 않음
       비워 둠(미검수) → DEFAULT_MODEL의 값을 넣고 미검수 목록에 경로를 추가 (D-35)
    2. MSDS 건마다 (키 경로, 값) 목록을 모아 unflatten_keyed로 msds 항목을 만든다.
       검수표에 없는 칸(두 모델 모두 빈 칸)은 base_doc 구조에서 null로 채워 TO21 형식을 맞춘다.
       가장 쉬운 방법: base_doc(기본값 모델의 실버)의 msds 항목을 keyed_flatten한 목록에서 시작해,
       행의 결정으로 값을 덮어쓰고(삭제는 빼고, 누락 추가·한쪽에만 있던 항목은 더하고) unflatten_keyed 한다.
       목록 항목 하나를 통째로 삭제할 때는 그 항목 아래 경로를 모두 뺀다.
    3. 근거(evidence): 행마다 채택한 쪽의 원문 조각·쪽(수정이면 수정 원문 조각·쪽)으로 만든다.
       method="수기", needs_review=False, confidence=None, bbox=None (D-36).
       목록 항목은 항목 단위 field(예: components[0])로 하나만 남긴다. field는 번호 경로로 바꿔 적는다.
    4. doc 칸은 base_doc의 doc을 쓰고 extraction.engine="manual(gold)"로 바꾼다.
    5. validate_to21과 run_to21_validator를 돌려 '오류'가 0건인지 확인한다.
    """
    raise NotImplementedError("TODO(A): build_gold")


def build_gold_file(doc_id: str) -> Path:
    """data/review/<문서>.xlsx → data/gold/<문서>.json (+ <문서>.unreviewed.json). TODO(A)"""
    raise NotImplementedError("TODO(A): build_gold_file")
