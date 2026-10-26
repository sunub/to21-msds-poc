"""2차 입력 로더 — 역할 D가 채운다 (TO21 정합성 설계서 v0.2, 1단계).

추출 JSON(TO21 v0.5)에서 2차 엔진이 쓰는 칸만 꺼내 정리한다.
처음에는 data/gold/ 또는 TO21 정답 예제(25번)를 입력으로 쓰고, 추출이 완성되면 runs/의 결과로 경로만 바꾼다 (D-30).

설계서가 정한 2차 입력 칸 (claude/TO21_정합성설계서_검토_20261024.md 4장)
- 최종 개정일(없으면 최초 작성일)
- 3항: 단일/혼합 구분, 유해성분 미함유 표기, 성분 CAS·함유량(Q)·함유량 부가 표기·영업비밀 여부
- 2항: 분류(코드·구분·노출 형태), H코드, 그림문자, 신호어
- 9항: 인화점, 끓는점, 동점도, pH, 성상
- 11항: 독성값(성분·항목·지표·값·노출 형태·노출 시간)
- 12항: 생태독성(성분·지표·값)
- 15항: 규제 행(법령·항목·성분·해당 여부·기준 농도), 위험물(류·품명·수용성·등급)

완료 확인: pytest tests/test_D_compliance.py
"""
from __future__ import annotations


def load_inputs(doc: dict, msds_index: int = 0) -> dict:
    """2차 엔진 입력 묶음을 만든다. TODO(D)

    돌려주는 값 예:
    {
      "doc_id": ..., "as_of_date": 최종 개정일 또는 최초 작성일,
      "composition": {"type": ..., "no_hazardous_component": ...},
      "components": [{"seq", "name", "cas_no", "content": Q, "content_note", "trade_secret"}],
      "hazard": {"classes": [...], "h_codes": [...], "pictograms": [...], "signal_word": ...},
      "physchem": {"FLASH_POINT": Q, ...}, "toxicity": [...], "ecotox": [...],
      "regulations": [...], "dangerous_goods": [...],
      "missing": [2차에 필요한데 비어 있는 칸 경로]
    }
    """
    raise NotImplementedError("TODO(D): load_inputs")
