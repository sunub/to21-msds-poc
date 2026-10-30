---
# 다듬기(refinement): PRODUCT.md의 결정대로 밝은 바탕·카드·시스템 글꼴을 유지한다.
name: B 작업 화면
description: 기존 화면 안에서 위계와 읽기 흐름을 다듬는 작업 도구
colors:
  ink: "#1f2328"
  muted: "#59636e"
  raw: "#6b7280"
  line: "#d1d9e0"
  soft: "#f6f8fa"
  ok: "#1a7f37"
  "no": "#cf222e"
  now: "#0969da"
  re: "#bf8700"
  limit: "#e16f24"
  gap: "#d4a72c"
  gold: "#afb8c1"
  white: "#fff"
  hover-neutral: "#eaeef2"
  selection-bg: "#fff8c5"
  selection-edge: "#eac54f"
  time: "#57606a"
  hover-row: "#f0f6fc"
  pass-bg: "#dafbe1"
  fail-bg: "#ffebe9"
  omission-current: "#8250df"
  cell-ok: "#aceebb"
  cell-retry: "#f5e0a3"
  cell-limit: "#ffc49b"
  cell-fail: "#ff8182"
  tooltip-bg: "#24292f"
  diff-delete-text: "#82071e"
  diff-add-text: "#116329"
  evidence-fill: "rgba(255, 212, 0, .28)"
  section-band-even: "#b6e3ff"
  section-band-odd: "#d8b9ff"
  silver-same: "#8c959f"
  silver-different: "#bc4c00"
  primary-hover: "#0550ae"
  result-fail-border: "#ffcecb"
  dialog-backdrop: "rgba(31, 35, 40, .35)"
  confirm-hover: "#a40e26"
  help-frame-border: "#d0d7de"
typography:
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR", sans-serif'
    fontSize: "14px"
    lineHeight: 1.5
  page-title:
    fontSize: "17px"
  card-title:
    fontSize: "16px"
  card-subtitle:
    fontSize: "14px"
  score:
    fontSize: "52px"
    fontWeight: 700
    lineHeight: 1
  score-unit:
    fontSize: "18px"
  sub:
    fontSize: "15px"
  hint:
    fontSize: "13px"
  mono:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "12px"
  raw:
    fontFamily: "ui-monospace, Menlo, monospace"
    fontSize: "12px"
  tooltip:
    fontSize: "12px"
  line-section:
    fontSize: "11px"
    fontWeight: 600
rounded:
  legend: "4px"
  control: "6px"
  card: "8px"
  badge: "10px"
  swatch: "50%"
spacing:
  micro: "2px"
  tight: "4px"
  field: "6px"
  small: "8px"
  control-x: "10px"
  grid: "12px"
  card-x: "16px"
  page-x: "20px"
  detail-indent: "24px"
  page-bottom: "40px"
components:
  button:
    backgroundColor: "{colors.soft}"
    rounded: "{rounded.control}"
    padding: "3px 10px"
  button-hover:
    backgroundColor: "{colors.hover-neutral}"
  button-primary:
    backgroundColor: "{colors.now}"
    textColor: "{colors.white}"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-confirm:
    backgroundColor: "{colors.no}"
    textColor: "{colors.white}"
  button-confirm-hover:
    backgroundColor: "{colors.confirm-hover}"
  card:
    backgroundColor: "{colors.white}"
    rounded: "{rounded.card}"
    padding: "12px 16px"
  tooltip:
    backgroundColor: "{colors.tooltip-bg}"
    textColor: "{colors.white}"
    typography: "{typography.tooltip}"
    rounded: "{rounded.control}"
    padding: "6px 9px"
  badge:
    rounded: "{rounded.badge}"
    padding: "1px 6px"
  dialog:
    rounded: "{rounded.card}"
    padding: "16px 20px"
---

다듬기(refinement)다. PRODUCT.md의 결정대로 밝은 바탕과 카드 구성을 유지한다. 컴퓨터에 있는 글꼴을 그대로 쓴다.

## Overview

이 문서는 2026-10-30 Step 0에서 확인한 현재 코드의 디자인 정본이다.
작업을 끝내는 도구 화면(Operate)으로 평가한다.
제품의 기준 문장은 “도구처럼 보여야 한다”다(PRODUCT.md:40).
새로운 브랜드 비유나 색 체계는 정하지 않는다.

