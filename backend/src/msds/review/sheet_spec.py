"""검수표 형식 (D-36). A의 make_sheet·build_gold와 F의 성적표가 함께 쓰는 약속이다.

이 파일의 이름·순서는 바꾸지 않는다. 바꿔야 하면 팀에 공유하고 결정기록에 남긴다.
"""
from __future__ import annotations

# 검수표 열 (엑셀 1행). 순서대로 만든다.
COLUMNS = [
    # 대상 (스크립트)
    "경로",            # align.keyed_flatten 경로. 예: regulations[k=7664-93-9|OSH|OSH_MEASURE||].applicable
    "칸 이름",         # 사람이 읽는 이름. 예: 15항 규제 · 해당 여부 (성분 7664-93-9 / OSH / OSH_MEASURE)
    "우선순위",        # 1 / 2 / 3 (common.priority)
    # 모델 결과 (스크립트)
    "GPT 값",
    "Claude 값",
    "일치",            # 일치 / 불일치 / GPT만 / Claude만
    "GPT 원문 조각",
    "GPT 쪽",
    "Claude 원문 조각",
    "Claude 쪽",
    # 자동 확인 (스크립트)
    "원문 대조",       # 일치 / 불일치 / 대조불가 (checks.source_match)
    "검증기",          # TO21 검증기에서 이 칸에 걸린 규칙. 예: 오류 V01 CAS 체크디지트
    # 모델 설명 (스크립트, 실버 검수 정보)
    "적용 규칙",       # 예: R04, R08
    "설명",
    # 검수 (사람)
    "검수 결과",       # RESULT_OPTIONS 중 하나. 비워 두면 미검수
    "수정값",          # 검수 결과가 '수정'·'누락 추가'일 때. 객체·목록은 JSON으로 적는다
    "수정 원문 조각",
    "수정 쪽",
    "검수자",
    "교차 확인자",
    "메모",
]

RESULT_OPTIONS = ["GPT 채택", "Claude 채택", "수정", "삭제", "누락 추가"]
MATCH_OPTIONS = ["일치", "불일치", "GPT만", "Claude만"]
SOURCE_MATCH_OPTIONS = ["일치", "불일치", "대조불가"]

# 검수표에 넣지 않는 칸
# - 두 모델이 모두 비워 둔 칸(null·빈 목록): '둘 다 없음'은 골드에도 그대로 null로 들어간다.
#   두 모델이 함께 빠뜨린 항목은 '개수 세기'(D-36 순서 3)로 찾아 '누락 추가' 줄을 직접 넣는다.
# - 근거·검증 칸(evidence, validation): 스크립트가 만든다.
EXCLUDED_TOP = {"evidence", "validation"}

# 시트 구성
SHEET_MAIN = "검수"            # COLUMNS 표
SHEET_INFO = "문서 정보"       # 문서 번호, 원본 파일, 쪽수, 검수 시작·끝 시각, 검수자
INFO_FIELDS = ["문서 번호", "원본 파일", "쪽수", "MSDS 순번", "검수 시작", "검수 끝", "검수자", "교차 확인자"]

# 정렬 (D-36 순서): 우선순위 → 일치 여부(불일치·한쪽만 먼저) → 원문 대조 실패 → 검증기 오류 → 경로
MATCH_ORDER = {"불일치": 0, "GPT만": 1, "Claude만": 1, "일치": 2}

# 기본값 모델: 검수 결과를 비워 둔 칸(미검수)에 들어갈 값의 모델.
# 프롬프트를 고정한 뒤 25번 실버를 TO21 정답 예제로 채점해, 점수가 높은 모델로 정해 여기에 적는다 (D-35, 계획서 11장 A).
DEFAULT_MODEL = "gpt"     # "gpt" 또는 "claude"
