---
name: 화학 안전문서 AI 결과 검토
description: 결론을 먼저 읽고 원문과 다음 시험으로 이어가는 작업 화면
colors:
  # 본문과 보조 글
  ink: "#23332f"
  muted: "#53645e"
  # 바탕과 구분선
  paper: "#ffffff"
  ground: "#f4f6f3"
  line: "#cbd4ce"
  soft: "#eaf0eb"
  context: "#edf2ed"
  # 행동과 초점
  accent: "#245e50"
  accent-hover: "#194a3e"
  input-line: "#8c9e93"
  # 선택한 원문 근거
  selected: "#fff3c6"
  selected-line: "#887029"
  # 확인된 실패 전용
  failure: "#a52f35"
  failure-bg: "#fff3f2"
  # 브라우저와 점수 막대
  scale-track: "#e4eae4"
  selection: "#d8e8dd"
  scrollbar: "#94a49b"
typography:
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif'
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontSize: "14px"
    lineHeight: 1.5
  app-name:
    fontSize: "18px"
    fontWeight: 750
  headline:
    fontSize: "28px"
    fontWeight: 700
    lineHeight: 1.35
    letterSpacing: "-0.02em"
  title:
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.35
  subsection:
    fontSize: "16px"
    fontWeight: 700
    lineHeight: 1.35
  score:
    fontSize: "48px"
    fontWeight: 750
    lineHeight: 1.15
  score-unit:
    fontSize: "20px"
    fontWeight: 500
  value:
    fontSize: "28px"
    fontWeight: 750
  code:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace"
    fontSize: "13px"
rounded:
  control: "4px"
  panel: "6px"
spacing:
  tight: "4px"
  field: "6px"
  small: "8px"
  control-y: "10px"
  compact: "12px"
  group: "16px"
  section-small: "20px"
  section: "24px"
  page-x: "28px"
  page: "32px"
  wide-page-x: "40px"
# 사용자 지정 경계선 토큰. 표준 스키마의 명시적 확장.
borders:
  standard: "1px solid #cbd4ce"
  selected: "1px solid #23332f"
  evidence: "1px solid #887029"
  input: "1px solid #8c9e93"
  failure: "1px solid #a52f35"
  focus: "3px solid #245e50"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
  context-bar:
    backgroundColor: "{colors.context}"
    typography: "{typography.label}"
    padding: "12px 24px"
  panel:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.panel}"
    padding: "24px"
  evidence:
    backgroundColor: "{colors.selected}"
    padding: "12px"
  guide-band:
    backgroundColor: "{colors.soft}"
    padding: "16px 20px"
  state-failure:
    backgroundColor: "{colors.failure-bg}"
    rounded: "{rounded.panel}"
    padding: "24px"
---

# 결론을 먼저 읽고 근거로 이어지는 화면을 유지합니다.

## Overview

승인된 방향은 ‘결론 먼저, 단계 따라가기’입니다.
시각 기준은 plain-3 fix 2와 이번 mockup.html입니다.
새 화면도 같은 밝은 바탕과 짙은 초록 행동색을 사용합니다.
정답과 원문을 읽는 작업이 장식보다 먼저 보입니다.
이 문서는 기존 제품의 DESIGN.md를 교체할 정본입니다.

실제 앱의 화면 순서는 STRUCTURE.md를 따릅니다.
이번 시안의 첫 장면인 화면 목록은 검토용입니다.
실제 앱의 재방문 시작점은 S01 최근 결과입니다.
모든 숫자 예시는 mockup에만 사용합니다.
각 장면 맨 아래에 ‘디자인 확인용 화면입니다. 숫자는 모두 예시입니다.’를 한 번 둡니다.
실제 앱에는 이 문구가 없습니다.

## Colors

행동색은 짙은 초록입니다.
주 행동과 링크와 키보드 초점에 씁니다.
면과 보조 글은 중립색입니다.
색만으로 현재 위치나 상태를 전하지 않습니다.

| 역할 | 토큰 | 함께 보일 글 |
|---|---|---|
| 본문과 보조 정보 | ink / muted | 값의 단위와 조건 |
| 화면과 패널 | ground / paper | 제목과 본문 |
| 전역 기준과 선택 목록 | context / soft | 선택됨 / 보고 있음 |
| 행동 | accent / accent-hover | 행동을 나타내는 동사 |
| 선택한 근거 줄 | selected / selected-line | 쪽과 줄 위치 |
| 확인된 실패 | failure / failure-bg | 실패 사실과 복구 행동 |

빨강은 확인된 실패에만 씁니다.
목표 미달 자체는 빨강으로 강조하지 않습니다.
‘연결 안 됨’과 ‘평가 문서 잠김’은 중립색입니다.
삭제 확인도 초록 행동색을 유지합니다.
예: E06 모델 없음은 중립 상태 상자를 사용합니다.