확인 근거는 `app.css`, `index.html`, `app.js`, `guide.html`이다.
서버의 경로는 `../b_app.py`에서 확인했다.
위의 기계가 읽는 설정(frontmatter)은 현재 CSS 값을 옮긴 것이다.
CSS 변수는 앞의 `--`만 뺐다. 나머지 이름은 이 문서의 위치 설명용 이름이다.
화면 코드에 이 이름의 변수를 새로 만들었다는 뜻은 아니다.

현재 구현과 다음 step의 요구를 구분한다.
시작 탭과 고급 스위치는 PRODUCT.md의 목표이며 현재 구현에는 없다.
카드 전체 접기와 키보드 말풍선도 아직 없다.
로컬 미리보기 서버가 권한 오류로 시작되지 않아 실제 배치와 글꼴 계산값은 확인하지 못했다.

## Colors

흰 바탕 위에 회색 구분선을 두고 상태에 따라 색을 붙인다.
색 값은 위 설정을 정본으로 삼는다.

| 현재 역할 | 설정 이름 | 코드 근거 |
|---|---|---|
| 본문·보조 글·선·옅은 면 | ink / muted / line / soft | app.css:3 |
| 통과·실패·선택한 탭 | ok / no / now | app.css:4, 23, 53–54 |
| 재시도·출력 한도·실버 빈 곳·기준 막대 | re / limit / gap / gold | app.css:4, 40, 69, 99 |
| 가리킨 단추·행 | hover-neutral / hover-row | app.css:14, 90 |
| 통과·미달 배지 | pass-bg / fail-bg | app.css:94–95 |
| 호출 격자 상태 | cell-ok / cell-retry / cell-limit / cell-fail | app.css:114–117 |
| 선택한 원문 줄·칸 | selection-bg / selection-edge | app.css:165 |
| 원문 그림의 강조 상자 | evidence-fill / limit | app.css:158 |
| 실버와 같음·다름·실버에만 있음 | silver-same / silver-different / no | app.css:180–182 |
| 안내문 삭제·추가 | fail-bg + diff-delete-text / pass-bg + diff-add-text | app.css:142–143 |
| 말풍선·대화상자 뒤의 면 | tooltip-bg / dialog-backdrop | app.css:123, 233 |

예: 현재 `.item.fail .badge`는 `#ffebe9` 바탕과 `#cf222e` 글자를 쓴다(app.css:95).

현행 예외도 보존 기록한다. 빠뜨림 표시는 보라색 `omission-current`다(app.css:100).
원문 구간 띠에도 보라 계열 `section-band-odd`가 있다(app.css:164).
이 값은 새 브랜드 색을 제안하는 것이 아니다.
향후 상태 의미 정리는 기존 빨강·주황·노랑 안에서 한다(UI_GUIDE의 사용자 결정).

실행 역사 그래프는 `app.js:16`의 여섯 색을 쓴다.
이는 CSS 상태 변수와 별개인 범주 구분이다.
추가 색은 `#bf3989`와 `#9a6700`이다. 나머지는 위 설정에 있다.

도움말은 별도 스타일을 가진다(`guide.html:8–18`).
본문은 `#1f2933`, 코드 바탕은 `#f3f5f7`, 표 선은 `#d0d7de`다.
예시는 `#eef6ff`와 `#4a90d9`, 주의는 `#fff4e5`와 `#e08a00`을 쓴다.
설명 그림에는 `#4a5568`, `#e8f7ec`, `#2f9e5a`도 있다(`guide.html:34–42`).
이를 앱 전체의 신규 색 체계로 확장하지 않는다.

## Typography

본문은 시스템 글꼴과 한국어 대체 글꼴을 쓰는 14px 글자다(app.css:8–9).
`Noto Sans KR`는 로컬 대체 후보이며 외부에서 내려받는 선언은 없다.
단추와 선택 상자는 본문 글꼴을 상속한다(app.css:13, 15).
제목의 굵기는 별도 CSS 값이 없으므로 브라우저 기본값에 맡긴다.
확인하지 않은 굵기를 설정에 넣지 않았다.

