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
  running-text: "#9a6700"
  warning-text: "#bc4c00"
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
  omission-current: "#cf222e"
  history-purple: "#8250df"
  history-pink: "#bf3989"
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
  help-title:
    fontSize: "24px"
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

이 문서는 2026-10-30 Step 0의 기준을 Step 8까지 갱신한 디자인 정본이다.
작업을 끝내는 도구 화면(Operate)으로 평가한다.
제품의 기준 문장은 “도구처럼 보여야 한다”다(PRODUCT.md:40).
새로운 브랜드 비유나 색 체계는 정하지 않는다.

확인 근거는 `app.css`, `index.html`, `app.js`, `guide.html`이다.
서버의 경로는 `../b_app.py`에서 확인했다.
위의 기계가 읽는 설정(frontmatter)은 현재 CSS 값을 옮긴 것이다.
CSS 변수는 앞의 `--`만 뺐다. 나머지 이름은 이 문서의 위치 설명용 이름이다.
화면 코드에 이 이름의 변수를 새로 만들었다는 뜻은 아니다.

시작 탭과 고급 스위치가 있다. 네 점수판 상세 카드와 작업의 더 하기는 접힌다.
용어와 기존 설명 말풍선은 키보드로도 열린다. 접기·안내·선택 저장 실패는 현재 화면 조작을 막지 않는다.
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

빠뜨림 표시는 빨강 `omission-current`다. 지어냄은 진한 주황 `warning-text`다.
원문 구간 띠에도 보라 계열 `section-band-odd`가 있다(app.css:164).
이 값은 새 브랜드 색을 제안하는 것이 아니다.
작은 상태 글은 대비를 위해 `running-text`와 `warning-text`를 쓴다. 옅은 색은 막대·칩·구간 띠에 남긴다.

실행 역사 그래프는 `app.js:16`의 여섯 색을 쓴다.
이는 CSS 상태 변수와 별개인 범주 구분이다.
추가 색은 `#bf3989`와 `#9a6700`이다. 나머지는 위 설정에 있다.

도움말의 별도 스타일도 같은 본문·면·선·주의·성공 색을 쓴다.
설명 그림의 모양과 글은 유지하고 기존 앱 팔레트에 맞췄다.
실버와 같은 값의 `#8c959f`는 범례 칩에만 쓴다. 값 글자는 `muted`다.

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
도움말 본문은 15px/1.7이며 제목은 24px·18px·15px이다.
새 글꼴이나 자동 확대 글자 크기는 추가하지 않는다.

## Layout

본문 최대 폭은 1240px이다. 여백은 위 12px, 좌우 20px, 아래 40px다(app.css:27).
본문을 가운데로 옮기는 자동 좌우 여백은 없다.
머리줄은 위에 고정되며 8px 20px 여백과 16px 간격을 쓴다(app.css:18–19).

| 구성 | 현재 값·동작 | 코드 근거 |
|---|---|---|
| 탭 | 4px 간격, 줄 바꿈, 선택한 단추는 파랑 | app.css:21–23 |
| 점수판 첫 줄·서버 카드 | 1.1fr : 1fr, 간격 12px, 960px 이하 한 열 | app.css:34–35 |
| 작업 카드 | 2fr : 1fr, 간격 12px, 1100px 이하 한 열 | `.jcols` |
| 실행 선택 상자 | 선호 폭 520px / 440px, 부모 폭 100% 이내 | `.pickrow`, `.pickcol` |
| 항목 신호등 | 이름·막대·종류·보조 점수는 가변 열, 수치·배지만 고정, 720px 이하 여러 줄 | `.item` |
| 역사 그래프 | 폭 100%, 최소 폭 없음, 원래 900 좌표 유지 | `.chart` |
| 원문 대조 | 최소 폭 0의 5fr : 6fr, 간격 12px, 960px 이하 한 열 | `.dgrid` |
| 쪽 그림·줄·값 패널 | 최대 높이 58vh / 32vh / calc(90vh - 40px) | app.css:154, 159, 170 |
| 도움말 틀 | 폭 100%, 높이 calc(100vh - 170px), 최소 480px | app.css:238 |