## Typography

글꼴은 컴퓨터의 기본 글꼴만 사용합니다.
외부 글꼴을 불러오지 않습니다.
수치에는 같은 폭 숫자(tabular-nums)를 적용합니다.
원래 경로와 코드에만 고정폭 글꼴을 씁니다.

본문은 body 토큰을 사용합니다.
보조 문장과 표와 전역 기준에는 label 토큰을 사용합니다.
점수는 score 토큰을 사용합니다.
문제 값에는 value 토큰을 사용합니다.
제목은 한 문장으로 결론을 말합니다.
어절 안에서 한국어를 자르지 않습니다(`word-break: keep-all`).
긴 경로와 기술 이름은 필요한 위치에서 줄바꿈합니다(`overflow-wrap: anywhere`).
일반 설명은 약 65~75자 폭을 목표로 합니다.

## Layout

지원 폭은 1280~1680px입니다.
기준 폭은 1440px입니다.
휴대폰용 구성을 따로 만들지 않습니다.
화면은 머리글과 전역 기준과 작업 공간 순서입니다.
왼쪽 메뉴는 장소 이동을 담당합니다.
본문의 1·2·3은 링크 없는 현재 작업 경로입니다.
두 번째 탭이나 별도 진행 막대를 만들지 않습니다.

| 영역 | 기본 | 1320px 이하 | 1550px 이상 |
|---|---|---|---|
| 왼쪽 메뉴 | 176px | 160px | 동일 |
| 본문 좌우 여백 | 28px | 24px | 40px |
| 점수 열 | 400px | 380px | 동일 |
| 문제 값 목록 | 290px | 270px | 320px |
| 열 사이 | 24px | 원문 영역 20px | 24px |

가변 열은 최소 폭을 0으로 둡니다.
표는 부모 폭 안에서 줄바꿈합니다.
호출 기록의 16개 부분은 여덟 칸씩 두 줄로 배치합니다.
가로 넘침을 숨기는 방식으로 내용 손실을 덮지 않습니다.
장면 바깥 글과 카드가 같은 시작선에 놓이게 합니다.
전체 폭의 펼침 행은 중간에서 끊지 않습니다.

전역 기준은 스크롤 중에도 남습니다.
높이를 고정하지 않습니다.
왼쪽 메뉴에는 별도 고정 위치를 쓰지 않습니다.
긴 전역 설명과 메뉴가 겹치지 않게 합니다.
장면 내용은 충분한 최소 높이를 갖습니다.
예시 안내는 그 아래의 마지막 줄입니다.

## Elevation & Depth

면과 1px 경계선으로 구분합니다.
그림자와 빛나는 효과는 쓰지 않습니다.
전역 기준만 스크롤 위에 남습니다.
시안의 확인창은 별도 주소의 평평한 확인 영역입니다.
실제 앱의 확인창은 초점을 안에 유지합니다.
취소하면 원래 단추로 초점을 돌립니다.
실제 앱에서 Escape로 취소할 수 있어야 합니다.
이 동작은 스크립트 없는 시안의 검증 범위에 포함되지 않습니다.

## Shapes

조작 요소는 control 모서리를 사용합니다.
점수와 원문 비교와 상태 상자는 panel 모서리를 사용합니다.
일반 표와 펼침은 둥근 카드로 감싸지 않습니다.
선택 상태는 테두리와 글을 함께 바꿉니다.
경계선은 frontmatter의 borders를 따릅니다.
이 항목은 요청에 따른 DESIGN.md 스키마 확장입니다.

초점 테두리는 초점이 있는 조작 요소에만 그립니다.
장면과 본문 컨테이너에는 초점 테두리를 그리지 않습니다.
전역 `outline: none`은 사용하지 않습니다.
선택한 값의 경계는 border로 그립니다.
초점 표시와 선택 상태를 같은 것으로 만들지 않습니다.

## Components