| 용도 | 현재 값 | 코드 근거 |
|---|---|---|
| 페이지 제목 / 카드 제목 / 카드 소제목 | 17px / 16px / 14px | app.css:20, 37–38 |
| 큰 점수 / 단위 / 부가 점수 | 52px·700·줄 높이 1 / 18px / 15px | app.css:50–52 |
| 설명·상태·범례 | 13px | app.css:24, 39, 43 |
| 원래 표기·코드 | 고정폭 12px | app.css:11 |
| 표 숫자 | 같은 폭 숫자(tabular-nums) | app.css:92, 134 |
| 원문 구간 번호 | 11px·600 | app.css:166 |

Step 1에서 `.raw`를 추가했다. 원래 폴더 이름·모델 태그는 지정된 회색 `#6b7280`과 고정폭 12px로 그린다.
긴 이름은 줄바꿈하며, 실행 선택지의 `title`에도 원래 이름을 둔다.
도움말 본문은 15px/1.7이며 제목은 22px·18px·15px이다(`guide.html:8–11`).
새 글꼴이나 자동 확대 글자 크기는 추가하지 않는다.

## Layout

본문 최대 폭은 1240px이다. 여백은 위 12px, 좌우 20px, 아래 40px다(app.css:27).
본문을 가운데로 옮기는 자동 좌우 여백은 없다.
머리줄은 위에 고정되며 8px 20px 여백과 16px 간격을 쓴다(app.css:18–19).

| 구성 | 현재 값·동작 | 코드 근거 |
|---|---|---|
| 탭 | 4px 간격, 줄 바꿈, 선택한 단추는 파랑 | app.css:21–23 |
| 점수판 첫 줄·서버 카드 | 1.1fr : 1fr, 간격 12px, 960px 이하 한 열 | app.css:34–35 |
| 작업 카드 | 같은 폭 세 열, 간격 12px, 1100px 이하 한 열 | app.css:187–188 |
| 실행 선택 상자 | 점수판 520px, 비교 440px | app.css:48, 127 |
| 항목 신호등 | 290px 16px 204px 58px 64px 230px 1fr, 간격 6px | app.css:88 |
| 역사 그래프 | 폭 100%, 최소 720px | app.css:79 |
| 원문 대조 | minmax(340px, 5fr) : 6fr, 간격 12px | app.css:152 |
| 쪽 그림·줄·값 패널 | 최대 높이 58vh / 32vh / calc(90vh - 40px) | app.css:154, 159, 170 |
| 도움말 틀 | 폭 100%, 높이 calc(100vh - 170px), 최소 480px | app.css:238 |

예: 960px 이하에서는 `.cols`가 `1fr` 한 열로 바뀐다(app.css:35의 조건).
이는 코드 규칙이며 브라우저에서 재측정한 결과는 아니다.

현재 점수판은 카드 일곱 개를 한꺼번에 그린다(index.html:27–35; app.js:134–141).
첫 두 카드 뒤에 다섯 카드가 세로로 이어진다.
`.scroll`은 내부 가로 스크롤을 허용한다(app.css:44).
1280–1680px에서 가로 스크롤이 없는지는 아직 실측하지 않았다.
다음 step은 정보를 보존하며 카드 요약과 접기를 추가한다. 최대 폭은 유지한다.

## Elevation & Depth

카드는 그림자 없이 1px 선으로 나눈다(app.css:36).
높이 순서는 고정 머리줄 5, 말풍선 20이다(app.css:18, 122).
서버 확인창은 브라우저 대화상자(`<dialog>`)를 쓴다(index.html:88).
뒤 화면에는 `dialog-backdrop`의 반투명 면을 둔다(app.css:233).
그림자 효과와 움직임 선언은 현재 `app.css`에 없다.

## Shapes

단추와 패널 모서리는 6px다. 카드와 확인창은 8px다.
배지는 10px, 작은 범례 표시는 4px, 원형 색 표시는 50%다.
탭은 위쪽 모서리만 6px이며 아래쪽 선이 없다(app.css:22).
현재의 차이를 유지한다. 모든 요소를 큰 둥근 카드로 통일하지 않는다.

## Components

