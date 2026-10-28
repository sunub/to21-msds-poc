"""성적표 — 역할 F가 채운다 (D-1, D-13).

TO21 채점기의 score()를 문서마다 돌려 평균을 내고, 결정 D-13의 형식으로 정리한다.
공식 점수는 TO21 채점기 그대로다. 우리 집계는 그 위에 '왜 틀렸는지'를 보여 주는 용도다.

이미 있는 도구
- checks.validator.load_to21_module("scorer")  TO21 채점기 모듈 (score 함수)
  score(gold_doc, pred_doc) → [(레벨, 항목, 지표, 점수, 비교 수, 목표)], 그리고 score.details에 필수 항목 오류 상세
- paths.gold_path / gold_unreviewed_path / silver_path / run_dir

완료 확인: pytest tests/test_F_score.py
"""
from __future__ import annotations

from pathlib import Path

WEIGHTS = {"필수": 3, "중요": 2, "일반": 1}


def score_pair(gold: dict, pred: dict) -> dict:
    """문서 한 건 채점.

    돌려주는 값 (TODO F)
    {
      "items": [{"level", "name", "metric", "score", "n", "target", "pass"}],   # TO21 채점기 23개 항목
      "weighted": 가중 종합 점수(0~100),
      "must_pass": 필수 17개가 모두 목표 이상인지,
      "details": [(항목, 종류, 내용)]   # 채점기의 필수 항목 누락·오추출·불일치 상세
    }
    """
    raise NotImplementedError("TODO(F): score_pair")


def score_set(pairs: list[tuple[str, dict, dict]]) -> dict:
    """여러 문서 채점. pairs = [(문서번호, 골드, 결과)]

    TODO(F)
    - 항목별 점수는 문서 평균 (TO21 채점기 설명과 같다)
    - 가중 종합 점수와 합격 판정: 필수 17개 모두 목표 이상 + 종합 90점 이상
    - D-13 집계: 상세 목록의 누락 → 빠뜨림, 오추출 → 지어냄, 불일치 → 틀림으로 세어 항목별로 보여 준다
      (목록에서 값이 틀린 항목은 채점기가 '누락 1 + 오추출 1'로 세므로, 그 점을 표에 각주로 단다)
    - 미검수 칸(gold_unreviewed_path)이 들어간 항목은 '참고'로 표시한다 (D-35)
    """
    raise NotImplementedError("TODO(F): score_set")


def write_report(result: dict, out_dir: Path, title: str) -> Path:
    """성적표를 파일로 저장 (CSV + 사람이 읽는 markdown). TODO(F)

    - 표 1: 필수 17개 항목별 점수·목표·통과 (결과별 열: 기준선, GPT 실버, Claude 실버)
    - 표 2: 가중 종합 점수, 합격 판정
    - 표 3: 빠뜨림·지어냄·틀림 개수 (D-13)
    - 25번은 TO21 정답 예제 기준 점수를 따로 적는다 (계획서 15장)
    - 실버 점수 옆에는 '참고값(정답이 실버에서 출발)'을 적는다
    """
    raise NotImplementedError("TODO(F): write_report")