| 구성 요소 | 배치와 내용 | 동작과 상태 |
|---|---|---|
| 전역 기준(context bar) | 문서 묶음 / 정답지 / 모델 상태의 세 칸 | 오류에도 유지합니다. 현재 선택과 실행 당시 조건을 구분합니다. |
| 왼쪽 메뉴 | STRUCTURE의 일곱 장소 | 한 곳에만 ‘보고 있음’을 붙입니다. S09는 다시 시험에 속합니다. S10은 두 결과 비교에 속합니다. |
| 단계 경로(step breadcrumb) | 결과 보기 / 원인 찾기 / 다시 시험 | 읽기 전용입니다. 실패 상태는 경로를 빼고 실패부터 읽게 합니다. |
| 점수 카드 | 모델과 문서 수 다음에 82.4 / 100점 | 90점 목표선과 차이를 붙입니다. 12/17의 뜻은 보통 크기 한 문장으로 씁니다. |
| 문제 카드 | 쉬운 문제 이름 다음에 문서 부분 | 세 종류 건수를 따로 링크합니다. 총손실과 해당 손실은 한 문장으로 연결합니다. |
| 값 목록과 필터 | 전체 9건과 못 뽑음 / 만듦 / 틀림 | 선택 값에 ‘선택됨’을 붙입니다. 필터 안에서도 값마다 원문을 엽니다. |
| 원문 대조 | 원문 줄과 AI 값의 두 열 | 실제 줄과 ‘원문 줄(추정)’을 구분합니다. 줄이 없으면 대신 고르지 않습니다. |
| 접힌 영역 | 내용 이름과 수와 요약을 제목에 둠 | 기본 details/summary를 씁니다. 23가지 기준을 모두 열 수 있어야 합니다. |
| 확인 영역(confirm sheet) | 대상 / 변경 / 비용 / 대기 / 보호 조건 / 유효시간 | 주 행동 하나와 취소를 둡니다. 만료와 상태 변경은 재확인으로 돌립니다. |
| 상태 상자(state block) | 확인한 사실과 할 일 | 빈 상태를 0점으로 바꾸지 않습니다. 조회 실패와 없음은 구분합니다. |
| 안내 띠(guide band) | 짧은 안내와 실제 기능 연결 | 메뉴를 막지 않습니다. 건너뛰기와 닫기를 제공합니다. 기존 경로를 함께 씁니다. |
| 설명 입력란 | 고정된 문서와 부분 바로 아래 | 새로고침 유실을 옆에 알립니다. 한 부분 시험에서만 수정합니다. |

정답을 보여 주는 곳에는 신뢰 범위를 함께 씁니다.
정답 초안은 AI가 먼저 만든 답이라고 설명합니다.
사람이 확인한 정답은 일부 개발 문서에만 있다고 설명합니다.
사람 확인 전 점수는 참고값이라고 설명합니다.

주 행동은 화면마다 하나입니다.
세부 행동은 관련 펼침 안에 둡니다.
추천 서버는 먼저 보여 줍니다.
대안 서버의 조작은 ‘다른 방법’ 안에 둡니다.
선택에 필요한 두 줄 비교는 접지 않습니다.
비용은 실제 요금이라는 말과 단위를 함께 보입니다.

가장 큰 문제에서 값을 여는 순서는 **틀림 → 만듦 → 못 뽑음**입니다.
같은 종류 안에서는 서버가 준 문서 순서와 값 순서를 유지합니다.
반드시 해당 채점 기준이 `items`에 있는 값을 고릅니다.
다른 기준의 값을 대신 열지 않습니다.
없으면 연결하지 못한 이유를 보여 줍니다.
예: 기본 첫 단추는 틀린 성분 A의 원문 5와 AI 값 8을 엽니다.
못 뽑음만 있으면 첫 누락 값을 엽니다.
그 줄에는 ‘원문 줄(추정)’을 붙입니다.

S02의 ‘이 부분 다시 시험’은 문서와 부분과 기준 실행을 S03에 채웁니다.
설명 입력란도 바로 노출합니다.
모델이 준비돼 있으면 ‘실제 시험 시작’으로 보냅니다.
추가 확인은 최대 한 번입니다.
이 시안은 일반 시험에 추가 확인을 두지 않습니다.
서버 변경의 비용 확인은 유지합니다.
모델이 없으면 연결 단계로 갑니다.
준비되면 ‘시험으로 돌아가기’를 보여 줍니다.
자동으로 화면을 옮기지 않습니다.

첫 사용 성공은 PRODUCT.md의 증거 조건을 따릅니다.
연습과 실제 성공을 합치지 않습니다.
근거 없는 상태에서 안내 완료를 만들지 않습니다.
다시 보기는 성공 이력을 지우지 않습니다.

## Do's and Don'ts

- **Do:** 결론과 다음 행동을 첫 화면에 둡니다.
- **Do:** 상태 글과 테두리를 함께 사용합니다.
- **Do:** 오류에도 전역 기준과 현재 대상을 남깁니다.
- **Do:** 원문 근거와 추정 위치를 구분합니다.
- **Do:** 0건과 기록 없음을 구분합니다.
- **Do:** 데이터 계약에 없는 정보는 NOTES에 남깁니다.
- **Don't:** 90점 목표선을 ‘합격’이라고 부르지 않습니다.
- **Don't:** 모델 없음과 터널 닫힘과 조회 실패를 합치지 않습니다.
- **Don't:** 두 번째 탐색 체계나 진행 표시를 만들지 않습니다.
- **Don't:** 애니메이션과 그라데이션과 글로우와 이모지를 넣지 않습니다.
- **Don't:** 평가용 문서 내용과 비밀값을 사용하지 않습니다.
- **Don't:** 기계 검사 통과를 실제 화면 검증이나 이해도 8/10의 증거로 쓰지 않습니다.