| 구성 요소 | 현재 규칙 | 상태와 제한 |
|---|---|---|
| 카드 | `.card`: 1px 선, 12px 16px 안쪽 여백, 아래 12px 간격 | `card()`는 제목·설명·본문을 항상 펼쳐 그린다(app.js:61–63). 전체 카드 접기는 없다. |
| 단추 | 기본 회색, 주 동작 파랑, 확인 동작 빨강 | hover 값은 있다. 공통 disabled·loading 규칙은 없다. 서버 disabled는 불투명도 .45다(app.css:226). |
| 선택 상자 | 기본 `<select>`, 본문 글꼴, 최대 폭 100% | 연결이 없는 모델 선택지를 일부 막지만 실행 단추의 조건과는 별개다(app.js:959–964, 1025, 1173). |
| 일반 표 | `.list`: 폭 100%, 선 합침, 아래 1px 선, 칸 여백 2px 6px | 마지막 칸은 긴 글을 글자 단위로 나눈다(app.css:104–106). |
| 호출 격자 | `.grid`: 12px 글자, 칸 52px × 24px, 여백 0 4px | 상태색과 시간 글자를 함께 쓴다(app.css:109–118; app.js:374–384). |
| 항목 행 | `.item`: 고정 열, 통과·미달 배지, 클릭하여 오류 표 펼침 | `div` 클릭이며 키보드 활성화 처리가 없다(app.js:247–259). |
| 말풍선 | `.tip`: 고정 위치, 최대 460px, 6px 9px 여백, 12px 글자 | `setupTip()`은 mouseover·mousemove만 처리한다(app.js:70–83). 포커스·점선 용어 규칙은 없다. |
| 원문 대조 | 쪽 그림 위 상자와 선택 줄의 노랑 바탕 | 근거 값 선택과 줄 선택을 연결한다. 접힘은 `details.dsec`·`details.dtab`을 쓴다(app.css:171–176). |
| 로그·안내문 차이 | 12px, 줄 바꿈, 1px 선, 6px 모서리 | 최대 높이 360px / 520px 후 내부 스크롤이다(app.css:139–140, 210–211). |
| 서버 확인창 | 최대 560px, 여백 16px 20px, 8px 모서리 | 요약 확인 후 실행한다. 실행 중 잠금도 있다(app.js:1359–1368, 1445–1475). |

예: `setupTip()`은 현재 `data-tip`을 가진 요소 위로 마우스가 들어오면 설명을 표시한다(app.js:72–75).

포커스 테두리를 지우는 선언은 없다. 전용 `:focus`·`:focus-visible` 규칙도 없다.
브라우저 기본 포커스의 실제 모습과 대비는 이번에 확인하지 못했다.
상태 글은 있으나 상태 영역의 자동 읽기(`aria-live`)는 없다(index.html:20).
`localStorage`에는 역사 그래프 선택을 저장한다(app.js:65–67, 285–293).
카드 접힘이나 첫 사용 안내를 저장하는 규칙은 현재 없다.

## Do's and Don'ts

다음 원칙은 PRODUCT.md와 사용자 UI_GUIDE에서 정한 개선 방향이다.
위의 현행 구현과 같다고 간주하지 않는다.

- **Do:** 지금의 최대 폭과 시스템 글꼴을 유지한다.
- **Do:** 카드마다 결론을 먼저 보여 주고 상세 표를 접는다. 정보는 보존한다.
- **Do:** 쉬운 실행 이름 옆에 원래 표기를 남긴다.
- **Do:** 색 옆에 상태 글을 둔다. 용어 설명은 포커스로도 열리게 한다.
- **Do:** 오류는 확인한 사실과 할 일을 나눈다. 예외 원문은 펼침에 둔다.
- **Don't:** 새 브랜드 색이나 외부 글꼴을 도입하지 않는다.
- **Don't:** 흐림 효과, 그라데이션 글자, 빛나는 그림자, 장식 이모지, 움직임 효과를 넣지 않는다.
- **Don't:** 현재 남아 있는 보라 계열을 새 브랜드 기준으로 삼지 않는다.
- **Don't:** 디자인 문서에 원문 내용이나 비밀값을 옮기지 않는다.

질문 단계는 이 step의 비대화형 지시에 따라 생략했다. 별도 디자인 보조 파일은 만들지 않았다.
