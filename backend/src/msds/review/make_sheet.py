"""검수표 만들기 — 역할 A가 채운다 (D-36).

입력: GPT 실버, Claude 실버, 각 실버의 검수 정보, 쪽 텍스트층, TO21 검증기 결과
출력: data/review/<문서번호>.xlsx  (형식은 sheet_spec.py)

이미 있는 도구 (그대로 쓴다)
- common.align.keyed_flatten(msds_item)   칸 단위로 펼치되 목록은 '무엇인지'로 짝지은 경로
- common.align.item_path_map / to_keyed   근거의 번호 경로 → 키 경로
- common.align.generic(path)              번호·키를 지운 경로 (칸 이름표 만들 때)
- common.priority.priority_of(path)       1·2·3순위
- common.jsonpath.to_cell(value)          엑셀 칸에 넣을 글자
- checks.source_match.match(...)          원문 대조 (C가 만든다)
- checks.validator.run_to21_validator(doc) TO21 검증기

완료 확인: pytest tests/test_A_review.py
"""
from __future__ import annotations

from pathlib import Path

from .sheet_spec import COLUMNS, EXCLUDED_TOP, INFO_FIELDS, RESULT_OPTIONS  # noqa: F401


def build_rows(gpt_doc: dict, claude_doc: dict,
               gpt_review: list[dict], claude_review: list[dict],
               page_texts: dict[int, str], validator_results: dict[str, list[dict]]) -> list[dict]:
    """검수표의 행 목록을 만든다. 행은 COLUMNS를 키로 가진 dict.

    해야 할 일 (TODO A)
    1. MSDS 건마다(msds[i]) keyed_flatten으로 두 모델을 펼친다. 경로 앞에 'msds[i].'를 붙인다.
       두 모델의 MSDS 건수가 다르면 메모에 적고 앞에서부터 맞춘다.
    2. 두 모델의 경로를 합친다(합집합). 경로마다 GPT 값, Claude 값을 넣는다.
       - 최상위가 EXCLUDED_TOP(evidence, validation)인 칸은 뺀다.
       - 두 값이 모두 비어 있으면(None, [], {}) 행을 만들지 않는다 (sheet_spec 설명 참고).
    3. 일치: 같으면 '일치', 다르면 '불일치', 한쪽에만 경로가 있으면 'GPT만'/'Claude만'.
       비교 기준은 결정 D-9: 글 칸은 공백 차이만 무시, 코드·숫자는 한 글자라도 다르면 불일치.
    4. 원문 조각·쪽: 각 모델의 검수 정보(review)에서 field를 to_keyed로 바꿔
       그 행 또는 그 행이 속한 항목(가장 긴 앞부분이 맞는 것)의 조각·쪽·규칙·설명을 넣는다.
    5. 원문 대조: 원문 조각이 있으면 checks.source_match.match로 확인해 결과를 넣는다.
    6. 검증기: validator_results[모델]에서 같은 칸(또는 같은 항목)에 걸린 오류·경고를 적는다.
    7. 우선순위: priority_of(경로).  칸 이름: generic(경로)를 사람이 읽기 쉽게 (필드 정의의 한글 이름 활용 가능).
    8. 정렬: sheet_spec.MATCH_ORDER와 D-36 순서(우선순위 → 불일치 → 원문 대조 실패 → 검증기 오류).
    """
    raise NotImplementedError("TODO(A): build_rows")


def write_sheet(rows: list[dict], info: dict, path: Path) -> None:
    """엑셀로 저장한다.

    해야 할 일 (TODO A)
    - 시트 '검수'에 COLUMNS 순서로 머리글과 행을 쓴다. 머리글 고정(freeze), 자동 필터.
    - '검수 결과' 열에 RESULT_OPTIONS 드롭다운(데이터 유효성 검사).
    - 시트 '문서 정보'에 INFO_FIELDS와 info 값(검수 시작·끝은 비워 둔다).
    - 사람이 쓰는 열(검수 결과 ~ 메모)은 배경색으로 구분하면 검수하기 쉽다.
    """
    raise NotImplementedError("TODO(A): write_sheet")


def make_review_sheet(doc_id: str) -> Path:
    """한 문서의 검수표를 만든다: 실버·검수 정보·쪽 텍스트를 읽고 build_rows → write_sheet.

    TODO(A): paths.silver_path / silver_review_path / page_txt / review_sheet_path 를 써서 구현
    """
    raise NotImplementedError("TODO(A): make_review_sheet")