예: 960px 이하에서는 `.cols`가 `1fr` 한 열로 바뀐다(app.css:35의 조건).
이는 코드 규칙이며 브라우저에서 재측정한 결과는 아니다.

점수판은 지금 상태·합격 기준 뒤에 여섯 카드가 이어진다.
역사·문서·호출 격자·행 수는 요약 뒤에 접고 저장한다. 값은 접힌 본문에도 남는다.
`.scroll`은 내부 가로 스크롤을 허용한다(app.css:44).
1280–1680px에서 가로 스크롤이 없는지는 아직 실측하지 않았다.
본문 최대 폭은 유지했다. 격자 자식의 최소 폭은 0이며 긴 이름과 표 칸은 줄바꿈한다.

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
| 카드 | `.card`: 1px 선, 12px 16px 안쪽 여백, 아래 12px 간격 | `card()`의 접힌 카드는 제목·요약·토글을 머리에 둔다. 좁으면 머리줄이 줄바꿈한다. |
| 단추 | 기본 회색, 주 동작 파랑, 확인 동작 빨강 | 최소 높이 32px. 비활성은 회색 글·면·선으로 공통 표시한다. |
| 선택 상자 | 기본 `<select>`, 본문 글꼴, 최소 높이 32px, 최대 폭 100% | 연결 상태·조회 실패에 따라 시험과 본 실행을 잠근다. |
| 일반 표 | `.list`: 폭 100%, 아래 1px 선, 칸 여백 4px 6px | 모든 칸의 긴 글을 줄바꿈한다. 값 표는 고정 표 배치로 부모 폭을 지킨다. |
| 호출 격자 | `.grid`: 폭 100%, 첫 열 100px, 나머지는 같은 폭, 12px 글자 | 성공·실패·재추출·한도·기록 없음이 글로 보인다. |
| 항목 행 | `.item`: 가변 열, 통과·미달 배지, 4px 모서리 | 실제 단추이며 펼침 상태를 알린다. 다시 그려도 키보드 초점을 유지한다. |
| 말풍선 | `.tip`: 고정 위치, 최대 460px, 6px 9px 여백, 12px 글자 | 포커스·마우스로 열고 Escape로 닫는다. 설명 위로 이동하는 150ms 동안 닫지 않는다. |
| 원문 대조 | 쪽 그림 위 상자와 선택 줄의 노랑 바탕 | 근거 값 선택과 줄 선택을 연결한다. 접힘은 `details.dsec`·`details.dtab`을 쓴다(app.css:171–176). |
| 로그·안내문 차이 | 12px, 줄 바꿈, 1px 선, 6px 모서리 | 최대 높이 360px / 520px 후 내부 스크롤이다(app.css:139–140, 210–211). |
| 서버 확인창 | 최대 560px, 여백 16px 20px, 8px 모서리 | 요약 확인 후 실행한다. 실행 중 잠금도 있다(app.js:1359–1368, 1445–1475). |

예: 원문 줄 단추를 누르면 같은 줄을 근거로 쓴 결과 값이 선택된다(DOM 시험).

포커스는 파란색 2px 테두리다. 진한 선택 탭·주 동작·확인 단추에서는 흰색이다.
단추·펼침·말풍선 대상은 안쪽에 그려 스크롤 경계에서 잘리지 않게 한다.
브라우저 기본 포커스의 실제 모습과 대비는 이번에 확인하지 못했다.
상태줄은 `role=status`·`aria-live=polite`이고 오류는 `role=alert`다.
`localStorage`에는 그래프 선택·카드 접힘·고급·첫 사용 안내를 최소 상태로 저장한다.
역사 그래프 점도 SVG 안의 실제 HTML 단추다. 24px 조작 영역과 기존 점 크기를 구분한다.
오류는 사실 한 문장·할 일 한 문장·접힌 원문이다. 공통 글은 `b_app_text.POLISH_TEXT`에서 최초 HTML에 주입한다.
쪽 그림의 대체 글은 쪽 번호를 포함한다. 실버 비교 상태와 선택 상태는 글·접근성 속성을 함께 쓴다.

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
