# 승인된 설계의 정보와 동작을 보존하며 작업 화면을 구현합니다.

이 문서는 app-redo step 0의 구현 계획입니다.
검토 기준일은 2026-10-31입니다.
이 step은 화면 코드와 시험을 바꾸지 않습니다.
근거는 승인 설계와 현재 코드입니다.
설계의 예시 수치와 실제 실행 결과를 구분합니다.

## 파일 나누기

빌드 없는 일반 스크립트(`<script>`) 10개로 나눕니다.
가져오기·내보내기 방식의 ES 모듈(`import`·`export`, `type="module"`)은 쓰지 않습니다.
`_common.txt` 3절의 결정을 따릅니다.

1. 기존 화면 시험은 Node의 격리 실행 함수(`vm.runInContext`)로 전역 이름을 읽습니다. 일반 스크립트는 같은 실행 공간에서 파일 순서대로 읽을 수 있습니다.
2. 새 패키지와 빌드 도구를 추가할 수 없습니다. 일반 스크립트는 브라우저에서도 별도 연결 도구 없이 같은 전역을 공유합니다.

| 순서 | 파일 | 맡는 일 | 만드는 step |
|---|---|---|---|
| 1 | `js/core.js` | 상태 `S`, 요소 만들기 `h`·`s`·`fill`, 요청 `api`·`post`, 글 `T`, 오류, 접기, 말풍선, 저장소, 사건 `on`·`emit` | 1 |
| 2 | `js/shell.js` | 구역 등록 `shellDefineView`, 화면 이동 `go`, 해시, 공통 맥락, 첫 화면, `start` | 1 |
| 3 | `js/score.js` | 최근 결과, 문제, 이력, 문서와 호출, 행 수, 채점 기준 | 2 |
| 4 | `js/source.js` | 원문 그림과 줄, 값 대조, 근거 선택 | 3 |
| 5 | `js/compare.js` | 두 결과 비교, 바뀐 값, 지시문 차이 | 4 |
| 6 | `js/servers.js` | 모델 연결, 서버 상태, 확인 절차, 짧은 연결 구역 | 5 |
| 7 | `js/jobs.js` | 다시 시험, 여러 문서 실행, 비교표, 작업 기록 | 6 |
| 8 | `js/journey.js` | 두 갈래 안내, 진행과 성공 기록 | 7 |
| 9 | `js/help.js` | 도움말과 용어, 문맥 도움 연결 | 8 |
| 10 | `js/boot.js` | `start();` 한 줄 | 1 |

`index.html`은 `</body>` 바로 앞에 이 순서로 싣습니다.
후속 step은 자기 파일을 `boot.js` 바로 앞에 추가합니다.
옛 `app.js`는 step 1부터 싣지 않습니다.
옛 시험이 사용하는 파일 자체는 step 9까지 유지합니다.
정적 파일 제공은 기존 `b_app.py:200`의 `_static`을 사용합니다.

맨 위 이름은 모든 파일을 통틀어 유일해야 합니다.
공통 계약 이름을 제외한 이름에는 영역 접두어를 붙입니다.
접두어는 `core`, `shell`, `score`, `source`, `compare`, `servers`, `jobs`, `journey`, `help`입니다.
상수도 `SCORE_`처럼 영역을 붙입니다.
예: 옛 시험의 `run_js`는 `vm.runInContext`로 `S`를 읽습니다(`test_B_b_app_score_ui.py:58`).

화면 이동은 `go(screenId, args)`로만 요청합니다.
다른 화면에 알릴 일은 `emit(event, payload)`로 보냅니다.
구독은 `on(event, handler)`로 등록합니다.
같은 구독을 다시 그릴 때마다 늘리지 않습니다.
사건 이름은 `STRUCTURE.md`의 이벤트 표를 따릅니다.
근거 선택은 `evidence_line_shown`입니다.
시험 결과 열기는 `try_result_viewed`입니다.
`S.focus`에는 실행과 문서와 항과 값 경로를 둡니다.
원문 묶음과 다음 시험 묶음을 구분해 둡니다.
선택한 원문 값과 AI 값은 메모리에서만 전달합니다.
step 6은 그 값으로 `jobs.focus.*`를 표시합니다.
다른 화면의 그리기 함수를 직접 호출하지 않습니다.
step 5가 명시한 공유 구역 `serversRenderCompact(el, {model})`는 구역 합성용 예외입니다.
첫 사용 기록에는 `S.focus`를 저장하지 않습니다.

본문은 `word-break: keep-all`을 씁니다.
임의 위치 줄바꿈(`overflow-wrap: anywhere`)은 아래 데이터 class에만 허용합니다.
화면 전체와 단추와 일반 설명에는 적용하지 않습니다.

| class | 담는 데이터 | 승인 근거 |
|---|---|---|
| `.technical` | 긴 경로, 모델 태그, 코드, JSON, 로그 | mockup의 기술 정보 구역과 DESIGN의 코드 글꼴 규칙 |
| `.big-value` | 길어질 수 있는 원문 값과 AI 값 | mockup의 값 대조 |
| `.selected-line` | 선택한 원문 줄 | mockup의 근거 줄 상자 |
| `.issue-meta` | 문제 목록의 문서 식별자와 값 | mockup의 문제 목록 |
| `.page-text` | 펼친 원문 글자 | mockup의 원문 영역 |
| `.raw` | 원래 폴더 이름과 태그 | 상위 UI_GUIDE의 원래 표기 규칙 |

`code`와 `pre`에는 `.technical`을 명시해 제한 범위를 유지합니다.
긴 경로 때문에 `word-break: break-all`을 사용하지 않습니다.

## 화면과 모듈

주소 해시에는 승인 화면 번호의 소문자 표기를 씁니다.
아래 구역 이름(view id)은 이 계획에서 정한 구현 식별자입니다.
승인된 정보 구역을 새 기능 없이 나눈 것입니다.
S01~S10은 화면입니다.
P01과 P02는 원래 화면으로 돌아오는 확인 영역입니다.
표에는 전용 구역 36개가 있습니다.

| 화면 id | 화면 이름(COPY.md) | 그 화면에 들어가는 구역(view) id | 그 구역을 그리는 파일 | 맡는 step |
|---|---|---|---|---|
| `s01` | 최근 결과 (`nav.recent`) | `score-summary`<br>`score-problems`<br>`score-history`<br>`score-docs`<br>`score-grid`<br>`score-rows`<br>`score-rule`<br>`score-gaps` | `js/score.js` | 2 |
| `s02` | 원문과 맞춰 보기 (`nav.source`) | `source-top`<br>`source-values`<br>`source-page`<br>`source-selection` | `js/source.js` | 3 |
| `s03` | 다시 시험 (`nav.retest`) | `jobs-try`<br>`jobs-result`<br>`jobs-connection` | `js/jobs.js`<br>`js/servers.js`는 연결 구역 제공 | 6, 연결 구역 5 |
| `s04` | 두 결과 비교 (`nav.compare`) | `compare-summary`<br>`compare-conditions`<br>`compare-items`<br>`compare-values`<br>`compare-rows`<br>`compare-prompts` | `js/compare.js` | 4 |
| `s05` | 작업 기록 (`nav.jobs`) | `jobs-list`<br>`jobs-detail` | `js/jobs.js` | 6 |
| `s06` | AI 켜기와 비용 (`nav.servers`) | `servers-summary`<br>`servers-models`<br>`servers-runpod`<br>`servers-rngd`<br>`servers-log` | `js/servers.js` | 5 |
| `s07` | 도움말 (`nav.help`) | `help-topics`<br>`help-glossary` | `js/help.js` | 8 |
| `s08` | 처음 사용 안내 (`nav.open_guide`) | `journey-choice`<br>`journey-records` | `js/journey.js` | 7 |
| `s09` | 여러 문서 시험하기 (`jobs.trial.open_batch`) | `jobs-run` | `js/jobs.js` | 6 |
| `s10` | 비교표 만들기 (`compare.table.open`) | `jobs-compare` | `js/jobs.js` | 6 |
| `p01` | 문서와 정답을 함께 검토한 뒤 적용하세요. (`context.picker.title`) | `context-picker` | `js/shell.js` | 1 |
| `p02` | 동작별 작업 확인 (`servers.confirm.*`, `jobs.confirm.stop.*`) | `action-confirm` | `js/servers.js`<br>`js/jobs.js` | 5, 6 |

공통 구역은 네 개입니다.

- `app-header`: 앱 이름과 처음 사용과 진행 중 작업입니다. step 1의 `shell.js`가 그립니다.
- `global-context`: 문서 묶음과 정답지와 모델 상태입니다. 머리글 아래에 둡니다. 스크롤 중에도 남습니다.
- `main-nav`: 왼쪽의 일곱 메뉴입니다. S09는 다시 시험에 속합니다. S10은 두 결과 비교에 속합니다.
- `journey-band`: S01의 첫 방문 안내와 재방문 알림입니다. step 1이 자리를 둡니다. step 7의 `journey.js`가 그립니다.

첫 방문도 `s01`로 들어갑니다.
처음인 경우에만 그 위에 안내 띠를 보입니다.
재방문도 `s01`의 최근 결과 요약으로 들어갑니다.
주소 해시가 있으면 지정 화면을 먼저 엽니다.
첫 방문 여부는 `/api/journey` 응답으로 판단합니다.
응답 전이나 조회 실패를 첫 방문으로 간주하지 않습니다.
예: 승인 구조의 `#s03`은 첫 방문이어도 S03을 지정합니다(`STRUCTURE.md:350`).

고른 묶음에 실행이 없으면 결과 없음으로 표시합니다.
정답지 변경 뒤에는 새 점수를 받기 전까지 이전 점수를 숨깁니다.
원문은 실행 당시 묶음을 먼저 엽니다.
다음 시험에 고른 묶음과 다르면 둘 다 표시합니다.
도움말과 연결 화면에서 돌아올 대상은 메모리에서 유지합니다.

## 정보 보존표

옛 함수 위치는 `backend/scripts/b_app_static/app.js` 기준입니다.
승인 구조의 I01~I81을 현재 코드와 대조했습니다.
추가 행은 값 상세와 도움말의 직접 이동 단위를 보충합니다.
`새 자리`는 해당 구현 step이 실제 함수 이름 또는 DOM id로 채웁니다.
step 9에서 94칸을 모두 확인했습니다. 첫 코드 표기는 자동 시험이 존재를 확인하는 대표 함수 또는 DOM id입니다.

| 번호 | 옛 정보 | 옛 자리 | 새 화면·구역 | 맡는 step | 새 자리 |
|---|---|---|---|---|---|
| I01 | 앱 이름, 탭, 시작 안내, 전체 상태 문장 | `index.html #status, setupTabs` | 공통 app-header·main-nav·global-context | 1 | `#app-heading`, `#main-nav`, `#global-context`, `#status`; `shellRenderHeader/go` |
| I02 | 화면 목적과 도움말 장 연결 | `index.html .tab 설명, guide.html 장 링크` | 공통 화면 설명 → S07 help-topics | 1, 8 | `#help-context-s01`~`s10`(S07 제외) → `helpOpen(topic, screen)`. 원래 화면과 선택은 `helpReturn`으로 복원 |
| I03 | 용어 말풍선, 접힘 상태, 키보드 포커스 | `term, setupTip, card, loadCards` | 공통 core 도우미 | 1 | `term`: `core.js`: `term/setupTip/card/loadCards/coreRead/coreWrite`; 말풍선·접기 새 시험 통과 |
| I04 | 앱 목적, 서버 없이 결과 확인, 점수→문제→원문 3단계 | `renderStart, journeyStep` | S08 journey-choice, S01 journey-band | 7 | `journeyRenderChoice`: `journeyRenderChoice/journeyRenderBand/journeyRenderStrip`: 두 갈래·실제 화면 행동·준비/실패/건너뛰기 |
| I05 | 단계 완료, 첫 성공 시각, 실패 후 위치 | `advanceJourney, journeyPassed, focusJourneyValue` | S08 journey-records | 7 | `journeyRenderRecords`, `journeyRecord/journeyComplete`: 실제 성공·연습·시각/횟수·이어하기. `journeyReplay/journeyDismiss`는 성공 이력 보존 |
| I06 | 다음에 할 일: 비교·시험·서버 | `renderStart, journeyStep` | S01 score-summary, S08 journey-choice | 2, 7 | `scoreConditions`의 다음 행동·`#score-retest`, `scoreRenderHistory`의 비교 이동. 서버 연결은 공통 맥락 줄. S08의 `journeyConnection`은 `serversRenderCompact` 재사용 |
| I07 | 안내 닫기, 처음부터 다시 보기 | `resetJourney, dismissJourney` | S08 journey-records | 7 | `journeyReplay`: `journeyRenderRecords`, `journeyRecord/journeyComplete`: 실제 성공·연습·시각/횟수·이어하기. `journeyReplay/journeyDismiss`는 성공 이력 보존 |
| I08 | 실행 목록·읽기 실패 수·다시 읽기·채점 로딩 | `loadAll, loadRun, renderScoreLoading, scoreLoadFailure` | S01 score-summary | 2 | `scoreLoad`: `scoreLoad/scoreRenderSummary/scoreSelect`: 개수 먼저 로딩, 부분 실패, 재조회 |
| I09 | 현재 점수·부족 점수·필수 달성 수·상위 문제 3개·다음 행동 | `renderStatus, openScoreSource` | S01 score-summary·score-problems | 2 | `scoreRenderSummary`: `scoreRenderSummary/scoreCounts/scoreOpenSource`, `scoreRenderProblems`: API 손실 순위, 부족 점수는 실행 조건의 API 요약 |
| I10 | 총점·목표선·필수 막대·전체 판정 | `renderNow, goalBar` | S01 score-summary | 2 | `scoreRenderSummary`: `scoreRenderSummary/scoreBar`: `targets.weighted`, `targets.must` 그대로 표시 |
| I11 | 실행 이름·원래 폴더명·모델 태그와 전체 이름·지시문 버전·입력 폴더·시각 | `runLabel, rawRun, modelName, renderNow` | S01 score-summary 실행 조건 | 2 | `scoreConditions`: 표시 이름·원래 이름·모델 태그/전체 이름·프롬프트·입력·시작 시각 |
| I12 | 완료 문서 수·진행 중·채점 수·제외 수·정답 없는 수 | `progressLine, renderNow` | S01 score-summary 채점 범위 | 2 | `scoreConditions`: progress, docs/no_gold/excluded 범위 |
| I13 | 값 없는 행을 뺀 점수·원점수와의 차이·계산 뜻 | `renderNow` | S01 score-rule | 2 | `#score-rule`, `scoreRenderRule`: 양쪽 빈 행 제외 보조 점수·차이·계산 뜻 |
| I14 | 모델 연결 안내와 저장 결과의 오프라인 조회 | `connLine, renderConnNow` | 공통 global-context, S01 score-summary | 1, 2 | `shellRenderModels`: `#global-context #context-model`, `shellRenderModels/shellPollServers`; `scoreConditions`에 실행 당시 모델 별도 표시 |
| I15 | 23개 항목의 등급 수·무게·목표·측정 방법·정답 초안 한계 | `renderRule` | S01 score-rule, S07 help-topics | 2, 8 | `scoreRenderRule`: 등급 수·무게·목표·방법·정답 한계. S07의 helpRenderMethods와 helpRenderTopics에 설명 보존 |
| I16 | 항목별 점수·목표선·달성 여부·미달만/모두·숨긴 수 | `renderItems, itemRow, scoreBar` | S01 score-problems | 2 | `scoreRenderProblems`: 서버 손실 순서, 전체/미달 필터, 숨긴 수, button/aria-expanded |
| I17 | 빠뜨림·지어냄·틀림의 뜻과 건수 | `renderItems, itemRow` | S01 score-problems | 2 | `scoreCounts`, `score-problems`의 문제 종류 펼침: counts null은 기록 없음 |
| I18 | 오류 상세 문서·종류·내용·현재 표시 제한 안내 | `detailList` | S01 score-problems → S02 source-values | 2, 3 | `scoreProblemDetail`: 문서·종류·내용, 300건씩 더 보기, `scoreOpenSource`. sourceRenderSelection에 실제 원문 표시 |
| I19 | 정답 초안의 빈 곳·출처·발견 시점 | `itemRow, /api/silver_gaps` | S01 score-gaps | 2 | `scoreGap`: `scoreGap/scoreRenderGaps`: 선택 key의 gaps, 출처·발견일·조회 실패 |
| I20 | 항목별 값 없는 행 제외 점수 | `itemRow` | S01 score-problems | 2 | `scoreProblemDetail`: items_na_excluded 값 그대로 |
| I21 | 실행 이력 그래프·날짜·모델 범례·현재 실행·목표선·최고 점수 | `renderHistory` | S01 score-history | 2 | `scoreRenderHistory`: `scoreRenderHistory/scoreHistoryRuns`: SVG·키보드 점·같은 선택 표, 시작일·모델·현재·목표선, 최고는 서버 요약 |
| I22 | 두 점 선택 순서·선택 해제·A/B로 보내기 | `savePick, renderHistory` | S01 score-history → S04 compare-summary | 2, 4 | `scoreSavePick`: `scoreSavePick/scoreHistoryPick` → `go(s04,{a,b})` → `compareEnsure`: 선택한 순서 그대로 A/B 복원 |
| I23 | 문서별 점수·필수 미달 항목·시간·300초 목표·시간 기록 없음 | `renderDocs` | S01 score-docs | 2 | `scoreRenderDocs`: 문서별 점수·필수 미달·초·시간 목표·기록 없음 |
| I24 | 문서×16항 호출 격자·한 문서의 여러 MSDS | `renderGrid` | S01 score-grid | 2 | `scoreRenderGrid`: 문서별/MSDS 순번별 16칸, 8칸씩 두 줄 |
| I25 | 성공·재추출·출력 한도·실패·기록 없음·시도 수·시간·방식·한도 원인 | `gridCell, renderGrid` | S01 score-grid | 2 | `scoreCall`: 상태 글·시도·시간·방식·한도 원인 펼침 |
| I26 | 표별 결과/정답 행 수·비율·남는 값(extras) | `renderRows` | S01 score-rows | 2 | `scoreRenderRows`: 표별 결과/정답 행 수·비율·extras |
| I27 | A/B 선택·실행 원래 이름·순서 교환·비교 중/실패 | `diffSelect, loadDiff, renderDiffTop` | S04 compare-summary | 4 | `compareEnsure`: `compareEnsure/compareLoad/compareSelect`, compare-summary: run_kind 묶음·run_label·원래 이름·순서 교환·로딩·실패·재시도 |
| I28 | 모델·지시문 버전·입력·동시 호출 수·코드 커밋·변경 조건 | `renderDiffTop` | S04 compare-conditions | 4 | `compareConditionsLead`: `compareConditionsLead/compareRenderConditions`: 결론 위 조건 차이와 같은 조건 흔들림, 상세의 모델·버전·입력·동시 수·코드·현재 정답지 |
| I29 | 총점 전후·차이·값 없는 행 제외 점수 전후 | `renderDiffTop, changeLine` | S04 compare-summary | 4 | `compareRenderSummary`: `compareRenderSummary/compareRenderConditions`: API weighted·weighted_na_excluded·delta와 양쪽 targets, 같은 조건은 중립 class |
| I30 | 공통 문서 수·A에만/B에만 있는 수·다른 평균의 주의 | `renderDiffTop` | S04 compare-conditions | 4 | `compareConditionsLead`: `compareConditionsLead/compareRenderConditions`: 공통·A 전용·B 전용 문서 수/목록, 서로 다른 평균 주의 |
| I31 | 23개 점수 차·등급·관련 항·하락만/모두·숨긴 수 | `renderDiffItems` | S04 compare-items | 4 | `compareRenderItems`: API 점수·등급·관련 항·정렬·내려간 것/모두·숨긴 수, 입력 배열 불변 |
| I32 | 2점 이상 하락의 원인 후보·후보 없음 | `renderDiffItems` | S04 compare-items | 4 | `compareRenderItems`: API causes의 후보 순서·근거·후보 없음, 추정 안내를 근거보다 먼저 표시 |
| I33 | 지시문 변경 항·전후 줄 수·행/JSON 형식·차이 줄·재구성 해시 불일치 | `togglePrompt, promptView` | S04 compare-prompts | 4 | `compareRenderPrompts`: `compareRenderPrompts/compareFetchPrompt/comparePromptBody`: 16개 항 lazy 요청·실행쌍 캐시·A/B 줄 수/형식·글 차이·해시 불일치·오류 복구 |
| I34 | 새로 맞춘 값·새로 틀린 값·문서·종류·내용·표시 수 | `renderDiffValues, valueTable` | S04 compare-values → S02 source-values | 4 | `compareRenderValues`: `compareRenderValues/compareValueList/compareOpenSource`: 두 목록·수·300개씩 더 보기·단추/초점 유지 → S02. 정확한 path 없는 현재 API는 항 단위 연결과 안내 |
| I35 | A/B/정답 표 행 수·가까워짐/멀어짐/차이 유지 | `renderDiffRows` | S04 compare-rows | 4 | `compareRenderRows`: API의 모든 A/B/정답 행 수, 가까움/멀어짐/유지 글. 같은 조건은 중립 표시 |
| I36 | 실행·문서 선택·정답 없는 개발 문서 | `initDoc, docsOf, renderDocTop` | S02 source-top | 3 | `sourceRenderTop`, `sourceEnsure`, `sourceRunDocs`: 실행·문서 선택과 원문 전용 경로 |
| I37 | 자료 불러오기 실패·할 일·예외 원문 | `renderDocTop, loadFailure` | S02 source-top | 3 | `sourceRenderTop`, `sourceReload`: 자료 없음·잠김·실패·로딩·재시도 |
| I38 | 쪽 선택·16항 이름·구간 시작/끝·제목 못 찾음 | `renderDocTop, goSection` | S02 source-top·source-page | 3 | `sourceGoSection`, `sourcePage`, `sourceRenderPage`: 16항 이름·구간·쪽 선택 |
| I39 | 결과 값 수·같음/다름/정답에만 수·정답 없음·문서 경고 | `renderDocTop` | S02 source-top·source-values | 3 | `sourceRenderTop`, `sourceRenderSelection`: 비교 수·정답 없음·경고 |
| I40 | 쪽 그림·원문 줄·근거 상자·항 구간 띠·줄별 연결 값 수 | `renderDocLeft, drawBoxes` | S02 source-page | 3 | `sourceRenderPage`, `sourceDrawBoxes`, `sourceMark`: 그림·줄 단추·근거 상자·항 표시·연결 수 |
| I41 | 결과의 항→표→행→칸 구조·기술 경로·칸 수·항 모름 | `renderDocRight, tableBlock, rowHead` | S02 source-values | 3 | `sourceStructure`, `sourceTable`: 항→표→행→칸, 알 수 없는 항과 extras 포함 |
| I42 | 결과 값·정답 값·정답에만 있는 행/칸·근거 줄 참조·비교 상태 | `valueRow, pickSilverOnly` | S02 source-values | 3 | `sourceValueButton`, `sourcePick`: 결과·정답·정답 전용 값 대조 |
| I43 | 선택한 값/줄·연결 값 수·근거 없음·좌표 없는 줄·스크롤 위치 | `noteSel, pickValue, pickLine, scrollInto` | S02 source-selection | 3 | `sourceRenderSelection`, `sourcePickLine`, `sourceScrollLine`, `sourceRemember`: 선택·근거 없음·좌표 없음·쪽과 읽던 위치 |
| I44 | 모델 선택·연결·다시 조회·기술 태그 | `modelSelect, connNote, loadOptions` | 공통 global-context, S03 jobs-connection, S06 servers-models | 1, 5, 6 | `serversRenderCompact`: S03 jobs-connection: serversRenderCompact + 기존 확인 동작 재사용. 모델 없음에도 같은 화면에서 터널/모델 준비. |
| I45 | 문서·입력 폴더·한 항/여러 항/전체 16항·기준 실행 자동/수동 | `renderJobTry` | S03 jobs-try | 6 | `jobsRenderTry`: S03 jobsRenderTry: 공통 set, runnable.try, 기준 실행과 1~16항 범위. |
| I46 | 지시문 기본/고쳐 쓰기·불러오기·다른 모델/항에서 온 글·한 항 제한 | `renderJobTry, loadPrompt` | S03 jobs-try | 6 | `jobsLoadPrompt`: S03 jobsLoadPrompt: 한 항만 조회/편집, 늦은 응답과 다른 출처 표시. |
| I47 | 지시문 임시 보관·새로고침 유실·전송 뒤 임시 파일 삭제·해시만 기록 | `renderJobTry, startTry` | S03 jobs-try, S07 help-topics | 6, 8 | `jobsRenderTry`: S03 지시문 위와 jobs-prompt-origin 펼침. 메모리만 보관. |
| I48 | 모델 미호출 연습(dry-run)·실제 보내기·연결 없음 안내 | `renderJobTry, startTry` | S03 jobs-try | 6 | `jobsStartTry`: S03 jobsStartTry: 연습/실제 구분, set/key 전송. |
| I49 | 결과 선택·작업 번호·완료 대기·결과 JSON 없음·저장 경로 | `renderJobResult, loadResult, watchTry` | S03 jobs-result, S05 jobs-detail | 6 | `jobsWatch`: S03 jobsWatch/jobsLoadResult: 세 모양·204·조회 오류 구분. |
| I50 | ① 입력: 문서·모델·폴더·분할법·MSDS 수·첫 자료만·항·형식·줄 머리·구간·쪽·이미지·경고 | `tryStages ①` | S03 jobs-result 입력 | 6 | `jobsRenderResult`: S03 jobs-stage-<id>-0: 입력과 분할·줄·이미지·경고. |
| I51 | ② 지시문: 항별 해시·수정 여부·전문 비기록 | `tryStages ②` | S03 jobs-result 지시문 기록 | 6 | `jobsRenderResult`: S03 jobs-stage-<id>-1: 항별 해시·수정 여부, 전문 비기록. |
| I52 | ③ 모델 원문 답·방식·종료 이유·시간·응답 없음 | `tryStages ③` | S03 jobs-result 원래 답 | 6 | `jobsRenderResult`: S03 jobs-stage-<id>-2: 원래 답·방식·종료 이유·시간. |
| I53 | ④ 읽은 결과: 성공·버린 줄·재추출·시도·입출력 토큰·오류·줄 검사·읽은 JSON | `tryStages ④` | S03 jobs-result 해석한 값 | 6 | `jobsRenderResult`: S03 jobs-stage-<id>-3: 읽은 값·오류·줄 검사·토큰·재추출. |
| I54 | ⑤ 최종 칸의 표 행 수·객체 칸 수·해당 항 서술/남는 값 | `tryStages ⑤` | S03 jobs-result 최종 형식 | 6 | `jobsRenderResult`: S03 jobs-stage-<id>-4: 항별 최종 칸 수. |
| I55 | ⑥ 총점 전후·기준 실행·바뀐 항목·점수 생략 사유·경고 | `scoreView, tryStages ⑥` | S03 jobs-result 점수 전후 | 6 | `jobsScore`: S03 jobsScore: target.key.label, 점수 전후·바뀐 기준·생략·경고. |
| I56 | 문서 전체의 성공/실패 항·재추출·시간·원문 답 폴더 연결 | `tryStages 문서 전체 갈래` | S03 jobs-result 전체 결과 | 6 | `jobsRenderResult`: S03 문서 전체 분기: run 수치, summary 원문, 저장 raw 경로와 S02 연결. |
| I57 | 연습에는 ③~⑥이 없음 | `tryStages 연습 갈래` | S03 jobs-result 연습 결과 | 6 | `jobsRenderResult`: S03 연습 분기: 입력/지시문 2단계, 실제 성공으로 세지 않음. |
| I58 | 본 실행 모델·입력·문서 모두/없음·선택 수·반복·이름·추천 이름·회차 접미사 | `renderJobRun, suggestName` | S09 jobs-run | 6 | `jobsRenderRun`: S09 jobsRenderRun: runnable.run·전체/비우기·1~10회·이름 제안. |
| I59 | 개발 전체/탐색 이름 규칙·자동 기준 실행·잠자기 방지·서버가 요구하는 확인·시작 상태 | `renderJobRun, startRun` | S09 jobs-run, P02 action-confirm | 6 | `jobsStartRun`: S09 jobsStartRun + P02 action-confirm: 409 요약과 조건 사본을 확인, 중복 실행 방지. |
| I60 | 비교표 선택 순서·실행별 이름·선택 수·목록 갱신·제목·기본 라벨·출력 경로 | `renderJobCompare, startCompare` | S10 jobs-compare, S05 jobs-detail | 6 | `jobsRenderCompare`: S10 jobsRenderCompare/jobsStartCompare: 순서·이름표·제목, 기본 정답지 제한. S05 결과 경로. |
| I61 | 작업 종류·내용·시작·상태·회차 진행·외부 프로세스·중단 가능 여부 | `renderJobList, progressText` | S05 jobs-list | 6 | `jobsRenderList`: S05 jobsRenderList: target 기준 조건·상태·진행·외부 작업·stoppable. |
| I62 | 작업 결과·로그·닫기·종료 코드·스크롤 유지·갱신·중단 경고 | `openLog, refreshLog, stopJob` | S05 jobs-detail, P02 action-confirm | 6 | `jobsOpenLog`: S05 jobsOpenLog/jobsRefreshLog + P02: 로그 스크롤·원문 코드·키보드 확인/취소·중단. |
| I63 | 현재 연결 모델·태그·조회 시각·재조회·서버 작업 진행과 마지막 결과 | `renderSrvTop, pollServers` | 공통 global-context, S06 servers-summary | 1, 5 | `serversRenderSummary`, `shellPollServers`·`shellScheduleServers` 한 타이머. S06 10초, 다른 화면 60초. |
| I64 | 세션 Pod 번호·준비 여부·자동 삭제 감시·작업에 전달되는 연결 | `renderSrvTop, srvDetail` | S06 servers-summary·servers-runpod | 5 | `serversRenderRunpod`: session 번호·adopted·others·실제 모델 일치·설정 변수 이름. 주소·키 값은 미표시. |
| I65 | 태그·기대 모델·서버 종류·주소 설정 여부·응답 여부·응답 모델·일치·오류 | `renderSrvModels` | S06 servers-models | 5 | `serversRenderModels`: 기대·응답 모델·태그·서버·주소 설정 유무·일치 여부·friendly 원문 펼침. |
| I66 | 서버 변경 잠금·잠긴 이유·최신 조회 실패의 조작 금지 | `srvBtn, lockNote` | S06 servers-summary | 5 | `serversReason`·`serversLockNote`: can/why·409 작업·최신 조회 실패. 터널 열기만 실행 중 허용. |
| I67 | Pod ID·이름·앱 소유 여부·상태·자동 삭제까지·시간당 요금·가동시간·추정 비용 | `renderSrvRunpod` | S06 servers-runpod | 5 | `serversRenderRunpod`: owned/deletable별 삭제 단추 미생성, uptime_s 시간·분, cost_est 달러, 비용 없음은 알 수 없음. |
| I68 | Pod 생성·삭제·계정 오류·네트워크 볼륨 수와 비용 | `renderSrvRunpod` | S06 servers-runpod, P02 action-confirm | 5 | `serversRenderRunpod`·`serversPropose`·P02: 생성·삭제·계정 오류·볼륨 수·잔여 비용 경고. |
| I69 | RNGD 카드 수·실행 모델·프로세스·사용 카드·올릴 모델 선택·올리기/내리기 | `renderSrvRngd` | S06 servers-rngd | 5 | `serversRenderRngd`: 선택 모델·카드 수·프로세스·올리기/내리기. 장비 출력은 펼침. |
| I70 | 가린 장비 명령 출력·진단 오류·15~25분 대기·프로세스와 준비 완료의 차이 | `renderSrvRngd, srvDetail` | S06 servers-rngd | 5 | `serversDiagnosis`: 진단 네 가지·진단 불가·loading_since 경과·15~25분. 준비는 기대 모델 응답으로 판정. |
| I71 | 서버 기록 마지막 10줄·기록 경로·수동 사용기록 이관 안내 | `renderSrvLog` | S06 servers-log, S07 help-topics | 5, 8 | `serversRenderLog`: 최근 10줄·실제 server_log.md·기록이 있을 때만 수동 이관 안내. helpRenderTopics의 servers 장에 연결. |
| I72 | 변경 요약·주의·확인 만료·한 번 사용·취소·실패·삭제 후 남은 Pod·모델 내린 PID | `openSrvDialog, closeSrvDialog, srvExecute` | P02 action-confirm, S06 servers-summary | 5 | `serversOpenDialog`·`serversExecute`·`serversResult`: 요약·경고·포커스·Escape·만료·일회용·실패 상세·남은 Pod/PID. |
| I73 | 도움말 전체 9장·장 링크·안내 재시작 | `index.html #help-frame, guide.html #s1~#s9` | S07 help-topics, S08 journey-choice | 7, 8 | `helpRenderTopics`: `js/help.js` → S07 `#help-topics`의 9개 details, `/static/guide.html#<장>`; `#help-replay` → S08(성공 기록 유지) |
| I74 | 도구 역할·PDF→쪽 글자→16항→결과→채점·실행 이름 해설 | `guide.html #s1` | S07 help-topics flow | 8 | `helpRenderTopics`: `#help-flow`, `guide.html#flow`; 실행 이름·처리 순서·새 안내 기록 설명 |
| I75 | 점수 해석·가중치·필수 목표·정답 초안 한계·원인 후보 기준 | `guide.html #s2, #s3` | S07 help-topics score | 8 | `helpRenderMethods`: `#help-score`, `#help-methods`, `guide.html#score`; 23개 방법·목표·무게·원인 후보·정답 초안 한계 |
| I76 | 설정 변수 6개의 이름과 뜻·예제 파일·로컬 앱 시작 명령 | `guide.html #s4` | S07 help-topics setup | 8 | `helpRenderTopics`: `#help-setup`, `guide.html#setup`; 변수 6개·앱 명령·RunPod 프록시와 RNGD SSH 구분 |
| I77 | 시험 순서·6단계 뜻·터미널 실행과 7개 옵션 | `guide.html #s5` | S07 help-topics retest | 8 | `helpRenderTopics`: `#help-retest`, `guide.html#retest`; 여섯 단계 표·CLI 명령·옵션 7개 |
| I78 | 지시문 출처 3곳·수정 반영 파일·버전 증가·해시·임시성·반복 시험 | `guide.html #s6` | S07 help-topics prompt | 8 | `helpRenderTopics`: `#help-prompt`, `guide.html#prompt`; 출처 3곳·수정 파일·버전·임시성·반복 확인 |
| I79 | 출력 한도 원인 3종·열 수 불일치·300초 초과·연결 오류 | `guide.html #s7` | S07 help-topics recovery | 8 | `helpRenderTopics`: `#help-recovery`, `guide.html#recovery`; 출력 한도 3유형·열 수·300초·연결 복구 |
| I80 | 평가 보호·비밀값 보호·문서 보호·Pod 비용·전처리 시험 제외 명령 | `guide.html #s8` | S07 help-topics protection | 8 | `helpRenderTopics`: `#help-protection`, `guide.html#protection`; 평가·키·자료·docs 보호·C 전처리 시험 제외 명령; 비용은 servers 장 |
| I81 | 용어 뜻·예, 용어 로딩 실패, 채점 항목 23개의 이름·등급·설명 | `guide.html #s9, /api/glossary` | S07 help-glossary | 8 | `helpRenderGlossary`: `#help-glossary`의 40개 용어·별칭 검색·조회 복구, `#help-methods`의 23개 채점 방법 |
| I82 | 값 말풍선의 쉬운 칸 이름과 알려지지 않은 값과 0·false 보존 | `valueRow, tipOf` | S02 source-values | 3 | `sourceTip`, `sourceValueButton`: API의 한국어 말풍선·키보드 접근 |
| I83 | 결과·정답·정답에만 있는 값의 원래 JSON과 안전한 글자 표시 | `noteSel, pickValue, pickSilverOnly` | S02 source-selection | 3 | `sourceRenderSelection`의 `details.source-raw`: 세 종류 JSON을 글자 노드로 보존 |
| I84 | 조회 실패의 사실·할 일·접힌 원문과 불러오는 중 표시 | `loadFailure, friendlyError, rawError` | 공통 오류 → 각 화면 상태 구역 | 1, 9 | `friendlyError`: 굵은 사실·할 일·기본으로 닫힌 원문. rawError/loadFailure와 go의 상태 글. 10화면 API 실패·불러오는 중·표시 완료 시험. |
| I85 | 원문 범례의 네 상태와 색·글과 선택 구간 요약 | `renderDocMain, renderDocRight` | S02 source-top·source-values | 3 | `sourceRenderTop`의 API 범례와 `sourceStructure`의 API 항 요약 |
| I86 | 도움말 1장: 이 도구는 무엇을 하나 | `guide.html #s1` | S07 help-topics: help.guide.flow | 8 | `helpRenderTopics`: `#help-flow`, `guide.html#flow` |
| I87 | 도움말 2장: 점수는 어떻게 읽나 | `guide.html #s2` | S07 help-topics: help.guide.score | 8 | `helpRenderTopics`: `#help-score`, `guide.html#score` |
| I88 | 도움말 3장: 탭마다 무엇을 보나 | `guide.html #s3` | S07 help-topics: flow·source·retest·servers와 S08 링크 | 8 | `helpRenderTopics`: flow의 처리·안내, score/source/retest/servers 장, 각 화면 아래 문맥 연결 |
| I89 | 도움말 4장: 처음 한 번 준비 | `guide.html #s4` | S07 help-topics: help.guide.setup | 8 | `helpRenderTopics`: `#help-setup`, `guide.html#setup` |
| I90 | 도움말 5장: 시험 하나 돌리기 | `guide.html #s5` | S07 help-topics: help.guide.retest | 8 | `helpRenderTopics`: `#help-retest`, `guide.html#retest` |
| I91 | 도움말 6장: 안내문을 바꿔 보기 | `guide.html #s6` | S07 help-topics: help.guide.prompt | 8 | `helpRenderTopics`: `#help-prompt`, `guide.html#prompt` |
| I92 | 도움말 7장: 자주 보는 실패 네 가지 | `guide.html #s7` | S07 help-topics: help.guide.recovery | 8 | `helpRenderTopics`: `#help-recovery`, `guide.html#recovery` |
| I93 | 도움말 8장: 하지 말 것 | `guide.html #s8` | S07 help-topics: help.guide.protection | 8 | `helpRenderTopics`: `#help-protection`, `guide.html#protection` |
| I94 | 도움말 9장: 용어 풀이와 채점 항목 23개 | `guide.html #s9, /api/glossary` | S07 help-glossary와 help-topics score | 8 | `helpRenderGlossary`: S07 `#help-glossary`·`#help-methods`, guide 용어 목록·score 장의 23개 방법 표 |

## 옛 시험 옮기기

파일 경로의 기준은 `backend/tests/`입니다.
행마다 원래 지키던 행동을 새 시험으로 먼저 옮깁니다.
단순히 현재 시험을 통과시키기 위해 기대값을 바꾸지 않습니다.
새 설계가 바꾸는 첫 진입과 기록 저장 방식은 아래에 구분했습니다.

| 옛 시험(파일::함수) | 지키던 행동 | 새 시험 파일 | 지우는 step |
|---|---|---|---|
| `test_B_b_app_score_ui.py::test_connection_banner_renders_server_copy_and_reserves_red_for_errors` | 연결 없음과 조회 중은 정상 안내. 조회 실패만 오류 색. API가 준 글 사용 | `test_B_b_app_shell_ui.py` | 1에서 이관, 2에서 원본 교체 |
| `test_B_b_app_score_ui.py::test_score_status_card_and_filter_preserve_all_values` | 상태 요약과 원인과 다음 행동 표시. 미달/모두 필터가 행을 보존. 원문 이동 대상 유지 | `test_B_b_app_score_ui.py` | 2 |
| `test_B_b_app_score_ui.py::test_score_collapsed_cards_keep_content_state_and_work_without_storage` | 접힘 상태와 본문 보존. 저장 실패와 깨진 저장값에도 조작 가능 | `test_B_b_app_shell_ui.py` | 1에서 이관, 2에서 원본 교체 |
| `test_B_b_app_score_ui.py::test_score_source_jump_selects_run_and_section_after_document_load` | 원문 데이터를 읽은 뒤 실행·문서·항 선택. 이동한 조작 요소에 초점 | `test_B_b_app_score_ui.py` | 2; 실제 S02 연결 3 |
| `test_B_b_app_score_ui.py::test_score_loading_displays_count_before_scoring_finishes` | 채점 완료 전 실행 개수 표시. 완료 후 로딩 글 제거 | `test_B_b_app_score_ui.py` | 2 |
| `test_B_b_app_diff_doc_ui.py::test_doc_value_tooltips_and_raw_json_for_both_sides_and_silver_only` | 결과·정답·정답 전용 값의 말풍선과 JSON 표시. HTML을 글자로 처리 | `test_B_b_app_source_ui.py` | 3 |
| `test_B_b_app_diff_doc_ui.py::test_diff_filter_retains_all_rows_and_candidate_reasons` | 하락/모두 필터가 모든 행을 보존. 숨긴 수와 후보 이유 순서 표시 | `test_B_b_app_compare_ui.py` | 4; 파일 삭제 |
| `test_B_b_app_diff_doc_ui.py::test_diff_server_headline_leads_controls_and_uses_direction_class` | API 결론이 선택기보다 먼저 보임. 비교 방향 class와 글 보존 | `test_B_b_app_compare_ui.py` | 4; 파일 삭제 |
| `test_B_b_app_diff_doc_ui.py::test_doc_first_open_uses_current_score_then_preserves_manual_selection` | 처음 원문은 현재 실행을 사용. 직접 고른 문서 유지. 새 실행에서 무효 선택 해제 | `test_B_b_app_source_ui.py` | 3 |
| `test_B_b_app_diff_doc_ui.py::test_doc_chips_use_api_colors_and_section_summary` | 범례는 API 색과 글을 함께 사용. 항별 다른 값과 누락 수 설명 | `test_B_b_app_source_ui.py` | 3 |
| `test_B_b_app_jobs_ui.py::test_jobs_try_offline_recovery_and_explicit_preview_choice` | 연결 없이 연습 가능. 실제 실행은 준비 전 제한. 사용자가 택한 연습은 복구 후 유지. 모델 없으면 전송 불가 | `test_B_b_app_jobs_ui.py` | 6; 파일 교체 |
| `test_B_b_app_jobs_ui.py::test_jobs_poll_refreshes_options_keeps_edits_and_more_state` | 옵션 갱신은 지시문 편집과 선택과 이름과 접힘을 유지. 같은 옵션이면 입력 DOM 유지 | `test_B_b_app_jobs_ui.py` | 6; 파일 교체 |
| `test_B_b_app_jobs_ui.py::test_jobs_four_steps_field_help_and_six_result_descriptions` | 시험 준비 순서와 필드별 도움말과 결과 여섯 단계 설명 보존 | `test_B_b_app_jobs_ui.py` | 6; 파일 교체 |
| `test_B_b_app_start_ui.py::test_start_optional_children_never_render_null` | 선택적 자식이 없어도 null·undefined·false 글자가 노출되지 않음 | `test_B_b_app_journey_ui.py` | 7 이관 완료; 옛 파일 삭제 |
| `test_B_b_app_start_ui.py::test_start_state_restore_reset_and_storage_denied` | 해시 우선과 저장 실패 복구 보존. 첫 화면은 S01 띠로 변경. 재시작은 v2 성공 기록 보존으로 교체 | `test_B_b_app_journey_ui.py` | 7 이관 완료; 옛 파일 삭제 |
| `test_B_b_app_start_ui.py::test_start_score_requires_loaded_visible_current_run` | 현재 실행의 점수가 실제 보이는 상태에서만 안내 단계 진전 | `test_B_b_app_journey_ui.py` | 7 이관 완료; 옛 파일 삭제 |
| `test_B_b_app_start_ui.py::test_start_tabs_hash_advanced_status_link_and_help_replay` | 해시 이동과 상태 링크와 도움말 재시작 유지. 서버 숨김은 승인에 따라 제거 | `test_B_b_app_journey_ui.py` | 7 이관 완료; 옛 파일 삭제 |
| `test_B_b_app_start_ui.py::test_start_navigation_buttons_never_complete_and_no_drops_offer_diff` | 이동 단추 클릭만으로 완료하지 않음. 실행 없음과 문제 없음에도 정직한 다음 행동 | `test_B_b_app_journey_ui.py` | 7 이관 완료; 옛 파일 삭제 |
| `test_B_b_app_start_ui.py::test_start_success_needs_mismatched_value_in_selected_section_and_rendered_line` | 고른 항의 다른 값과 실제 표시된 근거 줄이 함께 선택되어야 성공. 중복 열기는 최초 시각 보존 | `test_B_b_app_journey_ui.py` | 7 이관 완료; 옛 파일 삭제 |
| `test_B_b_app_polish_ui.py::test_server_log_copy_instruction_only_appears_with_lines` | 서버 기록이 있을 때만 수동 이관 안내. 없으면 빈 상태 | `test_B_b_app_servers_ui.py` | 5 |
| `test_B_b_app_polish_ui.py::test_item_toggle_is_button_and_preserves_focus_and_expansion` | 항목 펼침은 button과 aria-expanded. 펼침 후 초점과 상세 보존 | `test_B_b_app_score_ui.py` | 2 |
| `test_B_b_app_polish_ui.py::test_changed_values_toggle_is_button_and_keeps_both_lists` | 바뀐 값 펼침은 button. 초점 유지. 고친 값과 새로 틀린 값 두 목록 보존 | `test_B_b_app_compare_ui.py` | 4 |
| `test_B_b_app_polish_ui.py::test_history_points_are_buttons_and_storage_denial_keeps_selection` | 이력의 점은 키보드 button과 aria-pressed. 저장 거부에도 선택과 초점 유지 | `test_B_b_app_score_ui.py` | 2 |
| `test_B_b_app_polish_ui.py::test_source_lines_are_buttons_with_selection_and_no_page_is_empty` | 원문 줄은 button. 선택 상태 표시. 그림 대체 글. 쪽 없음도 빈 화면으로 두지 않음 | `test_B_b_app_source_ui.py` | 3 |
| `test_B_b_app_polish_ui.py::test_grid_states_and_silver_status_have_visible_text` | 호출 실패·재추출·기록 없음과 정답 비교 상태에 글 표시 | `test_B_b_app_score_ui.py`<br>`test_B_b_app_source_ui.py` | 2 격자 이관, 3 나머지 이관 후 삭제 |
| `test_B_b_app_polish_ui.py::test_errors_share_fact_action_and_collapsed_raw_on_each_tab` | 모든 화면 오류에 사실·할 일·접힌 원문. 원문 글자 그대로 안전하게 표시 | `test_B_b_app_audit_ui.py` | 9; 파일 삭제 |
| `test_B_b_app_polish_ui.py::test_tooltip_targets_get_keyboard_access_without_nested_tab_stops` | 독립 말풍선은 키보드로 접근. 단추 안에 중복 tab 정지점 금지 | `test_B_b_app_shell_ui.py` | 1 |
| `test_B_b_app_polish_ui.py::test_start_pending_and_jobs_refresh_error_do_not_leave_blank_or_stale_states` | 안내 로딩을 빈 화면으로 두지 않음. 옵션 갱신 오류가 나면 오래된 양식을 그대로 내보내지 않음 | `test_B_b_app_journey_ui.py`<br>`test_B_b_app_jobs_ui.py` | 6 jobs 부분 이관 확인, 7 시작 부분 이관·삭제 완료 |
| `test_B_b_app_polish_ui.py::test_start_shows_run_list_failure_after_guide_has_loaded` | 안내가 먼저 로드돼도 실행 목록 조회 실패를 사실·할 일로 표시 | `test_B_b_app_journey_ui.py` | 7 이관 완료 |
| `test_B_b_app_polish_ui.py::test_tooltip_keyboard_escape_and_pointer_transfer` | 말풍선은 포커스와 포인터로 열림. Escape로 닫힘. 포인터가 말풍선으로 옮겨가도 유지 | `test_B_b_app_shell_ui.py` | 1 |
| `test_B_b_app_polish_ui.py::test_options_poll_reports_failure_and_same_data_recovery_as_state_changes` | 옵션 실패와 같은 데이터로 복구도 상태 변화로 처리. 오류 해제 후 정상 갱신 | `test_B_b_app_jobs_ui.py` | 6 |
| `test_B_b_app.py::test_index` | 탭 이름 확인을 새 화면 뼈대 id 확인으로 교체. 메뉴 글은 JS 화면 시험에서 확인 | `test_B_b_app.py` | 1 |
| `test_B_b_app.py::test_static` | JS·CSS 정적 제공과 콘텐츠 형식 유지. 새 core.js 경로로 확인 | `test_B_b_app.py` | 1 |
| `test_B_b_app.py::test_static_start_entry_and_replay` | 첫 사용 진입과 재시작 링크 유지. 옛 start 우선 구조는 S01 안내 띠로 교체 | `test_B_b_app.py` | 1 |
| `test_B_b_app.py::test_index_has_help_tab_and_links` | 도움말에 도달할 수 있는 경로 유지. 화면별 장 링크는 새 구조로 검사 | `test_B_b_app.py / test_B_b_app_help_ui.py` | 1; 장 연결 8 |
| `test_B_b_app.py::STATIC_FILES` | 외부 주소 금지 대상에 js/*.js 추가. app.js는 삭제 전까지 검사 | `test_B_b_app.py` | 1 확장, 9 app.js 제외 |
| `test_B_b_app.py::GUIDE_SECTIONS / test_guide_route_has_all_sections` | 도움말 9장 전체 제공과 순서 보존. 제목은 COPY의 새 9장으로 변경 | `test_B_b_app.py / test_B_b_app_help_ui.py` | 8 |

step 1은 옛 DOM 대역을 `test_B_b_app_dom.py`의 `OLD_DOM`과 `run_old_js`로 옮깁니다.
옛 시험의 import만 새 대역으로 바꿉니다.
step 2가 옛 score 파일을 다시 쓰기 전까지 그 시험 함수는 유지합니다.
step 9가 `run_old_js`와 옛 `app.js`와 남은 polish 파일을 제거합니다.
`test_B_b_app_text.py`의 계산과 계약 시험은 유지합니다.
COPY 문장으로 바꾼 기대값은 해당 step의 summary에 이유를 적습니다.
범례 색 기대값은 step 1에서 실제 적용한 토큰과 함께 변경 이유를 적습니다.
정적 경로 보호와 HTML 문자 이스케이프와 외부 주소 금지 시험은 계속 유지합니다.

## API 확인

step 5에서 서버 계약을 다시 확인했습니다. 백엔드 파일은 수정하지 않았습니다.

| 계약 | 코드 확인 | 화면 처리 |
|---|---|---|
| 공통 조회 | `ServerManager.status`, `/api/servers` | `S.shell.servers` 하나를 S06·맥락 줄·짧은 연결 구역이 공유. 조회 중 요청은 합침. 기존 15초 주기는 이 step 요구대로 S06 10초/다른 화면 60초 한 타이머로 변경 |
| 시간·비용 | `_brief`, `_pod_view` | `uptime_s` 초를 시간·분으로 표시. `cost_est` 달러, `cost_per_hr` 달러/시간. null은 알 수 없음. `auto_delete_min`이 있을 때만 남은 분 표시 |
| 제안·실행 | `propose`, `execute`, `_server_post` | `post`는 `{status,data}` 포장이 아닌 본문을 반환. HTTP 오류는 `error.status/body`. 토큰 600초·일회용. 터널도 승인 구조에 따라 P02 확인 |
| 실행 중 잠금 | `_locked`, `server_controls` | 409의 `running`과 상태의 `running_jobs`를 구분. 여는 통로만 예외. 열린 확인 창에도 새 잠금·조회 실패를 반영 |
| 설정 다시 읽기 | `reload_env` | names/changed/removed는 변수 이름만. problems는 줄 번호·사실·할 일. 앞선 상태 조회가 진행 중이면 끝난 뒤 새 상태를 다시 조회 |
| 실행 결과 실패 | `_do_pod_delete`, `_do_rngd_up/down` | HTTP 200이어도 `ok:false`일 수 있음. `result`·`log_line`을 보존해 남은 자원과 실패를 표시 |
| 서버 기록 | `_log_tail(10)` | 실제 경로는 `runs/manual/server_log.md`. COPY의 server-events.log 시안 경로는 사용하지 않음 |


코드 위치의 기준은 `backend/scripts/`입니다.
통신 규약(API)은 현재 코드의 실제 반환값을 기준으로 확인했습니다.
코드 확인과 실제 서버 연결 확인은 다릅니다.
이 step에서는 모델 서버와 SSH를 호출하지 않았습니다.
`있음`은 코드에 있는 계약입니다.
`다름`은 상위 표보다 실제 조건이나 모양이 넓거나 좁은 경우입니다.
`빈칸`은 설계가 필요로 하지만 해당 응답에 없는 값입니다.

| 필드 | 코드에서 찾은 곳 | 정확한 이름·값 | 쓰는 step | 상태 |
|---|---|---|---|---|
| `GET /api/sets` | `b_app.py:420`, `b_app_sets.py:105` | `{sets,default}`. 각 묶음은 `id,label,path,usable,reason,counts,docs`. 기본 후보는 `prev/version9`. 시작 인자가 우선 | 1, 3, 6 | 있음 |
| `sets[].counts` | `b_app_sets.py:32`, `:108` | `dev,eval_locked,other,outside,unknown` 다섯 키. 없음은 0 | 1, 6 | 있음 |
| `sets[].docs[]` | `b_app_sets.py:78` | `doc_id,group,locked,reason,pages,line_numbers`. group은 `dev,eval,other,outside,unknown`. 잠긴 문서는 `line_numbers:null` | 1, 3, 6 | 있음 |
| 묶음 사용 불가 이유 | `b_app_sets.py:93`, `b_app_text.py:679` | 빈 폴더, 평가만, 전부 잠김, 줄 번호 없음. 문서 `reason`은 잠긴 이유이고 작업 불가 이유와 다름 | 1, 6 | 있음 |
| `GET /api/keys` | `b_app.py:429`, `b_app_sets.py:240` | `{keys,default}`. `id,label,kind,path,usable,reason,docs,counts,fingerprint,updated_at`. 목록 kind는 `silver` 또는 `gold` | 1 | 있음 |
| 정답지 유효성·기본 | `b_app_sets.py:220`, `:240`, `:293` | 문서별 JSON에 `msds` 목록 필요. 평가 파일 제외. `counts={docs,eval_locked,outside}`. 기본 후보 `silver/claude`; 시작 폴더 우선 | 1 | 있음 |
| 점수 요청의 `key` | `b_app.py:133`, `:617`, `:625`, `:634` | runs·run·diff는 쿼리 `key`를 받음. 응답 `key={id,label,fingerprint}`. 생략 시 앱 시작 정답지. 없는 id 404, 사용 불가 400 | 1, 2, 4 | 있음 |
| `run_kind` | `b_app_runs.py:177` | `models,silver,eval,outside,single,probe,dev10`. 옛 `kind=run/manual/models`와 다름 | 2, 4, 6 | 있음 |
| `comparable`·기본 실행 | `b_app_runs.py:266`, `b_app.py:214`, `b_app_text.py:603` | `run_kind==dev10`이고 점수 있음. 현재 실행과 최고 점수 후보는 silver 제외. 그 밖의 실행은 선택 목록에서 보존 | 2, 4 | 있음 |
| `targets` | `b_app_text.py:544`, `b_app.py:175`, `:195`, `:650` | `{weighted:{line,value,met},must:{total,met_count,met}}` 또는 null. diff는 `{a:targets,b:targets}`. 90·17 하드코딩 금지 | 2, 4 | 있음 |
| `same_conditions` | `b_app_diff.py:81`, `:101`, `:244` | 객체가 아니라 bool. 모델·프롬프트 버전·입력·동시 수·코드 커밋과 공통 항의 프롬프트 해시와 채점 문서 집합이 같아야 참 | 4 | 있음 |
| 비교 조건과 범위 | `b_app_diff.py:251` | `conditions[{what,a,b,changed}]`, `prompt_changed_sections`, `docs{common,only_a,only_b}`. 누락된 메타를 새로 입증해 주지는 않음 | 4 | 있음 |
| `/api/silver_gaps` | `b_app.py:435` | key 없음은 배열. key 있음은 `{key,gaps}`. `silver/claude` 외 정답지는 `gaps:[]` | 2 | 있음 |
| `/api/doc` 인자 | `b_app.py:329` | `doc` 필수. `run,set,key` 선택. run 생략은 원문 전용이며 결과 값과 정답 값은 빈 배열 | 3 | 있음 |
| 원문 묶음 선택 | `b_app.py:292`, `b_app_sets.py:142` | 명시 set → 실행 기록 → 시작 폴더 → 기본 묶음. 옛 `data/pages/version9`는 `prev/version9`로 해석 가능. 최초 요청에 전역 set을 강제로 붙이지 않음 | 3 | 있음 |
| 원문 응답 `set` | `b_app.py:298`, `:320`, `:357` | `{id,label,source,note}`. source는 `param,run,moved,startup,default`. 실행 목록의 set.source와 다른 값 목록 | 3 | 있음 |
| `image_base,image_query`·그림 `?set=` | `b_app.py:272`, `:357` | `image_base=/pages/<doc>/`, `image_query=?set=<인코딩한 id>` 또는 빈 글. 그림 파일은 `pNNN.png`. set 생략은 시작 폴더 | 3 | 있음 |
| 평가 문서 직접 조회 | `b_app.py:339`, `:349`, `:287`, `b_app_doc.py:347` | `/api/doc`와 그림 모두 404. 본문에서 평가 여부를 밝히지 않음. 잠긴 이유는 `/api/sets`의 docs.reason과 counts.eval_locked로 표시 | 1, 3, 6 | 있음 |
| `/api/options` | `b_app.py:374`, `:382` | `sets,default_set,outside_run_support` 추가. 옛 `docs,pages_dirs,default_pages_dir` 유지 | 1, 6 | 있음 |
| `runnable`·`run_reason` | `b_app.py:376`, `b_app_sets.py:189` | 문서별 `{try,run}`. 개발 문서는 줄 번호가 있어야 함. manifest 밖은 try 거짓. run은 `doc_meta_from_pages` 존재 시만 참 | 6 | 있음 |
| 실행기 능력 | `b_app_sets.py:182`, `src/msds/extract/section_runner.py` | 현재 소스에 `doc_meta_from_pages` 정의 없음. 허용 여부는 화면이 RAW 이름으로 판정하지 않고 응답을 따름 | 6 | 있음 |
| 시험 시작의 묶음 인자 | `b_app.py:504`, `:539` | `POST /api/jobs/try` 본문 `set`. 없으면 `pages_dir`. 둘 다 있으면 set 우선. 성공 `{id}`. 모르는 set 400 | 6 | 있음 |
| 시험 시작의 나머지 인자 | `b_app.py:539`, `b_app_jobs.py:245` | `model,doc,sections,all,system_text,base_run,dry_run,key`. 수정 지시문은 한 항만. sections는 1~16 정수 목록 | 6 | 있음 |
| 시험 점수 전후의 정답지 | `b_app.py:516`, `b_app_jobs.py:275`, `try_section.py:383` | 명시 key를 `--gold-dir`로 전달. 생략은 항상 `silver/claude`. 앱 시작 정답지와 다를 수 있음. `target.key.given`으로 구분 | 6 | 있음 |
| `/api/jobs` | `b_app.py:459`, `b_app_jobs.py:423` | `{jobs,running}`. `error`는 실패 작업의 `{message,fix,raw,warnings}` 또는 null. `warnings`는 항상 목록. `dry_run`은 bool | 6, 7 | 있음 |
| 작업 상태·중단·로그 | `b_app_jobs.py:403`, `:436`, `b_app.py:459`, `:558` | `running,done,failed,stopped,unknown`. `stoppable` 따름. 로그 `{id,text}`. stop POST `{stopped}`. 외부 작업은 running에 별도 표시 | 6 | 있음 |
| `/api/servers` 설정·세션 | `b_app_servers.py:411`, `:760`, `:801` | `env_problems` 목록. session은 null 또는 `pod_id,url,tag,ready,adopted,others`. `adopted`는 기존 앱 소유 Pod 자동 이어받기 | 1, 5 | 있음 |
| Pod 소유·삭제 | `b_app_servers.py:335`, `:518`, `:824` | `owned`와 `deletable=owned and not locked`. 옛 `ours` 유지. 앱 소유 아님은 삭제 API 403. 단추는 deletable 기준 | 5 | 있음 |
| Pod 시간·비용 단위 | `pod.py:116`, `b_app_servers.py:780` | `uptime_s`는 초 정수. `cost_per_hr`는 달러/시간. `cost_est`는 달러 추정액이며 소수 두 자리. 시각·요금 모르면 null | 5 | 있음 |
| Pod 자동 삭제 표시 | `b_app_servers.py:824` | `auto_delete_min`은 이 앱이 아는 감시 작업의 남은 분. 없으면 null. 기존 Pod의 예약을 새로 추정하지 않음 | 5 | 있음 |
| RNGD 터널 | `b_app_servers.py:394` | `rngd.tunnel={port,open,owned,pid,since}`. since는 시간대 포함 로컬 ISO 초 단위. 이어받은 터널이나 닫힌 터널은 null 가능 | 5 | 있음 |
| RNGD 진단·시각 | `b_app_servers.py:312`, `:744`, `b_app_text.py:949` | `diagnosis=ok/no_model/tunnel_closed/loading` 외에 null 가능. `loading_since`는 로컬 ISO 초 단위 또는 null. `diagnosis_text={message,fix}` 또는 null | 5 | 다름 |
| 설정 다시 읽기 | `b_app.py:485`, `b_app_servers.py:492` | `POST /api/servers/reload_env`. 성공 `{ok:true,names,changed,removed,problems}`. 목록은 변수 이름·문제 줄 정보. 실패 `{ok:false,error}`. 키 값 없음. 확인 토큰 없음 | 5 | 있음 |
| 서버 확인 두 단계 | `b_app_servers.py:451`, `:473`, `:276` | propose `{action,params}` → `{token,action,summary,warning,expires_in:600}`. execute `{token}`. 일회용. 만료 410, 틀린 토큰 400 | 5 | 있음 |
| `tunnel_open,tunnel_close` | `b_app_servers.py:262`, `:451`, `:561` | 둘 다 propose → execute. 여는 동작만 실행 중 허용. 닫기는 실행 중 409. 소유 터널 조건도 다시 검사 | 5 | 있음 |
| `status_text.losses` | `b_app_text.py:520` | 각 행 `name,level,weight,score,target,loss,below_target,section,rank`. score·target은 100점 단위. 숫자 점수가 있는 항만 포함. 미채점은 빈 목록이라 항상 23행은 아님 | 2 | 다름 |
| `top_problem`·`loss_basis` | `b_app_text.py:511`, `:538`, `b_app.py:194` | `top_problem=losses[0]+docs[{doc_id,score,loss}]` 또는 null. docs는 문서 손실 내림차순. `loss_basis={weight_total,loss_total}` 또는 null | 2, 3, 7 | 있음 |
| 손실 계산·동점 | `b_app_text.py:528`, `:535` | 손실은 무게×(1−항목점수)/무게합×100. 목표 이상도 포함. 동점은 criteria 순서. `top_drops`는 예전 목표 미달 순위로 유지 | 2 | 있음 |
| 실행의 `set` | `b_app.py:168`, `b_app_sets.py:162` | `{id,label,source,usable,missing_docs}`. source `run,moved,none,mixed`. 비교표 또는 읽기 실패 실행은 set null | 1, 2, 4 | 있음 |
| 채점 범위 | `b_app_runs.py:221` | `docs`는 채점된 문서, `no_gold`는 정답 없는 출력, `excluded`는 보호·용도 불명 문서. 모두 문서 ID 목록 | 2, 4 | 있음 |
| 정답지 지문·수정 시각 | `b_app_sets.py:230`, `:240` | 평가용 아닌 유효 답 파일의 이름·길이·바이트를 문서 순으로 sha256. `fingerprint`는 앞 16자. `updated_at`은 가장 늦은 수정 시각의 로컬 ISO 또는 null | 1 | 있음 |
| 개별 응답 `key.updated_at` | `b_app.py:133`, `:516` | `_pick_key`는 id·label·fingerprint만 반환. updated_at은 `/api/keys`에서 같은 id로 찾아 현재 폴더 시각으로만 표시. 과거 기록에 붙이지 않음 | 1, 2, 4, 6 | 빈칸 |
| `values[].items`·`silver_only[].items` | `b_app_doc.py:209`, `:258`, `:382` | 해당 값이 들어가는 채점 항목 이름 목록. 빈 목록 가능. 항 번호만으로 가장 큰 문제 값을 대신 고르지 않음 | 2, 3 | 있음 |
| 정답 쪽 줄 추정 | `b_app_doc.py:372` | `silver_only[].lines` 목록. `silver_lines={basis:"text_match",found,total}` 또는 null. found는 줄을 찾은 정답 값 수. 전체 정답 값 기준이며 누락 값만의 수가 아님 | 3, 7 | 있음 |
| 시험 작업 `target` | `b_app_jobs.py:285` | `{kind:"try",doc,sections,all,model,set,pages_dir,key:{id,label,fingerprint,given},base_run,dry_run,custom_prompt}`. 전체면 sections null. 옛 작업은 target null | 6, 7 | 있음 |
| 본 실행·비교표 `target` | `b_app_jobs.py:326`, `:348` | 본 실행 `{kind:"run",model,docs,set,run_names,repeat}`. 비교표 `{kind:"models",runs,title}`. 작업 자체 kind는 `compare` | 6 | 있음 |
| 연습 결과 | `try_section.py:378`, `b_app_jobs.py:500` | `/api/jobs/<id>/result` 200 `{plan}`. plan.sections 키는 글자. 실제 호출 결과 없음 | 6, 7 | 있음 |
| 항 시험 결과 | `try_section.py:419`, `test_B_b_app_jobs.py::test_route_result_shapes` | `{plan,results:{"8":{ok,…}},fields,base_run,score,score_skipped,saved}`. 항 번호 키는 글자 | 6, 7 | 있음 |
| 문서 전체 결과 | `try_section.py:356`, 같은 결과 시험 | `{plan,run,summary,score,base_run,saved}`. results 없음. 한 항 안내의 성공으로 세지 않음 | 6, 7 | 있음 |
| 결과 없음·성공 판정 | `b_app.py:474`, `test_B_b_app_jobs.py::test_route_result_none_is_204` | 결과 없음은 204와 빈 본문. done·returncode 0·dry_run 거짓·200·선택 results.ok 참·대상 일치·결과 요약 표시가 모두 필요 | 6, 7 | 있음 |
| 본 실행 확인 | `b_app.py:546` | confirm 없으면 409 `{summary,needs_confirm:true}`. 확인 후 같은 본문에 `confirm:true`를 더함. 성공 `{id,summary}` | 6 | 있음 |
| 비교표 생성의 선택 정답지 | `b_app.py:553`, `b_app_jobs.py:329`, `compare_models.py`의 gold-dir 기본값 | `POST /api/jobs/compare`는 title·runs·labels만 전달. 전역 key를 전달하지 않음. 현재 선택 정답지 기준 파일이라고 표시할 수 없음 | 6 | 빈칸 |
| journey GET·기본 v2 | `b_app.py:564`, `b_app_journey.py:34` | `{journey,problems}`. journey는 `version:2,progress,outcomes,pending,migrated_from`. 파일 없음은 기본값이며 파일 생성 없음 | 1, 7 | 있음 |
| journey progress | `b_app_journey.py:79` | `{active,dismissed_at,t1,t2}`. 갈래는 `{state,step,updated_at}`. state `not_started/in_progress/skipped/completed`; t1 step 0~3, t2 0~4 | 7 | 있음 |
| journey outcomes·pending | `b_app_journey.py:94`, `:111` | t1.real `{first_at,last_at,count}`. t2.real/practice는 last_job 추가. pending `{attempt,job,mode,started_at}` 또는 null. mode real/practice. migrated_from 1/null | 7 | 있음 |
| journey 시각·problems | `b_app_journey.py:30`, `:154` | 시각은 UTC 밀리초 `YYYY-MM-DDTHH:mm:ss.sssZ`. problems는 `{part,message}` 목록. 잘못된 부분만 기본값으로 복구 | 7 | 있음 |
| journey PUT·합치기 | `b_app.py:576`, `b_app_journey.py:181` | 본문 `{journey}`. 응답 `{journey,problems:[]}`. count 큰 값, first_at 이른 값, last_at 늦은 값. progress·pending 교체. migrated_from 1 유지 | 7 | 있음 |
| journey 오류 | `b_app.py:578`, `:591`, `:686`, `:712` | 16KB 초과·모르는 키·잘못된 JSON은 400. 설정 경로 없음 503. 읽기·쓰기 오류 500. HTTP 경계에서 비JSON·다른 Origin·다른 Host는 403. Origin 없는 로컬 JSON 요청은 허용 | 7 | 있음 |
| 문구 생성 위치 | `b_app_text.py:679`, `:708`, `:792`, `:949`; 아래 설명 | 묶음 reason·정답지 reason·작업 error·진단 설명은 주로 b_app_text. 판단 코드와 일부 원문 오류는 다른 파일에 남음 | 1~8 | 있음 |

API 빈칸은 두 개입니다.

1. 개별 응답의 `key.updated_at`입니다. `/api/keys`의 현재 수정 시각으로만 보충합니다.
2. 비교표 생성 요청의 선택 정답지입니다. 기본 정답지로 만든다는 사실을 표시합니다. 전역 정답지로 생성했다고 말하지 않습니다.

API 표와 실제 코드의 차이는 두 개입니다.

1. `rngd.diagnosis`는 조회가 불명확하면 null입니다. 기존 `friendly` 오류를 표시합니다.
2. `status_text.losses`는 점수가 없는 항을 뺍니다. 채점되지 않은 실행을 23개의 0점으로 만들지 않습니다.

예: 가짜 작업 계약 시험은 `sections:[15,8,8]`을 `target.sections:[8,15]`로 확인합니다(`test_try_target_records_conditions`).
예: 가짜 결과 계약 시험은 항 번호 8을 응답 키 `"8"`로 확인합니다(`test_route_result_shapes`).

문구를 바꿀 수 있는 경계를 구분합니다.

- 묶음과 문서의 reason은 `b_app_text.SET_TEXT`에서 옵니다. 판단은 `b_app_sets`가 합니다.
- 정답지 reason은 `b_app_text.KEY_TEXT`에서 옵니다.
- 작업 실패 문장은 `b_app_text.job_error`가 만듭니다. 키 가리기는 `b_app_jobs._log_problems`가 먼저 합니다.
- 진단 값은 `b_app_servers.diagnose_rngd`가 만듭니다. 진단 설명은 `b_app_text.rngd_diagnosis`가 만듭니다.
- `b_app.py._why_offline`의 일부 연결 이유는 파일 안의 문장입니다.
- 서버 확인 요약과 만료 오류 일부는 `b_app_servers`가 직접 만듭니다.
- 작업 입력 검사의 일부 오류와 작업 label은 `b_app_jobs`가 직접 만듭니다.
- 원문 경고는 `b_app_doc.doc_view`에도 있습니다.
- 비교 조건의 `what`과 원인 후보 설명은 `b_app_diff`에도 있습니다.

마지막 다섯 종류는 이 phase의 허용된 Python 수정 범위 밖입니다.
COPY의 제목과 복구 설명을 감싸서 표시합니다.
원래 응답은 상세에서 보존합니다.
응답 문장만 보고 새로운 성공 상태를 추측하지 않습니다.


### step 3 API 재확인

- `/api/doc`의 기본 요청에는 `key`만 공통 맥락에서 더합니다. `set`은 원문 영역의 묶음 선택이나 명시적인 원문 전용 전환 때만 보냅니다.
- `set.source`의 `run/moved/param/startup/default`와 `label/note`를 화면 글로 보입니다. 그림 주소는 `image_base + pNNN.png + image_query`입니다.
- `values[].items`와 `silver_only[].items`로 현재 문서의 문제 목록을 좁힙니다. 같은 값은 빼고 `silver.value == null`이면 만듦, 나머지 차이는 틀림, `silver_only`는 못 뽑음입니다. 문서별 값 수이며 점수 화면의 여러 문서 합계와 같다고 하지 않습니다.
- `silver_only[].lines`는 항상 추정 글과 점선·별도 바탕 토큰으로 보입니다. `silver_lines`는 전체 정답의 후보 줄 찾기 범위로 표시합니다.
- 빈칸: `/api/sets` 어느 판에도 없는 문서는 평가용인지 확정할 정보가 없습니다. 알려진 잠금은 이유를 보이고 요청하지 않습니다. 실행의 `docs/no_gold`와 묶음의 열람 가능 목록에도 없는 문서는 요청하지 않고 자료 없음으로 표시합니다. 404만 보고 평가용이라고 추정하지 않습니다.
- 단계 7 계약: `evidence_line_shown`의 `item`은 선택 값의 `items`에 실제로 있는 요청 항목만 보냅니다. 다른 기준의 값을 누르면 null입니다. 보이는 S02의 실제 쪽 줄 강조를 확인한 뒤 값마다 한 번 보냅니다. 자동 기본 선택과 추정 줄은 성공 사건을 보내지 않습니다.

### step 4 API 재확인

- `same_conditions`는 최상위 bool을 사용합니다. `headline` 객체의 반환 키도 유지하며 채점 문서가 다르면 내부 `same_conditions`도 false로 맞췄습니다. 조건이 비어 있으면 별도의 미기록 안내를 보입니다.
- `conditions[{what,a,b,changed}]`와 `prompt_changed_sections`, `docs{common,only_a,only_b}`를 결론 위에 표시합니다. 현재 선택 정답지 `key.label`을 두 실행의 재채점 기준으로 붙입니다. 과거 정답지 재현을 주장하지 않습니다.
- `comparable`에는 이유 필드가 없습니다. 값이 false인 이유는 `run_kind`의 의미로 설명합니다. 단건·일부·신규 문서는 이유와 함께 선택 가능하며 정답 생성·평가·비교표·읽기 실패 기록은 비활성입니다.
- STRUCTURE에 별도 기본 짝이 없으므로 현재 실행을 B로, 앞선 같은 `run_kind`와 같은 `set.id` 실행을 A로 고릅니다. 이력에서 `{a,b}`를 받으면 그 순서가 우선입니다.
- `/api/diff`의 `changed_values`는 `{doc_id,kind,content}`만 있습니다. 정확한 `path`가 없다는 안내를 보이고 고친 값은 A, 새로 틀린 값은 B의 문서·관련 항으로 갑니다. optional path가 주어지면 그대로 전달합니다. 글 내용에서 위치를 지어내지 않습니다.
- `/api/prompt_diff`에는 key 인자가 필요하지 않습니다. 실행쌍과 no만 전송하며 펼치기 전에는 요청하지 않습니다. 실행·정답 목록과 diff는 `ctxUrl`로 선택 key를 전달합니다.
- 표 행 수에는 거리 상태가 없습니다. 옛 표시처럼 받은 행 수와 정답 행 수의 절대 거리만 비교해 가까워짐·멀어짐을 표시합니다. 점수 차·바뀐 값·원인 후보는 API 값을 그대로 사용합니다.

#### Step 6 작업 API 재확인

- `jobsStartTry`는 공통 `set`·`key`를 요청 본문에 보냅니다. `jobsStartRun`은 `set`을 보내고 409 요약의 조건 사본을 P02에서 확인합니다.
- `jobsDocs`는 공통 set의 문서만 읽습니다. 두 양식은 각각 `runnable.try/run`과 `run_reason.try/run`을 사용합니다.
- `jobsRenderResult`는 실제 작업의 `target.key.label`을 점수 옆에 붙입니다. 결과 없음 204는 빈 성공 결과로 취급하지 않습니다.
- 비교표 API의 key 미지원은 그대로입니다. S10에는 기본 `silver/claude` 기준임을 표시합니다. 서버 파일과 실행기 인자는 변경하지 않았습니다.

## 글 출처

step 5: `UI_TEXT.servers`와 `errors.connection/env`를 COPY에서 이관했습니다.
서버 문장 함수는 기존 키·인자를 유지합니다. 고급 스위치 안내는 바로 보이는 ‘AI 켜기와 비용’으로 바꿨습니다.
`COPY_EXCEPTIONS`에는 동적 모델 상태·시간과 달러 단위·설정 이름 결과·실제 서버 번호·삭제 권한 이유·503·실행 결과·실제 기록 경로를 적었습니다.
시안의 ‘예시 서버’·‘(예시)’는 실제 확인 창에서 제거했습니다. 임대료는 제안 API의 실제 요약으로 확인하며 시안 금액을 박지 않았습니다.


고정 글은 `b_app_text.py`의 `UI_TEXT`에 모읍니다.
점으로 나눈 COPY 키를 같은 중첩 경로로 옮깁니다.
JS는 `T("nav.recent")` 같은 경로 조회만 합니다.
실제로 없는 키는 `⟦키⟧`로 드러나게 합니다.
`POLISH_TEXT`는 `UI_TEXT`와 같은 객체입니다. step 9에서 옛 화면 전용 글 묶음을 제거했습니다.
서버의 첫 HTML 주입 이름은 그대로 유지합니다.

| COPY.md 절 | UI_TEXT 최상위 키 또는 이관 규칙 | 맡는 step |
|---|---|---|
| 적용 계약 | 모든 키. HTML 문자 해제와 `{이름}` 치환 | 1 |
| 첫 사용 안내 두 갈래 | `journey`, `score`, `source`, `jobs` | 2, 3, 6, 7 |
| 용어표 — 40개 | `glossary`의 term·설명. 허용 농도와 단위는 첫 등장에도 표시 | 2, 3, 8 |
| 이름 바꾸기 | 표에 명시된 `jobs`, `glossary`, `context`, `score`, `servers` | 1~8의 소유 영역 |
| guide.html 구성 | `help.guide`의 9장 | 8 |
| 잘못된 접속 주소 안내 교정 | `help.settings`, `errors.env` | 5, 8 |
| 기존 문구 생성부 이관표 | 아래 영역별 키. 계산·판별 함수는 유지 | 1~8 |
| 막힘 → 바꾼 글 | `score`, `context`, `servers`, `errors`, `jobs`, `common`, `source`, `glossary` | 각 소유 step |
| nav — 전역 메뉴 | `nav` | 1 |
| context — 전역 상태 · P01 자료 기준 | `context` | 1, 연결 문구 5 |
| common — 공통 상태와 표시 | `common` | 1 |
| errors — E01–E09 복구 | `errors` | 공통 1, 실제 화면 연결 2~8 |
| score — S01 결과 · S08 결과 읽기 | `score` | 2, 안내 연결 7 |
| S01, S04, S07 — 채점 기준 23개 | `score`의 기준별 키 | 2, 비교 표시 4, 도움말 8 |
| source — S02 원문 | `source` | 3 |
| compare — S04 비교 · S10 비교표 | `compare` | 4, 비교표 생성 6 |
| servers — S06 연결 · P02 확인 | `servers` | 5 |
| jobs — S03 시험 · S05 기록 · S09 여러 문서 | `jobs` | 6 |
| journey — S08 두 갈래 안내 | `journey` | 7 |
| help — S07 도움말 | `help` | 8 |
| glossary — S07 용어 · S01, S02 첫 소개 | `glossary` | 8, 필요한 첫 소개 2~3 |

현재 COPY의 표는 1,798개의 키를 담습니다.
승인 기록은 문구 수를 1,812개로 적었습니다.
구현은 현재 표의 키 집합을 기준으로 합니다.
실제 자리표시는 `{score}`, `{count}`, `{section}`, `{name}` 같은 `{이름}` 형식입니다.
`N`이나 `<이름>`을 새 치환 규칙으로 추가하지 않습니다.
코드나 파일 이름 안의 `<문서 번호>` 같은 설명은 동적 값과 구분합니다.
`<br>`는 화면 줄바꿈으로 읽습니다.
예: COPY의 `compare.score_value`는 `{score} / 100점`입니다.
실행 이름과 원문과 수치와 모델 응답과 지시문 본문은 API 데이터입니다.
시안의 숫자와 이름을 기본 데이터로 옮기지 않습니다.

`COPY_EXCEPTIONS` 목록(step 1):

- `common.expand`, `common.collapse`: 공용 카드 펼침·접기의 기존 조작 이름 유지.
- `common.raw_error`: 공통 오류의 기존 ‘원문 보기’ 이름 유지.
- `common.todo`: API 복구 문장에 ‘할 일’을 한 번만 붙이는 자리표시.
- `context.model.connected_count`: 공통 연결 모델 수와 이름의 자리표시가 COPY에 없음.
- `context.model.checked_at`: STRUCTURE의 마지막 확인 시각에 대응하는 공통 문구가 없음.
- `context.unavailable`: 없는 값·시각을 0이나 빈 글 대신 ‘확인 못 함’으로 표시.

새 문구가 꼭 필요한 step은 키와 이유를 이 목록에 추가합니다.
승인 COPY 자체는 수정하지 않습니다.

step 2의 글 출처입니다.

- COPY의 `score.*`와 `jobs.kinds.*`를 `UI_TEXT`에 옮겼습니다. 채점 항목의 쉬운 이름·측정 방법도 같은 표를 씁니다.
- COPY_EXCEPTIONS의 `score.basis.*`, `loading.scoring`, `load_failed.*`는 동적 기준·로딩·조회 실패를 보충합니다.
- `score.summary.must_progress/target_line/top_problem/open_source/unlinked`는 사용자 결정의 짧은 목표·일반 문제 제목·연결 불가를 표시합니다.
- `score.criteria.hidden/score/weight`, `problem.shown/show_more/empty/cause/evidence_unrecorded`, `selection.*`는 실제 API 범위와 기록 없음 상태에 대응합니다.
- `score.history.point/selected/plotted/current_record/started/scope`, `conditions.progress/running/nonempty_difference/nonempty_meaning`는 이력·진행·보조 점수 범위를 보충합니다.
- `score.calls.scope/attempt_info/mode/limit_reason`, `calculation.weight/loss_formula/weight_basis`, `gaps.*`, `documents.seconds`, `value_points`는 실제 수치에 단위와 뜻을 붙입니다. 공식 점수와 손실은 새로 계산하지 않습니다.
- 예외 이유는 코드의 COPY_EXCEPTIONS에 키별로 기록했습니다. 승인 COPY는 수정하지 않았습니다.

step 4의 글 출처입니다.

- `compare.*`의 승인 문장을 `UI_TEXT.compare`에 옮겼습니다. `diff_headline/diff_ui_text`의 인자·반환 키는 그대로 두고 COPY 문장으로 바꿨습니다.
- 비교 조건과 목록의 동적 단위, 정렬/필터/재시도 단추, 선택 불가 사유, API 미기록 상태, 행 수 거리, 지시문 요청 상태는 COPY에 일반형이 없어 `COPY_EXCEPTIONS`에 이유를 기록했습니다.
- 승인 COPY와 DESIGN 파일은 수정하지 않았습니다. 원인 후보는 서버가 준 글과 순서를 그대로 보존합니다.

### step 8 글 출처와 예외 재검토

- `UI_TEXT.help`와 `UI_TEXT.glossary`는 COPY의 동일 키에서 옮겼습니다. `guide.html`은 같은 글의 정적 사본입니다. 실행 시 COPY 파일을 읽지 않습니다.
- `GLOSSARY`는 승인된 40개 용어의 뜻을 한 문장과 예 한 줄로 나눕니다. 옛 이름·별칭과 의미 키도 `also`로 찾아집니다. 항목의 `{term, short, example, also}`와 `/api/glossary` 계약은 같습니다.
- `help.facts.run_*`, `scores/targets/two_targets/empty_rows/auxiliary/draft_gap/old_draft/ranking/cause_*`는 옛 guide 1~3장의 사실입니다. 과거 실버 통계는 현재 정답지 상태와 구분했습니다.
- `help.facts.setup_*`, `rngd_tunnel`, `trial_*`, `cli_*`, `prompt_*`, `limit*`, `columns/slow/connection`, `protect_*`는 옛 guide 4~8장의 설정·명령·여섯 단계·수정 위치·실패 규칙·금지 사항입니다. RunPod 주소 설명만 승인된 프록시 설명으로 바로잡았습니다.
- `source_*`, `journey*`, `storage/cards`, `server_*`, `jobs`는 STRUCTURE의 새 화면·기록·서버 계약에 맞춘 설명입니다. 이전 ‘고급 스위치’와 ‘안내 기록 초기화’ 설명은 새 동작으로 대체했습니다. `counts`는 실행 수치 없는 도움말에 자리표시를 남기지 않는 설명입니다.
- `help.navigation.*`는 STRUCTURE S07의 원래 화면 복귀·장 직접 이동·용어 검색과 두 조회의 독립 복구에 필요한 조작 글입니다. 용어와 기준 목록은 각각 `/api/glossary`, `/api/criteria`에서 읽습니다.
- `COPY_EXCEPTIONS`는 키별로 다시 검토했습니다. 이미 COPY 안에 동일한 문장이 있는 **52개**를 예외에서 뺐습니다. 남은 **420개**는 공통 4·맥락 3·점수 44·원문 61·비교 68·서버 68·작업 77·안내 23·도움말 72개입니다. 각 사유는 코드에 남습니다.
- 같은 키가 COPY와 다른 예외는 8개입니다. 서버 5개는 실서버의 예시 표시 제거·실제 기록 경로·요금 확인 계약입니다. 도움말 3개는 주소 예시 금지 2개와 실제 용어 수 40개입니다. 그 외 예외는 동적 수치·미기록 상태·추가 조작·이전 사실 보존으로 승인 표에 동일 키가 없습니다.
- `run_label`, 모델·실행 이름, `score_status`의 항목 문장, `card_summary`의 호출 상태를 승인 글로 맞췄습니다. `friendly_error/server_ui_text/diff_headline`은 이미 승인 글을 사용합니다. SET_TEXT·KEY_TEXT·JOB_ERROR_TEXT·JOURNEY_TEXT·PROBLEM_TEXT 설명도 같은 글을 사용합니다. `error` 식별 글과 함수 인자·반환 키·계산은 그대로입니다.
- `b_app_text.py` 밖에서 만드는 Python 문장은 변경하지 않았습니다. 위 API 확인 목록의 `_why_offline`, 서버 확인/만료, 작업 검증/label, 원문 warnings, 비교 what/원인 후보는 후속 백엔드 검토 대상입니다.

step 9 글 예외: `common.screen_shown`은 화면 이동이 끝났다는 상태 알림입니다. 조회나 모델 실행 성공을 뜻하지 않습니다. 승인된 화면 이름을 끼워 넣으며 새 기능을 설명하지 않습니다.

## 설계와 다른 점

| 번호 | 확인한 차이 또는 빈 곳 | 적용할 계획 | 담당 step |
|---|---|---|---|
| D01 | step 0 설명은 처음 방문을 안내 화면으로 보냄. `_common.txt` 2절과 STRUCTURE의 들어오는 길은 S01 위 안내 띠 | 상위 사용자 결정을 따라 첫 방문과 재방문 모두 S01. 해시 우선 | 1, 7 |
| D02 | STRUCTURE의 O1~O6·O9와 G01~G05는 API 보충 전 대안을 포함 | 새 API 필드를 사용. top_drops와 임시 메모리 저장으로 대체하지 않음 | 1~7 |
| D03 | 관문 ④의 고른 문제 값 표시가 STRUCTURE와 mockup에 없음 | `S.focus`로 받은 값만 S03 지시문 위에 표시. `jobs.focus.*` 사용 | 6 |
| D04 | STRUCTURE의 화면 이름과 COPY의 최종 이름이 다름 | 화면 위치와 흐름은 STRUCTURE. 화면 글은 COPY | 1~8 |
| D05 | DESIGN은 목표 미달을 중립색으로 규정. UI_GUIDE는 미달·내려감·실버 전용 값을 빨강으로 규정 | `_common.txt`의 우선순위상 UI_GUIDE를 적용. 빨강과 상태 글을 함께 표시. 실제 오류와 미달은 문구로 구분 | 1~4 |
| D06 | DESIGN의 색 토큰에 UI_GUIDE의 주의 주황이 없음 | step 1에서 기존 주의 주황 `#bc4c00`을 `--warning-text`로 유지. 나머지 범례는 muted `#53645e`, failure `#a52f35`, selected `#fff3c6` 적용. 승인 파일은 수정하지 않음 | 1, 3, 9 |
| D07 | mockup은 코드와 pre에 직접 anywhere를 적용. `.raw`는 mockup에 없음 | 이 계획의 데이터 class로 적용 범위를 제한. `.raw`는 상위 UI_GUIDE 근거로 유지 | 1 |
| D08 | mockup의 화면 목록과 172장면 이동과 가짜 숫자와 디자인 바닥글은 제품 기능이 아님 | 검토용 요소 제외. 실제 데이터와 상태로 같은 승인 구성을 그림 | 1~8 |
| D09 | API 표는 모든 key에 updated_at이 있다고 읽힐 수 있음. 실제 개별 응답에는 없음 | API 확인의 빈칸 1에 따름. 현재 폴더 시각과 과거 작업 기준을 구분 | 1, 6 |
| D10 | S10 설계는 전역 정답지를 계속 보여 줌. 생성 API는 key를 전달하지 않음 | API 확인의 빈칸 2에 따름. 비교표 파일의 실제 기본 정답지를 표시 | 6 |
| D11 | COPY 설명은 용어 40개. `help.terms.title`은 38개 | term 키 40개 보존. 제목을 40개로 표시하고 COPY_EXCEPTIONS에 근거 기록 | 8 |
| D12 | 승인 기록은 문구 1,812개. 현재 표에는 키 1,798개 | 현재 키 표를 이관 기준으로 삼음. 없는 키를 수량에 맞춰 만들지 않음 | 1, 8 |
| D13 | STRUCTURE에는 구역의 실제 DOM id와 일반 스크립트 등록 방식이 없음 | 위 36개 전용 구역과 공통 4개 구역으로 고정. 표·단추·선택 상자·details를 사용 | 1~8 |
| D14 | 옛 CSS와 일부 옛 시험은 휴대폰 폭과 고급 뒤 서버와 브라우저 안내 저장을 전제 | 데스크톱 1280~1680px만 구현. 서버 메뉴 노출. journey API 사용. 행동 시험은 새 의미로 이관 | 1, 5, 7 |
| D15 | step 2 구현 문장은 큰 표 안의 가로 넘침을 허용. STRUCTURE와 DESIGN은 표도 줄바꿈하며 넘치지 않도록 규정 | 승인 레이아웃대로 열 너비와 줄바꿈을 조절. 호출은 8칸씩 두 줄. 숨김으로 내용을 잘라내지 않음 | 2, 9 |
| D16 | STRUCTURE의 모듈 간 사건은 저장하지 않는 속성만 제시. `_common.txt`는 메모리 사건에 문서·항·값 경로 허용 | 메모리에서 성공 판정에 사용. journey 저장은 허용된 v2 필드만 사용 | 3, 6, 7 |
| D17 | step 1은 10개 화면 모두 메뉴 단추를 요구하고 승인 왼쪽 메뉴는 일곱 장소 | 일곱 주 메뉴를 유지. S08은 머리 단추. S09·S10은 각각 S03·S04를 고를 때 보이는 하위 단추. 현재 화면 제목과 상위 메뉴 표시를 함께 유지 | 1 |

시안 캡처는 1280px와 1440px만 있습니다.
1680px는 향후 실제 브라우저 확인 범위에 포함합니다.
API의 null과 오류 상태는 단순한 상태 상자와 재시도 단추로 채웁니다.
새 메뉴와 새 계산 방식은 추가하지 않습니다.

step 2의 API 확인 보충입니다.

- `/api/runs`에는 별도 `history[]`나 `best` 객체가 없습니다. `run_kind`로 정답 생성 실행을 제외한 API 기록을 그립니다. 최고점은 `/api/run`의 `card_summaries.history` 문장만 사용합니다. 화면에서 최고점을 다시 뽑지 않습니다.
- 이력 요약은 모든 묶음 기준입니다. 현재 점수는 선택한 묶음만, 펼친 이력은 전체 묶음이라고 글로 구분합니다. 이력 표에 각 실행의 묶음·정답지·채점 수를 붙입니다.
- 완료 시각 필드는 없습니다. 있는 `started_at`을 ‘시작 시각’으로 표시합니다. COPY의 ‘완료 시각’이라고 바꿔 부르지 않습니다.
- API의 current가 선택 묶음과 다르면 API 시각 순 목록의 같은 묶음 마지막 실행을 씁니다. 묶음이 없거나 id가 미확정이면 결과 없음입니다.
- key.label이 없는 응답은 ‘정답 초안(실버) 기준’으로 표시합니다. targets가 없으면 목표는 확인 못 함입니다. 90·17을 대입하지 않습니다.
- counts·cause만 손실 행에 추가했습니다. 기존 손실 수식·값·순위와 top_drops는 유지합니다. next_action은 같은 가장 큰 문제를 가리키게 했습니다.

## 브라우저로 볼 것

- fix step 0 미실행: 도움말 9장과 점수 기준 펼침, 모델 조회 실패·켜는 중·다른 모델의 공통 줄/S06 상태, 모델 응답 없이 S01·S02·갈래 1 읽기, 정답지 미확인/선택 불일치, 202·204 후 결과 재조회, S02→S03 숫자 묶음의 원문 글 표시를 실제 브라우저에서 확인한다.

step 9에서 step 1~8의 미실행 목록을 아래 100줄로 합쳤습니다. 모든 줄은 미실행입니다.
각 줄을 가로 1280px·1440px·1680px에서 각각 확인합니다(총 300회). 휴대폰은 범위 밖입니다.
Claude의 후속 브라우저 확인용입니다. 이 step에서는 서버·포트·브라우저를 열지 않았습니다.
가짜 API 자료와 개발용 문서만 씁니다. 평가용 내용과 비밀값은 넣지 않습니다.
처음 방문은 v2 기록 없음, 다시 방문은 성공·연습·중단 기록 있음으로 준비합니다.
서버 꺼짐은 모델 프로세스 없음, 연결 없음은 터널 닫힘 또는 모델 접속 단절입니다. 앱 자체는 후속 확인 환경에서 열려 있어야 합니다.
오류는 해당 조회 API의 실패를 주입합니다. 실제 장비를 내리거나 과금 동작을 할 필요가 없습니다.
갈래 2의 성공 UI는 가짜 작업 응답으로 확인합니다. 실제 모델 한 항 시험과 터널 및 키 재읽기와 Pod 이어받기 및 청구액은 하네스 밖의 별도 실장비 확인입니다.
실제 브라우저·보조기기·서버 증거를 각각 기록합니다. DOM 대역 통과를 화면 확인으로 적지 않습니다.

| 번호 | 화면 | 상태 또는 과제 | 가로 너비(px) | 통과할 때 보이는 것 |
|---|---|---|---|---|
| B001 | S01 | 처음 방문 | 1280 / 1440 / 1680 | 현재 점수와 가장 큰 문제가 먼저 보이고 첫 사용 안내 띠가 보인다. |
| B002 | S01 | 다시 방문 | 1280 / 1440 / 1680 | 현재 점수와 저장된 펼침 상태가 보이며 첫 방문 성공 기록을 덮지 않는다. |
| B003 | S01 | 실행 없음 | 1280 / 1440 / 1680 | 고른 묶음의 결과 없음이 보이고 0점이나 다른 묶음의 점수가 대신 나오지 않는다. |
| B004 | S01 | 서버 꺼짐 | 1280 / 1440 / 1680 | 모델 꺼짐 안내와 함께 저장된 점수와 문제를 읽을 수 있다. |
| B005 | S01 | 연결 없음 | 1280 / 1440 / 1680 | 연결 없음 안내와 함께 저장된 결과의 원문 이동 단추를 쓸 수 있다. |
| B006 | S01 | 정답지 바꿈 | 1280 / 1440 / 1680 | 이전 점수를 숨긴 뒤 새 정답지 이름과 재계산된 점수로 바뀐다. |
| B007 | S01 | 잠긴 문서 | 1280 / 1440 / 1680 | 공통 선택창에서 평가 문서의 잠긴 이유가 보이고 원문을 열 수 없다. |
| B008 | S01 | 오류 | 1280 / 1440 / 1680 | 조회 실패의 굵은 사실과 할 일과 접힌 원문이 보이고 다시 읽기가 가능하다. |
| B009 | S02 | 처음 방문 | 1280 / 1440 / 1680 | 실행과 문서를 고르는 영역 아래에 문제 목록과 원문 대조가 보인다. |
| B010 | S02 | 다시 방문 | 1280 / 1440 / 1680 | 직접 고른 문서와 항과 값 및 읽던 쪽이 유지된다. |
| B011 | S02 | 실행 없음 | 1280 / 1440 / 1680 | 실행 없이 쓸 수 있는 개발 문서는 원문만 보이며 정답과 결과가 없음을 알린다. |
| B012 | S02 | 서버 꺼짐 | 1280 / 1440 / 1680 | 모델이 꺼져도 저장된 값과 원문 줄 및 쪽 그림을 볼 수 있다. |
| B013 | S02 | 연결 없음 | 1280 / 1440 / 1680 | 모델 연결이 없어도 원문과 값 선택이 작동하고 시험 연결 안내를 볼 수 있다. |
| B014 | S02 | 정답지 바꿈 | 1280 / 1440 / 1680 | 새 정답지로 값 대조를 다시 읽고 실행 당시 원문 묶음은 유지한다. |
| B015 | S02 | 잠긴 문서 | 1280 / 1440 / 1680 | 잠긴 문서는 이유만 보이고 값과 줄 및 그림을 요청하지 않는다. |
| B016 | S02 | 오류 | 1280 / 1440 / 1680 | 조회 오류는 사실과 할 일과 접힌 원문으로 보이고 그림만 실패하면 줄 글자가 남는다. |
| B017 | S03 | 처음 방문 | 1280 / 1440 / 1680 | 문서와 항 및 모델을 고르는 순서와 선택한 문제 값이 보인다. |
| B018 | S03 | 다시 방문 | 1280 / 1440 / 1680 | 문서와 항 및 임시 지시문이 남고 단순 재방문으로 작업을 보내지 않는다. |
| B019 | S03 | 실행 없음 | 1280 / 1440 / 1680 | 기준 실행이 없어도 시험 준비와 연습을 열 수 있으며 점수 생략 이유를 알린다. |
| B020 | S03 | 서버 꺼짐 | 1280 / 1440 / 1680 | 실제 전송 제한과 제자리 모델 연결 및 연습 선택이 보인다. |
| B021 | S03 | 연결 없음 | 1280 / 1440 / 1680 | 연결 복구 동작과 연습이 구분되며 전송 단추만으로 실제 성공을 기록하지 않는다. |
| B022 | S03 | 정답지 바꿈 | 1280 / 1440 / 1680 | 새 시험의 정답지 이름이 바뀌고 이미 끝난 작업의 정답지는 작업 기록대로 보인다. |
| B023 | S03 | 잠긴 문서 | 1280 / 1440 / 1680 | 시험할 수 없는 문서의 이유가 보이고 선택 및 전송이 막힌다. |
| B024 | S03 | 오류 | 1280 / 1440 / 1680 | 옵션 조회 실패의 사실과 할 일과 접힌 원문이 보이고 오래된 양식을 보내지 않는다. |
| B025 | S04 | 처음 방문 | 1280 / 1440 / 1680 | A와 B 선택 및 조건 차이가 비교 결론보다 먼저 보인다. |
| B026 | S04 | 다시 방문 | 1280 / 1440 / 1680 | A와 B 순서와 필터 및 펼친 값 선택이 유지된다. |
| B027 | S04 | 실행 없음 | 1280 / 1440 / 1680 | 비교할 실행이 부족하다는 안내가 보이고 가짜 차이나 점수가 나오지 않는다. |
| B028 | S04 | 서버 꺼짐 | 1280 / 1440 / 1680 | 모델이 꺼져도 저장된 두 실행과 값 차이를 비교할 수 있다. |
| B029 | S04 | 연결 없음 | 1280 / 1440 / 1680 | 연결 없음은 공통 영역에서 알리고 저장된 비교 내용을 계속 읽을 수 있다. |
| B030 | S04 | 정답지 바꿈 | 1280 / 1440 / 1680 | 양쪽 점수를 같은 새 정답지로 다시 읽고 이전 비교 점수를 숨긴다. |
| B031 | S04 | 잠긴 문서 | 1280 / 1440 / 1680 | 평가 문서의 원문 이동이 차단되고 공통 선택창에 잠긴 이유가 보인다. |
| B032 | S04 | 오류 | 1280 / 1440 / 1680 | 비교 조회 오류의 사실과 할 일과 접힌 원문을 읽고 다시 비교할 수 있다. |
| B033 | S05 | 처음 방문 | 1280 / 1440 / 1680 | 진행 중 작업과 끝난 작업을 상태 글 및 대상 조건으로 구분할 수 있다. |
| B034 | S05 | 다시 방문 | 1280 / 1440 / 1680 | 선택한 로그와 읽던 위치가 갱신 뒤에도 유지된다. |
| B035 | S05 | 실행 없음 | 1280 / 1440 / 1680 | 작업 기록 없음이 보이고 빈 표나 결과 성공을 대신 표시하지 않는다. |
| B036 | S05 | 서버 꺼짐 | 1280 / 1440 / 1680 | 모델이 꺼져도 저장된 작업 대상과 결과 및 로그를 읽을 수 있다. |
| B037 | S05 | 연결 없음 | 1280 / 1440 / 1680 | 연결 없음과 작업의 실패 및 완료 상태가 서로 다른 글로 보인다. |
| B038 | S05 | 정답지 바꿈 | 1280 / 1440 / 1680 | 공통 정답지는 바뀌지만 과거 작업의 target 정답지와 지문은 바뀌지 않는다. |
| B039 | S05 | 잠긴 문서 | 1280 / 1440 / 1680 | 평가 문서를 열거나 재시험하는 경로가 없고 공통 잠금 이유가 보인다. |
| B040 | S05 | 오류 | 1280 / 1440 / 1680 | 목록 및 로그 조회 오류에 사실과 할 일과 접힌 원문이 보인다. |
| B041 | S06 | 처음 방문 | 1280 / 1440 / 1680 | 현재 연결 상태와 서버별 비용 및 가능한 동작이 바로 보인다. |
| B042 | S06 | 다시 방문 | 1280 / 1440 / 1680 | 이어받은 Pod와 마지막 조회 상태가 보이고 방문만으로 서버를 만들지 않는다. |
| B043 | S06 | 실행 없음 | 1280 / 1440 / 1680 | 실행 기록 없이도 서버 상태를 읽고 조작 가능 여부를 확인할 수 있다. |
| B044 | S06 | 서버 꺼짐 | 1280 / 1440 / 1680 | 모델 없음과 준비 동작이 보이며 프로세스 존재를 준비 완료로 표시하지 않는다. |
| B045 | S06 | 연결 없음 | 1280 / 1440 / 1680 | 터널 닫힘과 모델 없음이 서로 다른 사실 및 할 일로 보인다. |
| B046 | S06 | 정답지 바꿈 | 1280 / 1440 / 1680 | 공통 정답지 이름만 바뀌고 서버 및 비용 상태를 임의로 바꾸지 않는다. |
| B047 | S06 | 잠긴 문서 | 1280 / 1440 / 1680 | 공통 문서 선택의 잠금이 유지되고 서버 준비가 문서 잠금을 풀지 않는다. |
| B048 | S06 | 오류 | 1280 / 1440 / 1680 | 조회 실패의 사실과 할 일과 접힌 원문이 보이며 오래된 조작 단추를 쓸 수 없다. |
| B049 | S07 | 처음 방문 | 1280 / 1440 / 1680 | 도움말 아홉 장과 용어 검색 및 원래 화면으로 돌아가는 동작이 보인다. |
| B050 | S07 | 다시 방문 | 1280 / 1440 / 1680 | 읽던 장과 검색어를 유지하고 돌아가면 이전 화면의 선택이 남는다. |
| B051 | S07 | 실행 없음 | 1280 / 1440 / 1680 | 실행 기록 없이도 처리 순서와 채점 기준 및 용어를 읽을 수 있다. |
| B052 | S07 | 서버 꺼짐 | 1280 / 1440 / 1680 | 모델 없이도 도움말과 준비 방법을 읽을 수 있다. |
| B053 | S07 | 연결 없음 | 1280 / 1440 / 1680 | 연결 복구 설명과 화면 복귀를 사용할 수 있고 실제 연결 성공을 표시하지 않는다. |
| B054 | S07 | 정답지 바꿈 | 1280 / 1440 / 1680 | 공통 정답지 이름이 바뀌어도 일반 채점 설명을 특정 실행 점수처럼 보이지 않는다. |
| B055 | S07 | 잠긴 문서 | 1280 / 1440 / 1680 | 평가 문서 보호 설명과 선택창의 잠금 이유를 읽을 수 있다. |
| B056 | S07 | 오류 | 1280 / 1440 / 1680 | 용어와 기준 조회가 각각 복구되고 실패하지 않은 도움말은 계속 읽을 수 있다. |
| B057 | S08 | 처음 방문 | 1280 / 1440 / 1680 | 점수 읽기와 한 항 시험의 두 갈래 및 서로 다른 성공 조건을 읽을 수 있다. |
| B058 | S08 | 다시 방문 | 1280 / 1440 / 1680 | 성공과 연습 기록 및 중단한 위치가 남고 이어하기를 선택할 수 있다. |
| B059 | S08 | 실행 없음 | 1280 / 1440 / 1680 | 점수 갈래의 건너뛰기와 시험 연습 안내가 보이며 성공을 만들어 내지 않는다. |
| B060 | S08 | 서버 꺼짐 | 1280 / 1440 / 1680 | 서버 없는 점수 갈래와 시험의 연결 또는 연습 선택이 구분된다. |
| B061 | S08 | 연결 없음 | 1280 / 1440 / 1680 | 복구 동작을 안내하면서 선택한 갈래와 진행 위치를 유지한다. |
| B062 | S08 | 정답지 바꿈 | 1280 / 1440 / 1680 | 선택한 정답지로 다음 행동을 안내하고 이전 성공 이력을 지우지 않는다. |
| B063 | S08 | 잠긴 문서 | 1280 / 1440 / 1680 | 잠긴 문서는 안내 대상으로 잡히지 않고 다른 개발 문서를 고를 수 있다. |
| B064 | S08 | 오류 | 1280 / 1440 / 1680 | 기록 조회 실패의 사실과 할 일과 접힌 원문이 보이며 실패를 첫 방문으로 처리하지 않는다. |
| B065 | S09 | 처음 방문 | 1280 / 1440 / 1680 | 문서 묶음과 모델 및 반복 수와 실행 이름을 검토할 수 있다. |
| B066 | S09 | 다시 방문 | 1280 / 1440 / 1680 | 고른 문서와 반복 수 및 입력한 이름이 유지되고 자동으로 실행하지 않는다. |
| B067 | S09 | 실행 없음 | 1280 / 1440 / 1680 | 과거 실행이 없어도 사용 가능한 문서를 골라 실행 준비를 할 수 있다. |
| B068 | S09 | 서버 꺼짐 | 1280 / 1440 / 1680 | 서버 준비 안내가 보이고 준비되지 않은 모델로 본 실행을 보내지 않는다. |
| B069 | S09 | 연결 없음 | 1280 / 1440 / 1680 | 연결 복구 뒤 돌아오면 문서 선택과 실행 이름이 남는다. |
| B070 | S09 | 정답지 바꿈 | 1280 / 1440 / 1680 | 공통 정답지 변경이 표시되고 실행 조건과 비교표 기준을 혼동시키지 않는다. |
| B071 | S09 | 잠긴 문서 | 1280 / 1440 / 1680 | 문서마다 runnable.run과 사유를 반영하며 전체 선택도 잠긴 문서를 고르지 않는다. |
| B072 | S09 | 오류 | 1280 / 1440 / 1680 | 옵션 오류의 사실과 할 일과 접힌 원문이 보이고 오래된 선택을 실행하지 않는다. |
| B073 | S10 | 처음 방문 | 1280 / 1440 / 1680 | 비교할 실행의 이름과 조건 및 선택 순서와 제목 칸이 보인다. |
| B074 | S10 | 다시 방문 | 1280 / 1440 / 1680 | 선택한 실행 순서와 제목이 남고 방문만으로 비교표를 만들지 않는다. |
| B075 | S10 | 실행 없음 | 1280 / 1440 / 1680 | 선택 가능한 실행 없음이 보이고 비교표 생성이 제한된다. |
| B076 | S10 | 서버 꺼짐 | 1280 / 1440 / 1680 | 모델이 꺼져도 저장된 실행을 비교표 대상으로 고를 수 있다. |
| B077 | S10 | 연결 없음 | 1280 / 1440 / 1680 | 연결 없음과 무관하게 저장된 실행 선택과 조건 검토를 할 수 있다. |
| B078 | S10 | 정답지 바꿈 | 1280 / 1440 / 1680 | 공통 선택과 실제 비교표의 기본 정답지 제한을 별도 글로 보여 준다. |
| B079 | S10 | 잠긴 문서 | 1280 / 1440 / 1680 | 평가 실행을 선택할 수 없고 잠금 이유를 읽을 수 있다. |
| B080 | S10 | 오류 | 1280 / 1440 / 1680 | 실행 목록 오류의 사실과 할 일과 접힌 원문이 보이며 다시 읽을 수 있다. |
| B081 | P01 | 적용·취소·키보드 | 1280 / 1440 / 1680 | Tab과 Shift+Tab 및 Escape를 써도 초점이 보이고 취소는 원래 단추로 돌아가며 적용만 맥락을 바꾼다. |
| B082 | P02 | 확인·취소·만료 | 1280 / 1440 / 1680 | 확인 요약과 주의 및 한 번 사용 규칙이 보이고 취소 및 만료 뒤 중복 동작을 보내지 않는다. |
| B083 | 공통 | 한국어·긴 이름·스크롤 | 1280 / 1440 / 1680 | 머리와 메뉴 및 고정 맥락 줄이 겹치지 않고 한국어 단어를 보존하며 페이지와 표에 가로 스크롤이 없다. |
| B084 | 공통 | 말풍선·포커스·화면 끝 | 1280 / 1440 / 1680 | Tab으로 설명을 열고 Escape로 닫을 수 있으며 포인터를 설명으로 옮겨도 유지되고 화면 밖으로 잘리지 않는다. |
| B085 | 공통 | 불러오는 중·표시 완료·보조기기 | 1280 / 1440 / 1680 | 열 화면에서 대기와 화면 표시 완료 글이 상태 영역으로 전달되며 표시 완료를 모델 실행 성공으로 읽지 않는다. |
| B086 | S01 | 숫자·호출 격자·이력 | 1280 / 1440 / 1680 | 손실의 점 단위와 0건 및 기록 없음을 구분하고 8칸 두 줄 격자 및 이력의 동등한 표 선택을 쓸 수 있다. |
| B087 | S01→S04 | 이력 두 점·저장 거부 | 1280 / 1440 / 1680 | 두 점을 고른 순서로 A와 B에 보내고 선택 취소 및 저장 거부 뒤에도 초점과 현재 선택이 남는다. |
| B088 | S02 | 그림 좌표·실제와 추정 근거 | 1280 / 1440 / 1680 | 실제 쪽 그림의 상자가 글자와 맞고 추정 줄은 점선과 추정 글로 구분되며 실제 근거 선택만 안내 성공으로 센다. |
| B089 | S02 | 도움말 삽입 뒤 격자 순서 | 1280 / 1440 / 1680 | 제목과 도움말 및 실행 선택이 전체 폭을 차지하고 그 아래에 문제 목록과 값 및 원문이 겹치지 않게 놓인다. |
| B090 | S04 | 같은 조건·필터·지시문 | 1280 / 1440 / 1680 | 같은 조건 차이는 중립으로 보이고 양쪽 값 목록 및 지시문을 펼칠 때만 읽으며 교환 뒤 늦은 응답이 끼지 않는다. |
| B091 | S03→S06→S03 | 연결 준비·복귀 | 1280 / 1440 / 1680 | 제자리 연결과 확인을 거쳐 시험으로 돌아오면 문서와 항 및 지시문이 남고 클릭 수와 준비 대기시간을 따로 기록할 수 있다. |
| B092 | S03·S05 | 결과 세 모양·204·실패 | 1280 / 1440 / 1680 | 연습 두 단계와 항 시험 여섯 단계 및 전체 문서 결과를 구분하고 결과 없음과 실패 및 저장 경로를 읽을 수 있다. |
| B093 | S06 | 소유권·비용·주기 조회 | 1280 / 1440 / 1680 | 남의 Pod에는 삭제 단추가 없고 비용 미상과 0달러를 구분하며 10초 및 60초 조회 뒤 초점과 펼침이 유지된다. |
| B094 | S07·guide | 아홉 장·40개 용어·23개 기준 | 1280 / 1440 / 1680 | 독립 도움말과 화면 도움말이 같은 아홉 장을 보이고 72ch 본문 및 긴 명령과 두 조회의 독립 복구를 읽을 수 있다. |
| B095 | S08→S01→S02 | 갈래 1 끝까지 | 1280 / 1440 / 1680 | 문제의 실제 근거 줄까지 직접 열어 성공 시각이 남고 이동 단추나 추정 줄만 열면 성공으로 세지 않는다. |
| B096 | S08→S03 | 갈래 2 끝까지 | 1280 / 1440 / 1680 | 연습과 실제 결과를 차례로 열면 별도 기록이 남고 dry_run=false 및 선택 항 ok=true인 결과 요약 표시만 실제 성공으로 센다. |
| B097 | S08·S03 | 새로고침·저장 실패·두 탭 | 1280 / 1440 / 1680 | 중단 위치와 보낸 작업이 복원되고 자동 재전송이 없으며 다시 보기와 닫기 및 두 탭 저장이 기존 성공을 줄이지 않는다. |
| B098 | 처음 보는 사용자 과제 1 | 지금 점수와 가장 큰 문제 말하기 | 1280 / 1440 / 1680 | 프로젝트 설명 없이 앱만 읽은 사용자가 현재 정답지와 점수 및 손실이 가장 큰 문제와 원문 위치를 말한다. |
| B099 | 처음 보는 사용자 과제 2 | 한 항목 시험 | 1280 / 1440 / 1680 | 프로젝트 설명 없이 문서와 항을 골라 결과를 열고 연습인지 실제 성공인지 구분한다. |
| B100 | 처음 보는 사용자 과제 3 | 묶음 또는 정답지 바꾸기 | 1280 / 1440 / 1680 | 프로젝트 설명 없이 선택창에서 적용하고 바뀐 기준과 점수 또는 결과 없음 및 잠긴 이유를 말한다. |

### step 0

브라우저 확인 없음: 계획 step

- ① 진단: 승인. CRITIQUE 파일이 있고 비어 있지 않습니다.
- ② 구조: 승인. STRUCTURE 파일이 있고 비어 있지 않습니다.
- ③ 시안: 승인. mockup과 PNG 16장이 있습니다. DESIGN·PRODUCT는 기준 커밋 `2a78072` 이후 HEAD에서 달라졌습니다.
- ④ 문구: 승인. COPY 파일이 있고 비어 있지 않습니다.

impeccable context: 한 번 실행해 성공했습니다. 지정 index와 PRODUCT·DESIGN을 찾았습니다. surface brief는 없습니다. 자동 detector 훅은 없습니다.

Questions skipped: non-interactive.
이 step은 UI를 편집하지 않아 craft-floor와 detect를 실행하지 않았습니다.
승인 PNG 16장은 직접 읽었습니다.
실제 앱의 브라우저 동작은 확인하지 않았습니다.
관문 ⑤ 수락은 이 step의 판정 범위가 아닙니다.

검증 결과는 아래에 기록합니다.

- step 파일의 AC 명령 전체를 저장소 최상위에서 직접 실행했습니다. 종료 코드는 0입니다.
- 승인 네 줄과 필수 파일과 기준 커밋 차이와 필수 절 제목을 모두 통과했습니다.
- 전체 시험은 1,909개 통과했습니다. 30개는 건너뛰었습니다. 실행 시간은 34.28초입니다.
- `test_preprocess.py`는 지정된 `--ignore` 인자로 제외했습니다.
- 경고 7개는 SWIG 기반 외부 라이브러리 타입의 `__module__` 관련 사용 중단 경고입니다. 시험 실패는 없습니다.
- 정보 보존표는 94줄입니다. 새 자리 94칸은 모두 비어 있습니다. 시험 이관표는 37줄입니다.
- API 확인표는 59줄입니다. 빈칸은 2개입니다. 실제 조건이 다른 계약은 2개입니다.
- 화면은 10개입니다. 공통 선택·확인 영역은 2개입니다. 전용 구역은 36개입니다. 공통 구역은 4개입니다.
- 작업 전 저장한 기존 파일 500개의 SHA-256을 대조했습니다. 완료 상태 기록 전까지 변경은 없었습니다.
- ARCHITECTURE의 일반 스크립트 구성과 API 계약을 계획에 연결했습니다. 계약 차이는 숨기지 않고 표에 기록했습니다.
- ADR-028의 승인 구조와 정보 보존과 평가용 문서 잠금을 유지합니다. 실제 서버 연결은 이번 검증에 포함하지 않았습니다.
- UI_GUIDE의 외부 주소 금지와 키보드 조작과 데스크톱 너비 기준을 계획에 반영했습니다. 시각 규칙 충돌은 D05~D07에 기록했습니다.
- BUILD에는 평가용 문서 내용과 쪽 글자와 TO21 자료와 비밀값을 넣지 않았습니다. 원문 데이터와 `.env`를 계획 작성에 사용하지 않았습니다.
- 화면 코드와 시험과 승인 설계와 docs와 실행기는 수정하지 않았습니다. 커밋하지 않았습니다.

### step 1

⚠️ DEGRADED: no browser in sandbox

Questions skipped: non-interactive.

구현 전에 새 시험을 실행했습니다. 24 failed / 235 passed입니다.
실패를 직접 본 시험은 다음과 같습니다.

- `tests/test_B_b_app_dom.py::test_scripts_exist_and_boot_is_last`
- `tests/test_B_b_app_dom.py::test_static_rules_no_modules_korean_strings_external_addresses_or_motion`
- `tests/test_B_b_app_dom.py::test_all_scripts_load_without_boot`
- `tests/test_B_b_app_shell_ui.py::test_initial_route_is_pure_and_defaults_to_recent`
- `tests/test_B_b_app_shell_ui.py::test_navigation_menu_focus_registration_and_hash_changes`
- `tests/test_B_b_app_shell_ui.py::test_context_picker_applies_once_keeps_cancel_and_shows_reasons_dates_and_fingerprint`
- `tests/test_B_b_app_shell_ui.py::test_context_restores_only_usable_values_and_survives_storage_errors`
- `tests/test_B_b_app_shell_ui.py::test_context_empty_lists_and_request_failure_keep_navigation_and_honest_state`
- `tests/test_B_b_app_shell_ui.py::test_context_url_adds_key_only_to_contract_paths_preserving_other_arguments`
- `tests/test_B_b_app_shell_ui.py::test_api_and_post_preserve_error_status_and_gaps_response_shapes`
- `tests/test_B_b_app_shell_ui.py::test_model_connection_names_count_neutral_absence_and_error_recovery`
- `tests/test_B_b_app_shell_ui.py::test_start_draws_navigation_before_pending_requests_and_polls_without_duplicates`
- `tests/test_B_b_app_shell_ui.py::test_text_interpolation_missing_key_zero_false_and_shell_has_no_missing_copy`
- `tests/test_B_b_app_shell_ui.py::test_card_preserves_content_state_focus_and_works_without_storage`
- `tests/test_B_b_app_shell_ui.py::test_error_is_fact_action_and_closed_raw_detail_and_code_is_safe`
- `tests/test_B_b_app_shell_ui.py::test_tooltip_targets_get_keyboard_access_without_nested_tab_stops`
- `tests/test_B_b_app_shell_ui.py::test_tooltip_keyboard_escape_and_pointer_transfer`
- `tests/test_B_b_app_text.py::test_doc_legend_matches_existing_css_colors_and_returns_fresh_values`
- `tests/test_B_b_app_text.py::test_ui_text_contains_shell_keys_and_legacy_keys_without_collision`
- `tests/test_B_b_app_text.py::test_ui_text_matches_copy_md`
- `tests/test_B_b_app.py::test_index`
- `tests/test_B_b_app.py::test_static`
- `tests/test_B_b_app.py::test_static_start_entry_and_replay`
- `tests/test_B_b_app.py::test_index_has_help_tab_and_links`

산출물과 다음 step 연결 계약입니다.

- `index.html`은 일반 스크립트 core → shell → boot만 싣습니다. 옛 `app.js`는 보존했습니다.
- `core.js`는 `S.ctx`, `S.focus`, `S.cards`, `h/s/fill/T/api/post/on/emit/card/term`을 제공합니다. `coreReplace`는 없는 자식을 글자 `null`로 그리지 않습니다.
- `shell.js`는 `go`, `shellDefineView(viewId, {load, render})`, `shellInitialRoute`, `ctxUrl`, `start`를 제공합니다. `load(args)` 뒤 `render(element, args)`를 부릅니다. 늦게 끝난 이전 이동은 그리지 않습니다.
- 화면 10개와 전용 구역 36개의 id는 계획표와 같습니다. 첫 방문·빈 해시·모르는 해시는 S01로 갑니다. 안내 기록은 아직 읽지 않습니다(step 7).
- `S.ctx`는 `{version:1,set:<id|null>,key:<id|null>}`입니다. P01 적용 후 `context_changed`에 같은 모양의 사본을 한 번 전달합니다. 변경 없는 적용과 취소는 사건을 보내지 않습니다.
- `/api/sets`·`/api/keys`의 목록과 기본값을 사용합니다. 사용 불가 후보는 disabled와 이유로 표시합니다. 수정 시각은 현재 `/api/keys` 값입니다. 지문은 접힌 상세에만 둡니다.
- `ctxUrl`은 지정된 다섯 점수·원문 API에만 `key`를 붙입니다. `set`은 자동 추가하지 않습니다. 정답지 유무에 따른 `/api/silver_gaps`의 두 응답 모양을 유지합니다.
- 모델 상태는 15초마다 조회합니다. 중복 조회는 합칩니다. 없음·확인 중·503은 중립색입니다. 일반 조회 실패만 오류색입니다.
- `UI_TEXT`는 COPY의 nav/context/common/errors와 두 하위 화면 제목을 담습니다. 옛 `POLISH_TEXT`를 `_LEGACY_POLISH_TEXT`로 옮긴 뒤 합쳤습니다. 글 예외 7개는 위 목록과 코드에 이유를 남겼습니다.
- 점수·원문·비교·시험·서버 관리·안내 내용은 이 step에서 구현하지 않았습니다.

기존 시험을 바꾼 이유와 보존 범위입니다.

- `test_B_b_app_dom.py`에 옛 DOM 문자열과 실행 도우미를 이름만 바꿔 그대로 옮겼습니다. 별도 대조에서 문자열과 함수 본문이 일치했습니다.
- 옛 score/start/jobs/diff_doc 시험의 검증 함수 본문은 그대로입니다. import만 새 옛 틀로 바꿨습니다. polish는 import 변경과 명시된 말풍선 시험 두 개 삭제만 했습니다. 삭제한 두 동작은 새 shell 시험에서 확인합니다.
- `test_B_b_app.py`의 index/static/start/help 시험은 옛 탭 화면이 이번 step에서 교체되므로 새 뼈대와 스크립트 기준으로 바꿨습니다. 초기 HTML 문구 주입·HTML 이스케이프 시험은 그대로 통과했습니다.
- `doc_legend`와 해당 시험의 기대 색 세 개는 새 DESIGN 토큰에 맞췄습니다. 주의 주황은 UI_GUIDE에 따라 그대로입니다. 다른 Python 함수 본문은 변경하지 않았습니다.

검증 결과입니다.

- 실패 확인 후 구현했습니다. 처음 24 failed / 235 passed에서 공통 뼈대와 글·정적 경로의 누락을 확인했습니다.
- 지정 정적 AC 명령과 Node 확인은 종료 코드 0입니다.
- 새 DOM·shell 시험: 18 passed. 서버 정적 경로·문구 시험: 244 passed.
- 옛 화면 회귀까지 합친 집중 시험: 292 passed / 7 warnings.
- 전체 지정 명령: 1930 passed / 30 skipped / 7 warnings, 34.43초. `tests/test_preprocess.py`를 제외했습니다. 경고는 기존 SWIG 타입의 `__module__` 사용 중단 경고입니다.
- impeccable context를 한 번 실행했습니다. detect를 한 번 실행했습니다. 총 22개 지적은 기존 `design/wireframes.html` 15개와 `guide.html` 7개입니다. 변경한 index/app.css/js의 지적은 0개입니다. 기존 지적 파일은 수정하지 않았습니다.
- 보호 대상 127개 지문을 대조했습니다. 허용된 BUILD.md 외 변경은 없습니다. 상태 기록 뒤에는 자기 step의 상태·summary만 바뀌는지 다시 확인합니다.
- 아키텍처 점검: b_app.py와 옛 app.js 불변. 일반 스크립트 순서·API 인자 계약 준수. 새 파일에 외부 주소·한글 JS 문자열·동작 효과 없음. 새 의존성 없음. `.env`와 문서 원문을 읽지 않았습니다. 시험은 가짜 응답을 사용했습니다.
- 실제 서버 연결과 브라우저 배치·한국어 줄바꿈·가로 스크롤은 확인하지 않았습니다. `_common.txt` 7절의 서버·브라우저 실행 금지를 따릅니다. 기계 시험을 시각 확인으로 간주하지 않습니다.
- 커밋하지 않았습니다. `phases/app-redo/index.json`의 step 1만 완료로 기록합니다.

### step 2

⚠️ DEGRADED: no browser in sandbox

Questions skipped: non-interactive. 승인된 구조·시안을 그대로 구현합니다.

- 시험 먼저: `/tmp/step2-red.txt`에서 16 failed, 16 passed를 확인했습니다.
- 실패: 새 score UI 11개(요약·이동·빈 상태·목록·실행 선택·이력·세부·로딩·경합·대체 글·초기 맥락), `test_problem_loss_counts_preserves_missing_zero_and_input` 3사례, `test_problem_loss_counts_partial_and_ties`, `test_problem_status_copy_contract_has_no_pass_judgement`.
- 실패 이유: score.js 미구현, counts·cause 없음, COPY 요약 미이관.
- 옛 polish의 항목 펼침·이력 저장 두 시험은 같은 행동을 새 DOM 시험으로 이관한 뒤 삭제했습니다.

구현과 기존 시험 이관 기록입니다.

- `js/score.js`는 S01 8개 구역을 등록합니다. `S.score`가 이 화면 상태를 맡습니다. `scoreLoad`는 선택 key로 재채점 요청을 읽고 늦은 응답을 무시합니다.
- `scoreOpenSource`는 `go("s02",{run,doc,section,item,pick:"mismatch"})`를 부릅니다. doc은 top_problem.docs[0]이며 S.focus에도 남깁니다. 같은 대상 재시험은 실행 조건의 `score-retest`에서 S03으로 연결합니다.
- 저장 상태 `b_app.pick`은 두 실행의 비교 순서입니다. 카드 접힘은 기존 core의 b_app.cards를 씁니다.
- `test_B_b_app_score_ui.py`는 새 run_js로 교체했습니다. 기존 polish 2개를 이관·삭제했고 격자/실버 시험은 그대로 남겼습니다.
- `test_B_b_app_text.py`의 기존 status/summary 기대 문장은 COPY의 목표선·필수 달성·한 문장 한 사실로 바꿨습니다. 이유: 사용자 결정 ‘합격’ 금지와 새 화면 이름. 수치·손실·top_drops 검증은 그대로입니다.
- `test_status_next_action_uses_last_known_connection`은 새 손실 순위의 문제를 가리키도록 바꿨습니다. 기존 fixture에서 가장 큰 손실은 11항이며 옛 top_drops의 8항과 다릅니다. 옛 top_drops 순위 단언은 유지했습니다.
- `test_B_b_app.py`의 `test_api_run_and_diff_targets`, `test_run_status_and_summaries_do_not_change_cached_scores`는 역사 문구 접두어만 COPY로 바꿨습니다. 서버 요약 수·캐시 불변 단언은 유지했습니다.
- 추가 실패 확인: 원래 항목명에 붙는 괄호 설명, 미확정 묶음, 건수 미기록 문구와 점수 기준, 실행 조건의 다음 행동 4개를 RED→GREEN으로 보완했습니다. 저장된 이력 선택의 새로고침 보존도 확인했습니다.
- impeccable context·craft/distill 참고와 craft-floor를 읽었습니다. detect는 한 번 실행했고 기존 지적 22개(wireframes 15, guide 7)뿐입니다. 변경한 index/app.css/js 지적은 0개입니다. 정적 경로 `/static/app.css`를 검사기가 상대 경로로 풀어 못 읽는 경고가 있어 색 검사 범위는 불완전합니다. 직접 CSS 토큰과 정적 규칙 시험을 확인했습니다.
- 브라우저·앱 서버·모델 서버는 실행하지 않았습니다. 전체 AC 안의 A 시험이 포트를 열려다 샌드박스에서 거부되었습니다. A 시험을 고치거나 제외하지 않았습니다.

최종 AC와 아키텍처 확인입니다.

- `/tmp/step2-ac.sh`에 지정 AC를 그대로 넣어 저장소 최상위에서 bash로 실행했습니다. 최종 종료 코드는 1입니다. 기록은 `/tmp/step2-ac.log`입니다.
- 정적 파일·스크립트·counts·옛 시험 이관·BUILD 절·Node 확인은 모두 통과했습니다.
- score UI + DOM: 20 passed. loss/status/top_problem: 23 passed. b_app + b_app_runs: 117 passed.
- 전체 지정 시험: **1 failed, 1944 passed, 30 skipped, 7 warnings** (36.78초). 경고는 기존 SWIG 타입의 __module__ 사용 중단 경고입니다.
- 실패는 `tests/test_A_input.py::test_every_changing_route_answers_with_update` 한 개입니다. A 시험의 425행 `HTTPServer(("127.0.0.1", 0), ...)`가 `socket.bind`에서 `PermissionError: [Errno 1] Operation not permitted`로 중단됩니다. 이 샌드박스의 포트 열기 제한입니다. A 파일과 시험 기대값은 변경하지 않았습니다.
- 전체 AC를 통과하지 못했으므로 step 2 상태는 **error**입니다. 브라우저와 로컬 포트가 허용된 실행 환경에서 전체 AC 재확인이 필요합니다. 현재 환경에서 예외를 숨기거나 시험을 제외하지 않습니다.
- 10/31 Claude가 샌드박스 밖에서 전체 시험을 다시 돌렸습니다: 1945 passed, 30 skipped. A 시험도 통과했습니다. 그래서 step 2를 completed로 바꾸고 실행기 AC 재검증에 맡겼습니다.
- 원래 추적/보호 파일 3,722개의 지문과 비교했습니다. 허용된 기존 파일 8개만 달랐고 score.js 하나를 새로 만들었습니다. 정보 보존표의 이 step 빈칸은 0개입니다. 상태 기록은 step 2만 변경합니다.
- `b_app.py`, `b_app_runs.py`, 추출·공용·다른 역할 코드, 옛 app.js, 승인 설계, docs, CLAUDE.md, step 파일은 불변입니다. score_losses의 기존 수식·정렬·값, top_drops의 값·순서와 모든 기존 API 키를 보존했습니다.
- 일반 script 순서, 가짜 API 시험, 온전한 실패 원문 표시, 한글 문자열의 UI_TEXT 집중, 패키지·외부 주소·움직임 효과 금지를 확인했습니다. `git diff --check`가 통과했습니다.
- 이력과 목표 막대는 받은 점수를 좌표로만 바꿉니다. 계산은 보조 점수 차이와 표 행 비율 등 기존 표시값뿐입니다. 목표값 90·17이나 손실 순위를 화면에 박지 않았습니다.
- 브라우저 확인을 수행하지 않았으므로 첫 화면 높이·가로 넘침·줄바꿈·실제 원문/재시험 흐름은 확정하지 않습니다. 커밋하지 않았습니다.

#### Step 2 재시도 검증

⚠️ DEGRADED: no browser in sandbox

- 이전 시도의 미커밋 변경을 읽고 그대로 이어서 검증했습니다. 이번 재시도에는 기능 코드와 시험을 추가로 바꾸지 않았습니다. 위의 실패 시험 기록은 이전 구현 시도의 기록입니다.
- 정적 AC와 `git diff --check`는 종료 코드 0입니다. 지정한 시험 세 묶음은 각각 20 passed, 23 passed, 117 passed입니다.
- 전체 지정 시험은 **1 failed, 1944 passed, 30 skipped, 7 warnings**입니다(36.82초, 종료 코드 1). 실행 기록은 `/tmp/to21-step2-full-ac.log`입니다.
- 실패는 동일한 `tests/test_A_input.py::test_every_changing_route_answers_with_update`입니다. 425행의 로컬 HTTP 서버가 `socket.bind`에서 `PermissionError: [Errno 1] Operation not permitted`로 중단됩니다. A 시험은 수정하거나 제외하지 않았습니다. 현재 권한과 B 역할의 변경 범위 안에서는 이 제한을 해소할 수 없습니다.
- 기존 손실 함수의 구문 트리를 대조했습니다. `counts`·`cause` 추가 부분을 제외하면 기존 수식·정렬·반환 구조가 같습니다. 정보 보존표의 Step 2 담당 20줄에 새 위치가 모두 있습니다.
- impeccable context와 detect를 각각 한 번 실행했습니다. 지적 22개는 기존 `wireframes.html` 15개와 `guide.html` 7개입니다. 변경한 화면 파일의 새 지적은 없습니다. `/static/app.css` 경로 해석 경고로 색·사용자 정의 속성 검사는 불완전합니다.
- 재시도 시작 때 기록한 보호 파일 128개의 지문이 같습니다. 이번 변경은 이 재시도 기록과 `phases/app-redo/index.json`의 Step 2 상태·오류뿐입니다.
- Step 2는 **error**로 기록합니다. 로컬 포트가 허용된 환경에서 전체 AC를 다시 실행해야 합니다. 브라우저 확인 항목은 위 ‘브라우저로 볼 것’에 유지합니다. 커밋하지 않았습니다.

#### Step 2 이번 세션 재검증 (2026-10-31)

⚠️ DEGRADED: no browser in sandbox

- 이전 미커밋 구현과 시험을 보존했습니다. 이번에는 기능 코드와 시험을 추가로 변경하지 않았습니다. 테스트 선작성·실패 확인은 위의 이전 구현 기록에 해당합니다.
- 지정 AC를 각각 직접 실행했습니다. 정적 AC는 종료 코드 0입니다. 화면·DOM 시험은 20 passed, 손실·상태 시험은 23 passed, API·실행 요약 시험은 117 passed입니다.
- 전체 지정 시험은 **1 failed, 1944 passed, 30 skipped, 7 warnings**입니다(36.60초, 종료 코드 1). `tests/test_preprocess.py`만 지정대로 제외했습니다. 경고 7개는 기존 SWIG 타입의 `__module__` 사용 중단 경고입니다.
- 실패는 `tests/test_A_input.py::test_every_changing_route_answers_with_update`입니다. 425행의 `HTTPServer(("127.0.0.1", 0), ...)`가 `socket.bind`에서 `PermissionError: [Errno 1] Operation not permitted`로 중단됩니다. A 시험을 수정하거나 추가로 제외하지 않았습니다.
- `score_losses`를 HEAD의 구문 트리와 대조했습니다. `counts`·`cause`를 넣는 반복문을 제외하면 기존 수식·정렬·반환 구조가 같습니다. 화면은 API의 손실 순서·목표값을 사용합니다.
- impeccable context와 detect를 각각 한 번 실행했습니다. 지적 22개는 기존 `design/wireframes.html` 15개와 `guide.html` 7개입니다. 변경한 화면 파일의 지적은 0개입니다. `/static/app.css` 해석 경고로 색·사용자 정의 속성 검사는 불완전합니다.
- 기록 작성 전 파일 3,902개의 지문이 시작 때와 같았습니다. 이번 변경은 BUILD의 이 기록과 index의 Step 2 상태·오류뿐입니다. 다른 step과 보호 파일은 변경하지 않습니다.
- 전체 AC 실패에 따라 Step 2를 **error**로 기록합니다. 로컬 포트가 허용된 환경에서 전체 AC를 재실행해야 합니다. 실제 화면 검증은 위 ‘브라우저로 볼 것’ 목록에 남깁니다. 커밋하지 않았습니다.


### step 3

⚠️ DEGRADED: no browser in sandbox

Questions skipped: non-interactive.

시험을 먼저 작성하고 실행했습니다. `test_B_b_app_source_ui.py` 18개가 모두 실패했습니다.
`source.js`와 원문 구역 등록이 없어 `S.source`와 `sourceLoad`와 값 단추가 없는 실패였습니다.
실패 시험은 처음 열기·직접 선택 유지, key/set·그림 주소, 세 값의 말풍선·JSON,
범례·항 요약, 줄 단추·그림 없음, 근거 사건·없는 쪽, 문제 필터·선택 순서(2개),
추정 줄, 잠김·404, 로딩·재시도, 늦은 응답·정답 변경, 재시험 전달,
원문 전용, 정답 없음·없는 경로, 점수 단추 실제 연결입니다.

옛 원문 시험 3개와 polish 시험 2개를 같은 동작의 새 시험으로 이관했습니다.
격자의 다섯 상태 글은 step 2의 `test_score_details_preserve_documents_grid_rows_rules_and_selected_answer_gaps`가 이미 검증합니다.


산출물과 후속 연결입니다.

- `js/source.js`: `S.source`, `sourceEnsure`, `sourceLoad`, `sourcePick`, `sourcePickLine`, `sourceGoSection`, `sourceDrawBoxes`와 네 구역을 구현했습니다.
- `sourceRemember`는 `S.focus`에 `run/doc/section/item/path/kind/expected/actual/page/line/lines/estimated/source_set/key/scroll`을 남깁니다. 자료는 메모리에만 있습니다. `sourceRetest`가 `go("s03", {...S.focus})`로 넘깁니다.
- `scoreOpenSource`의 기존 인자를 그대로 받아 실제 S02 이동까지 시험했습니다. `score.js`는 수정하지 않았습니다.
- `UI_TEXT.source`에는 COPY의 source 문장과 옛 항·표 이름을 넣었습니다. COPY에 없는 일반 문서용 조작·상태·이름은 `COPY_EXCEPTIONS`에 이유를 등록했습니다.
- `doc_legend/doc_ui_text/value_tip_lines`의 반환 키는 유지했습니다. 문구와 참·거짓 표시를 COPY에 맞추면서 `test_B_b_app_text.py`의 기대 문장도 같은 규칙으로 바꿨습니다.
- 처음 RED 뒤 초기 주소 복원·응답 역전·삭제된 실행·목록 밖 문서·그림 좌표·값 유지 시험을 추가했습니다. 실패를 본 뒤 수정했습니다.
- 전체 회귀 첫 실행은 1966 passed / 30 skipped / 1 failed였습니다. 초기 실행 목록 조회의 처리되지 않은 예외를 발견했습니다. 재시도 회귀 시험부터 추가하고 오류 처리를 고쳤습니다.
- impeccable `detect --json backend/scripts/b_app_static` 1회 실행은 종료 코드 0입니다. 출력에서 기존 `design/wireframes.html`과 `guide.html`의 색·모서리 권고를 확인했습니다. 수집 출력이 제한되어 전체 지적 건수는 확정하지 않았습니다. 새 화면의 토큰·JS 글·외부 주소·움직임 금지는 DOM 정적 시험으로 검사합니다.
- 승인 구조의 문제 목록/선택 값 대조/전체 원문 구역을 사용합니다. 시안의 문서 10건·9개 문제 같은 예시 수치는 코드에 넣지 않았습니다. 브라우저 배치 확인은 하지 않았습니다.
- 아키텍처 점검: 원문·그림을 파일로 저장하지 않습니다. 평가용 내용과 비밀값을 읽지 않았습니다. 결과 값·JSON·오류 원문은 `h`의 글자 노드로만 그립니다. 백엔드 API, 공용·다른 역할 코드, 옛 app.js, 승인 설계 정본은 바꾸지 않았습니다. 커밋하지 않습니다.


최종 완료 기준 검증 결과입니다.

- 파일·스크립트 등록·옛 시험 제거·기록 절·Node 확인: 모두 종료 코드 0.
- 원문·점수·DOM 시험: 47 passed.
- 문구·원문 응답 시험: 258 passed, 7 warnings.
- 전체 회귀(`--ignore=tests/test_preprocess.py`): 1968 passed, 30 skipped, 7 warnings, 38.40초.
- 경고는 기존 SWIG 타입의 DeprecationWarning입니다. 이번 전체 실행에는 포트 권한 실패가 없었습니다.
- 새 원문 시험 27개는 모두 직접 만든 자료와 API 대역으로 실행했습니다.
- `git diff --check`로 공백 오류를 확인합니다. 단계 3만 completed로 기록합니다.


### step 4

⚠️ DEGRADED: no browser in sandbox

Questions skipped: non-interactive. 승인된 설계를 그대로 구현합니다.

시험 먼저: `/tmp/to21-step4-red.log`에서 **24 failed, 2 passed, 159 deselected**를 확인했습니다.
새 compare.js와 UI_TEXT.compare가 없어 실패했습니다. 기존 문장 시험은 COPY의 새 문장을 기대하도록 먼저 이관했습니다.
옛 비교 화면 시험 2개와 polish의 값 펼침 시험 1개는 새 DOM 시험으로 옮긴 뒤 삭제했습니다.

실패한 시험입니다.

- `tests/test_B_b_app_compare_ui.py::test_same_conditions_are_before_headline_and_all_deltas_are_neutral`
- `tests/test_B_b_app_compare_ui.py::test_changed_conditions_have_separate_lines_and_direction_with_text`
- `tests/test_B_b_app_compare_ui.py::test_filter_sort_keeps_all_rows_hidden_count_and_candidate_reasons`
- `tests/test_B_b_app_compare_ui.py::test_empty_filter_can_restore_unscored_and_positive_items`
- `tests/test_B_b_app_compare_ui.py::test_changed_values_toggle_is_button_keeps_focus_and_both_lists`
- `tests/test_B_b_app_compare_ui.py::test_value_source_link_uses_exact_path_when_present_and_honest_section_fallback`
- `tests/test_B_b_app_compare_ui.py::test_grouped_selection_reasons_and_default_pair_skip_other_kinds`
- `tests/test_B_b_app_compare_ui.py::test_key_changes_reload_and_late_old_response_cannot_replace_new_result`
- `tests/test_B_b_app_compare_ui.py::test_prompt_is_lazy_cached_per_pair_and_failure_has_fact_action_raw_retry`
- `tests/test_B_b_app_compare_ui.py::test_error_keeps_selection_hides_stale_scores_and_recovers`
- `tests/test_B_b_app_compare_ui.py::test_different_document_sets_and_prompt_hash_changes_are_visible_above_conclusion`
- `tests/test_B_b_app_compare_ui.py::test_missing_metadata_targets_and_empty_runs_remain_unknown_not_zero`
- `tests/test_B_b_app_compare_ui.py::test_rows_keep_all_counts_and_direction_is_neutral_for_repeat`
- `tests/test_B_b_app_compare_ui.py::test_score_history_navigation_and_compare_table_link_preserve_order`
- `tests/test_B_b_app_text.py::test_diff_headline_direction_and_labels[-0.5-0.5\uc810 \ub0ae\uc2b5\ub2c8\ub2e4]`
- `tests/test_B_b_app_text.py::test_diff_headline_direction_and_labels[0.5-0.5\uc810 \ub192\uc2b5\ub2c8\ub2e4]`
- `tests/test_B_b_app_text.py::test_diff_headline_changed_conditions_and_prompt_content`
- `tests/test_B_b_app_text.py::test_diff_headline_commit_only_is_not_same`
- `tests/test_B_b_app_text.py::test_diff_headline_no_comparable_items[items0]`
- `tests/test_B_b_app_text.py::test_diff_headline_no_comparable_items[items1]`
- `tests/test_B_b_app_text.py::test_diff_headline_adds_flutter_only_when_same_conditions`
- `tests/test_B_b_app_text.py::test_diff_headline_unscored_total_does_not_claim_equal`
- `tests/test_B_b_app_text.py::test_diff_ui_text_counts_hidden_items_including_unscored`
- `tests/test_B_b_app_text.py::test_diff_same_conditions_copy_is_cautious_and_uses_api_flag`

구현과 검증 기록입니다.

- `js/compare.js`가 S04의 여섯 구역을 `shellDefineView`로 등록합니다. `S.compare`가 선택·요청·펼침 상태를 보관합니다. `compareEnsure/compareLoad`는 초기 맥락 완료를 기다리고 늦은 응답을 무시합니다.
- `compareRenderSummary`는 조건 → 서버 결론 → 양쪽 목표 → 선택/순서 순입니다. 항목·조건·값·행·지시문 상세는 기본 접힘입니다. `compareRenderItems`는 필터와 정렬 후에도 API 배열을 바꾸지 않습니다.
- `compareRenderValues`는 단추 자체를 교체하지 않아 펼친 뒤 초점이 남습니다. `compareFetchPrompt`는 펼친 항만 요청하고 실행쌍별로 메모리에 보관합니다. 정답지를 바꾸면 비교 결과를 다시 요청합니다.
- 옛 `test_B_b_app_diff_doc_ui.py`의 두 시험과 polish의 값 펼침 시험을 새 `run_js` 시험으로 이관해 삭제했습니다. 나머지 기존 시험은 유지했습니다.
- `test_B_b_app_text.py`의 비교 문장 기대값은 COPY의 ‘높습니다/낮습니다’, 신중한 흔들림 표현, 항목/조건/후보 안내에 맞춰 바꿨습니다. 가장 큰 차이 선정·동점 처리·입력 불변·반환 키 검증은 유지했습니다. 문서 구성이 다를 때 same_conditions가 false임도 확인합니다.
- 첫 구현 집중 시험에서 빠진 글 키 `score.documents.document`를 발견하고 기존 `common.document`로 수정했습니다. 집중 시험 213개가 통과했습니다.
- 추가 검증: 초기 #s04 진입, 늦은 지시문 응답, 실제 S02 모듈로 key/path 전달, 305개 값의 전체 접근, API delta의 무변경 표시를 확인했습니다. S02 시험의 가짜 실행 목록에 docs가 빠진 것을 바로잡았습니다. 제품 원문 코드는 수정하지 않았습니다.
- 양쪽 목표 상태 글의 빠짐은 새 시험 실패를 확인한 뒤 API `targets.*.weighted.met`로 표시했습니다. 목표를 화면에서 재계산하지 않습니다.
- impeccable context와 detect를 각 1회 실행했습니다. detect의 22개 권고는 기존 wireframes.html 15개와 guide.html 7개입니다. 새 화면 지적은 0개입니다. `/static/app.css`를 상대 경로로 해석하지 못한 경고로 색·사용자 정의 속성 검사에는 한계가 있습니다.
- 첫 전체 회귀: 1980 passed, 30 skipped, 7 warnings, 1 failed(39.73초). 실패는 `tests/test_A_input.py::test_every_changing_route_answers_with_update`의 socket.bind PermissionError뿐입니다. `_common.txt` 7절은 이 환경 실패 하나만 있으면 completed를 허용하고 실행기가 밖에서 재검증하도록 정합니다. A 시험을 고치거나 제외하지 않았습니다.
- 브라우저·앱 서버·모델 서버를 실행하지 않았습니다. 실제 시각 배치·한국어 줄바꿈·가로 넘침은 미확인입니다. 이 목록은 위 ‘브라우저로 볼 것’에 남깁니다.

최종 완료 기준과 변경 경계입니다.

- 지정 AC를 `/tmp/to21-step4-ac.sh`로 그대로 실행했습니다. 기록은 `/tmp/to21-step4-ac.log`입니다.
- 정적 파일·스크립트·같은 조건·옛 시험 이관·BUILD 절·Node 확인: 모두 통과.
- 비교 UI + DOM: **24 passed**. 비교 화면 시험은 20개입니다.
- 문구 + 비교 API/계산: **195 passed, 7 warnings**.
- 전체 지정 시험: **1986 passed, 30 skipped, 7 warnings, 1 failed**, 39.65초. 전체 명령의 종료 코드는 1입니다.
- 유일한 실패는 기존 A 시험 `test_every_changing_route_answers_with_update`의 `socket.bind` → `PermissionError: [Errno 1] Operation not permitted`입니다. `_common.txt` 7절의 명시된 예외에 따라 step 4를 completed로 기록합니다. 실행기가 샌드박스 밖에서 전체 AC를 다시 검증합니다. 경고 7개는 기존 SWIG 타입의 DeprecationWarning입니다.
- 시작 때 기록한 3,911개 파일 지문과 비교했습니다. 허용된 기존 파일만 변경되었습니다. 비교 정보 보존표 I27~I35의 새 위치 9개가 모두 채워졌습니다. `git diff --check`가 통과했습니다.
- 아키텍처 점검: `b_app.py/b_app_diff.py`, 앞선 core/shell/score/source, 옛 app.js, 공용·다른 역할 코드, docs·CLAUDE·하네스·승인 설계 정본은 불변입니다. 새 패키지·외부 주소·이미지·애니메이션은 없습니다. 평가용 내용과 비밀값을 사용하지 않았습니다.
- API 응답 키와 점수/바뀐 값 계산은 유지합니다. targets 목표값은 서버 값을 사용합니다. 조건이 같거나 미확인이면 점수 방향은 중립입니다. 바뀐 값·원인·오류·지시문 글은 글자 노드로만 그립니다.
- 자기 step의 status와 summary만 기록합니다. 커밋하지 않았습니다.

### step 5 — model-connection

⚠️ DEGRADED: no browser in sandbox

- Questions skipped: non-interactive. 승인된 구조와 시안을 코드로 옮깁니다. impeccable context 1회 실행 후 craft·harden·clarify 지침을 읽었습니다.
- RED: 새 `test_B_b_app_servers_ui.py` 20개가 실패했습니다. 구현 전 S06에 동작 단추·문장이 없고 `serversRenderCompact`가 없는 것이 원인입니다. 소유·비용·진단·확인·설정 다시 읽기·409·503·기록·공유 조회를 검사합니다.
- RED: `test_server_copy_uses_approved_diagnoses_controls_and_visible_management`, `test_server_friendly_errors_and_env_problem_follow_copy_without_address_examples` 2개가 옛 진단·주소 예시 문장 때문에 실패했습니다.
- 터널도 P02 확인을 거칩니다. STRUCTURE ‘흐름 5’·PRODUCT의 연결 통로 변경 확인과 COPY의 tunnel_open/close 확인 문구가 이를 요구합니다. 직접 실행은 확인이 없는 설계에만 적용되는 조건부 요구이므로 적용하지 않습니다.

- 구현: `js/servers.js`의 S06 5구역과 P02, `serversRenderCompact(el,{model})`. `S.servers`는 조작 상태만 갖고 `S.shell.servers`가 자료를 소유합니다. `servers_changed` 사건으로 맥락·S06·합성 구역을 갱신합니다. 선택 모델은 `S.focus.model`, 돌아갈 화면은 `S.focus.returnScreen`(s03/s09), 문서·항·편집 상태는 지우지 않습니다.
- 접근성·보호: 남의 Pod와 deletable:false의 삭제 단추를 만들지 않습니다. 실제 button·label·표·dialog를 씁니다. 포커스 순환·Escape·복귀·한 번 실행·만료·늦은 잠금·실패 조회를 시험했습니다. 표시 문자열은 글자 노드이며 주소·설정 할당·SSH 인자를 가리고 응답 전체를 덤프하지 않습니다.
- HARDEN RED→GREEN: 추가 7시험 중 4개가 실패했습니다(조회 간격, 확인 창 갱신, 삭제 실패 상세 보존, 장비 펼침 유지). 고친 뒤 27개가 통과했습니다. 정상 미준비 상태의 중립색과 설정 재읽기 뒤 오래된 조회 합침 문제도 실패 시험으로 확인하고 고쳤습니다.
- 시험 이관: `test_B_b_app_polish_ui.py::test_server_log_copy_instruction_only_appears_with_lines`는 새 파일의 `test_server_log_instruction_only_with_lines`로 행동을 옮긴 뒤 삭제했습니다.
- 기존 시험 수정 이유: 서버 관리를 고급 뒤에 숨기지 않는 사용자 결정과 COPY 문장에 맞춰 `test_B_b_app_text.py`의 연결·오류·진단·잠금·시작 안내·try_hint 기대 문장을 바꿨습니다. `test_B_b_app_servers.py`·`test_B_b_app_server_actions.py`도 동일 문장을 검증하는 단언만 바꿨습니다. 소유권·HTTP 코드·토큰·호출·키 보호 단언은 유지했습니다. shell 시험은 15초 반복 타이머 단언을 이 step의 한 타이머로 바꿨습니다.
- 집중 AC: 화면·공통 뼈대·DOM 48 passed, 문구·서버·서버 동작 314 passed, 합계 362 passed / 7 warnings. 새 화면 시험은 30개입니다. 파일 존재·스크립트 등록·필수 함수와 필드·옛 시험 이관·BUILD 제목·node 확인도 통과했습니다.

- 연결 진입의 요청 모델 보존도 RED→GREEN으로 확인했습니다. `serversEnsure(args)`는 전달된 모델을 선택합니다. 사라진 모델을 고른 경우 다른 연결 모델을 근거로 준비됐다고 표시하지 않습니다.
- impeccable detect 1회: 종료 코드 0, 기존 `design/wireframes.html` 15개와 `guide.html` 7개 권고, 합계 22개입니다. 새 변경 파일 지적 0개입니다. `/static/app.css`를 상대 경로로 풀지 못해 색·사용자 정의 속성 검사는 불완전합니다. CSS 토큰·금지 규칙은 DOM 정적 시험으로 별도 확인했습니다.
- 아키텍처 확인: S06·P02는 기존 API와 토큰 두 단계를 유지합니다. 백엔드 실행 로직·모델 설정·추출·채점·공용 폴더를 고치지 않았습니다. 새 패키지·외부 주소·글꼴·움직임 효과를 넣지 않았습니다. 평가 문서 내용·실제 설정·키·서버 주소를 읽거나 새 코드/시험/로그에 복사하지 않았습니다. 앱·모델·SSH는 실행하지 않았습니다.
- 보호 파일 해시: 변경 0개. 승인 설계와 `docs/`·CLAUDE·하네스 실행기·step 파일·옛 app.js·서버 백엔드 파일은 그대로입니다. 다른 step 상태도 그대로입니다. 커밋하지 않았습니다.
- 전체 AC 최종 실행: `2018 passed, 30 skipped, 7 warnings`, 실패 1개. `tests/test_A_input.py::test_every_changing_route_answers_with_update`가 `socket.bind`에서 `PermissionError: [Errno 1] Operation not permitted`로 실패했습니다. `_common.txt` 7절이 명시한 유일한 예외이므로 completed로 기록합니다. A 시험은 수정하거나 제외하지 않았습니다. 실행기가 샌드박스 밖에서 재검증합니다. 브라우저 확인은 미완료입니다.

### step 6 — test-and-runs

⚠️ DEGRADED: no browser in sandbox

- Questions skipped: non-interactive. 승인된 구조와 문구를 구현합니다. `_common.txt` 7절에 따라 서버·브라우저·포트는 열지 않습니다.
- RED: 새 `test_B_b_app_jobs_ui.py` 26사례와 `test_field_help_and_try_stage_help_are_complete`가 실패했습니다(27 failed / 172 passed). S03/S05/S09/S10의 미구현과 FIELD_HELP·TRY_STAGE_HELP·JOB_UI_TEXT의 옛 문구가 원인입니다. 실패 목록은 문서별 실행 허용·맥락 전달·연결 복구·옵션 실패/회복·문제 값 4종·여섯 단계·작업 오류/경고·성공 사건·세 결과 모양/204·target·확인·비교표·로그/중단입니다.

- 구현: `js/jobs.js`의 `S.jobs`, `jobsEnsure`, `jobsPoll`, `jobsRenderTry/Run/Compare/List/Result`, `jobsWatch`, `jobsLoadPrompt`로 S03/S05/S09/S10을 등록했습니다. index에서 boot 직전에 싣습니다.
- 정보 보존: I44~I62의 새 자리를 채웠습니다. 목록 밖 가짜 RAW도 API가 허용하면 선택됩니다. 화면은 문서 이름·purpose로 잠금을 추론하지 않습니다.
- API 재확인: `/api/options`의 현재 set에 속한 docs만 사용합니다. 시험은 `runnable.try/run_reason.try`, 본 실행은 `runnable.run/run_reason.run`입니다. 시작에는 set을 보내고 시험에는 key도 보냅니다. 별도 입력 기본 경로를 만들지 않습니다.
- API 재확인: `/api/jobs`의 target만 조건 설명에 씁니다. label은 이름표로만 표시하고 command는 접힌 원문입니다. error의 사실과 COPY의 할 일·로그를 함께 보입니다. warnings는 성공에도 보입니다.
- API 재확인: `/api/jobs/<id>/result`의 plan-only·results(글자 키)·run/summary·204를 구분합니다. 전후 점수는 target.key.label 기준입니다. 비교표 POST는 key를 받지 않아 기본 silver/claude를 사용한다고 표시합니다(기존 빈칸 유지).
- 사건: `try_result_viewed`는 돌아가던 작업을 관측한 뒤 S03 요약이 보일 때 한 번만 보냅니다. mode는 작업의 dry_run으로 결정합니다. section_ok는 target.sections 전부의 results[String(no)].ok입니다. 처음부터 끝난 작업·실패·중단·대상 불일치·문서 전체에는 성공 사건을 보내지 않습니다. 이어보기 저장은 step 7 몫입니다.
- HARDEN RED→GREEN: 추가 6사례가 실패한 뒤 늦은 지시문/새 편집 보존, 바뀐 묶음의 무효 문서 선택 유지, 참/거짓 표시와 접힘 저장 실패, P02 키보드/초점, 제자리 터널 준비, 전체 결과/늦은 결과를 고쳤습니다. 사용한 확인으로 재전송되는 문제도 별도 RED 뒤 막았습니다. 점수 화면 재시험 연결은 변경 없이 기존 go의 doc/section/base_run 계약으로 통과했습니다.
- 이관: jobs UI의 옛 3시험을 새 DOM 37사례로 교체했습니다. polish의 옵션 실패·동일 자료 회복 시험 1개는 새 jobs 시험에 옮긴 뒤 삭제했습니다. text 시험은 공개 키를 유지한 FIELD_HELP·TRY_STAGE_HELP·JOB_UI_TEXT의 승인 COPY 문장에 맞춰 변경했습니다.
- 글 출처: jobs 표와 errors.job 표는 COPY 그대로 옮겼습니다. 상태 이름·동적 표 머리·입력 값 검증·조회 회복·기본 정답지 제한 등 COPY에 일반형이 없는 글은 COPY_EXCEPTIONS의 jobs.form/record/result/compare/status/kind에 이유를 남겼습니다. 시안의 예시 문서·8항 이름·시간·점수·요금은 실제 정보처럼 쓰지 않습니다.
- 설계 보완: step 3의 S.focus에는 줄 번호만 있고 줄 글자가 없는 경우가 있습니다. 이때는 ‘원문 줄’과 번호만 보이며 추정이면 추정을 붙입니다. 원문 글을 지어내거나 추가로 요청하지 않습니다. P02는 기존 action-confirm을 함께 사용합니다. S03 짧은 영역은 step 5의 상태·확인 도구를 재사용하고 S06으로 이동하지 않아도 터널/모델 준비를 시작할 수 있습니다.
- impeccable detect: 새 구현 파일 지적 0개. 기존 wireframes 15개·guide 7개 지적은 수정 범위 밖입니다. /static/app.css를 로컬 경로로 읽지 못해 색·변수 검사는 불완전하다는 도구 경고가 있습니다. 실제 브라우저 검증 증거로 쓰지 않습니다.
- 집중 AC: 화면·서버·DOM 71 passed, 문구·작업 API·앱 334 passed(기존 SWIG 경고 7개). 정적 AC와 Node 문법 검사도 통과했습니다.
- 마지막 대상 점검 RED→GREEN: 명시한 재시험 대상에 이전 문제 값이 섞이는 경우, 문서 미선택을 전체 잠금으로 잘못 설명하는 경우, 비교표 후보의 기록 조건·채점 범위 누락을 새 3시험으로 확인하고 고쳤습니다.
- 전체 AC 최종: **2052 passed, 30 skipped, 7 warnings, 1 failed**(45.28초). 유일한 실패는 `tests/test_A_input.py::test_every_changing_route_answers_with_update`의 `socket.bind` → `PermissionError: [Errno 1] Operation not permitted`입니다. `_common.txt` 7절의 명시 예외에 따라 completed로 기록합니다. A 시험은 변경하거나 제외하지 않았습니다. 실행기가 샌드박스 밖에서 다시 검증합니다.
- 보호 검증: 시작 시 기록한 120개 파일 중 허용된 BUILD.md를 제외한 119개가 동일합니다. 최종 단계 상태는 index.json의 step 6만 바꿉니다. docs·CLAUDE·백엔드 API·실행기·승인 설계는 변경하지 않았습니다. git diff --check 통과. 커밋 없음.

### step 7

⚠️ DEGRADED: no browser in sandbox. 미실행: 브라우저 확인.

- 시험 먼저: `test_B_b_app_journey_ui.py` 21사례와 `test_start_text_contract`가 실패했습니다(22 failed). `journeyDefault` 미정의와 `UI_TEXT.journey` 부재가 원인입니다.
- 옛 시작 시험 파일과 polish 시작 시험 2개를 이관합니다. 작업 새로고침 오류는 step 6의 `test_poll_failures_and_same_data_recovery_are_visible_without_losing_input`가 이미 검사합니다.
- Questions skipped: non-interactive. 승인 설계의 onboard 흐름을 적용합니다.

- 산출물: `js/journey.js`, S08 두 갈래 선택/기록, S01 첫 방문·이어하기·지난 시험 띠, 본문 안내 막대. `journeyEnsure/Load/Save/Change`, `journeyStart/Next`, `journeyRecord/Complete`, `journeyReplay/Dismiss/Skip`를 추가했습니다.
- 저장: `/api/journey` v2 전체를 PUT합니다. 요청은 직렬 처리하며 대기 중 변경은 최신 하나로 합칩니다. 늦은 GET을 버립니다. 저장 실패 상태는 다음 GET으로 지우지 않습니다. 성공 이력은 서버 응답과 합칩니다. `visibilitychange`는 재조회만 하고 작업을 재전송하지 않습니다. 옛 v1은 유효성 검사 뒤 한 번만 읽어 옮기며 키를 지우지 않습니다.
- 성공: 갈래 1은 가장 큰 문제에서 넘어온 같은 실행·문서·항·채점 기준의 `evidence_line_shown(mismatch=true)`만 받습니다. 자동 선택·추정 줄은 성공이 아닙니다. 새로 안내한 같은 값은 실제로 다시 선택하면 재확인할 수 있습니다. 갈래 2는 `try_result_viewed(mode=real, section_ok=true)`만 받습니다. 연습·실패·여러 항·취소·실제 호출 여부 불명은 실제 성공에서 제외합니다. 같은 작업은 중복 집계하지 않습니다.
- 연결 변경: `shell.js`는 시작/화면 표시 사건을, `score.js`는 문제 열기 사건을 더했습니다. `source.js`는 안내 대상 표식과 새 확인 시도의 사건 중복 범위를 추가했습니다. `jobs.js`는 준비·요청·작업 조회 사건과 안내용 대상 준비 인자를 추가했습니다. 기존 채점과 서버 작업 계산은 바꾸지 않았습니다. `serversRenderCompact`만 공유 구역 합성에 직접 사용합니다.
- API 확인: PUT 응답의 실제 모양은 `{journey, problems}`입니다. `pending.job`의 완료 작업은 목록에서 확인한 뒤 결과 보기로만 복원합니다. 처음부터 완료돼 있던 일반 작업은 기존 시험대로 성공 사건을 내지 않습니다. `START_TEXT is UI_TEXT["journey"]`이며 `/api/start`는 서버 호출 없이 같은 값을 줍니다.
- 글 출처: `UI_TEXT.journey`는 COPY.md의 journey 표를 그대로 옮겼습니다. 두 갈래 단계 배열은 글만 담는 공용 규칙을 위해 번호 키의 dict로 표현합니다. COPY에 없는 동적 안내 띠·단계 표시·실패 복구·건너뛰기 글은 STRUCTURE의 조건을 바탕으로 `COPY_EXCEPTIONS`에 기록했습니다. 승인 설계 파일은 수정하지 않았습니다.
- 기존 시험 변경 이유: `test_start_text_contract`는 두 갈래 안내로 교체했습니다. `test_text_module_has_no_pass_word`의 참조 위치만 새 `start.no_problem`으로 바꿨으며 금지어 단언은 유지했습니다. 옛 `test_B_b_app_start_ui.py`와 polish 시작 시험 2개는 새 DOM 시험으로 이관하고 삭제했습니다. jobs 오류 복구 검사는 기존 step 6 시험을 그대로 유지했습니다.
- 추가 실패 확인 후 수정: 연결 시험에서 새로고침 뒤 완료 작업을 못 세는 문제를 확인했습니다. 보관한 작업만 결과 관찰 대상으로 복원했습니다. 저장 실패 후 GET이 성공 기록을 지우는 문제, JSON 키 순서에 따라 첫 방문 판정이 달라지는 문제, 실패한 작업을 대기 중으로 보이는 문제도 먼저 실패 시험으로 재현하고 고쳤습니다.
- 자동 검증: 정적 AC 통과. journey API 42 passed, journey/shell/DOM 54 passed, start/journey 문구·라우트 15 passed. 전체 `pytest -q --ignore=tests/test_preprocess.py`: **2081 passed, 30 skipped, 7 warnings, exit 0**. 포트 권한 실패 없음. 경고는 기존 SWIG 형식의 DeprecationWarning입니다. 마지막 기록 표 제목 수정 후 UI 54개를 다시 확인했습니다.
- impeccable detect: 1회 실행했습니다. 기존 `design/wireframes.html`·`guide.html`의 색/글자 크기 권고가 나왔습니다. `/static/app.css`를 로컬 파일로 해석하지 못해 색 검사는 불완전합니다. 새 CSS는 승인된 토큰만 사용하며 DOM 정적 규칙 검사도 통과했습니다.
- 경계 확인: 보호 파일 129개 해시 불변. 새 안내 저장 자료에는 원문·문서·실행·항·값·모델·경로·키를 넣지 않습니다. 백엔드 API와 원문·평가 자료를 변경하지 않았습니다. 실모델·브라우저 검증 없음. 커밋 없음.

### step 8

⚠️ DEGRADED: no browser in sandbox. 미실행: 브라우저 확인.

- Questions skipped: non-interactive. 승인된 COPY·STRUCTURE를 구현합니다. `impeccable clarify`와 Read 모드의 읽기 폭·제목 간격을 적용합니다.
- 시험 먼저: 새 `test_B_b_app_help_ui.py`와 COPY 용어·예외 정리·실행 이름 시험을 실행했습니다. `22 failed, 256 passed, 7 warnings`를 확인했습니다.
- 실패한 계약: 새 9장 제목·직접 장 연결, RunPod 프록시 설명, 명령·단계·용어 보존, S07 열기·화면별 도움 연결·대상 유지 복귀, 용어 조회 실패 복구, 포커스 말풍선·첫 등장, README 새 구성, GLOSSARY 40개·COPY 문장, 이미 승인된 예외 제거, 실행 이름 COPY 문장, 기존 guide 제목 시험입니다.
- 기대값 변경: `GUIDE_SECTIONS`와 용어 필수 목록만 승인된 제목과 40개 용어로 바꿨습니다. 기존 형태·별칭·예제 보호·주소 및 비밀값 금지 검사는 유지했습니다.

- 구현: `js/help.js`의 `HELP_CHAPTERS`, `HELP_CONTEXT`, `S.help`, `helpEnsure/Load`, `helpRenderTopics/Glossary/Methods`, `helpOpen/Return`로 S07 두 구역을 등록했습니다. boot 직전에 읽습니다. 각 화면 제목 아래 해당 장으로 이동하는 연결이 있습니다. 원래 선택을 보관하고 돌아옵니다.
- 용어: API를 열기 전에도 `core.term()`이 HTML의 승인 글로 설명합니다. 점수·원문·비교·시험·서버·공통 정답지에 첫 등장 말풍선을 더했습니다. 알려지지 않은 정답지 종류를 실버로 추정하지 않습니다. 8항 첫 등장에는 허용 농도와 단위를 설명합니다.
- 도움말: 승인 순서의 9장을 적용했습니다. 변수 6개·앱 명령·시험 명령·여섯 단계·일곱 CLI 옵션·지시문 출처·실패 규칙·하지 말 것을 보존했습니다. RunPod 설정 문단에는 ‘터널’이 없습니다. 외부 주소·설정 값은 넣지 않았습니다. 본문은 app.css 토큰과 keep-all, 읽기 폭 72ch를 사용합니다.
- 추가 RED→GREEN: 도움말의 미치환 자리표시, 늦게 연 화면으로 돌아가지 못하는 문제, S01 단위 설명 누락, 종류 미상 정답지를 실버로 설명하는 문제를 먼저 실패 시험으로 확인하고 고쳤습니다. 승인 문구로 바꾼 서버 설명과 모델 상태 이름도 실패 시험을 먼저 확인했습니다.
- 기존 시험 변경 이유: `test_B_b_app_text.py`는 COPY의 40개 용어·실행 이름·모델/작업 상태·오류 문구로 기대 글을 교체했습니다. `test_B_b_app.py`는 9장 제목·실행/정답지 표시 이름·복구 글을 맞췄습니다. `test_B_b_app_sets.py`와 `test_B_b_app_jobs.py`는 평가 잠금·입력 오류·작업 오류의 사람이 읽는 문장만 COPY로 바꿨습니다. 이유의 내부 코드명(D-43, L001, format40)을 강제하던 단언도 같은 승인 문장으로 교체했습니다. 잠금 여부·작업 거부·오류 식별자·반환 모양·정렬·입력 불변 검사는 유지했습니다. README 계약 시험은 수정하지 않았습니다. 삭제한 시험은 없습니다.
- README: 새 화면 10개와 js 파일 나누기, UI_TEXT/COPY 출처, 설계 정본 위치를 62줄로 정리했습니다. 기존 API·설정 이름·기본 폴더 안내도 남겼습니다.
- impeccable detect: 1회 실행했습니다(exit 2). 기존 wireframes의 지적 15개와 guide의 2개가 나왔습니다. 도구가 `/static/app.css`를 로컬 파일로 읽지 못해 guide의 글자 크기를 모두 16px·검정으로 판단했습니다. 실제 CSS 선언은 본문 16·h1 28·h2 20·h3 16px와 `--ink` 토큰입니다. 승인된 스타일 링크를 바꾸지 않고 도구 한계로 남깁니다. 새 JS/CSS 지적은 없습니다. 실제 렌더링 확인은 하지 않았습니다.
- 아키텍처: API 경로·응답 모양과 채점 계산은 그대로입니다. Python 구현 수정은 b_app_text.py뿐입니다. 새 패키지와 외부 주소를 넣지 않았습니다. 평가 자료·실제 키·실모델·SSH를 사용하지 않았습니다. TO21 자료와 프롬프트 파일을 새로 만들지 않았습니다.

- 최종 AC: 파일·script 순서·설정 이름·잘못된 터널 설명 금지·외부 주소 금지·step 기록·Node 확인 모두 통과했습니다. 도움말/DOM **27 passed**, 문구/앱 **265 passed**입니다. JS 10개 문법 검사와 git diff --check도 통과했습니다.
- 전체 AC: **2110 passed, 30 skipped, 7 warnings, 1 failed**(53.25초). 유일한 실패는 `tests/test_A_input.py::test_every_changing_route_answers_with_update`의 `socket.bind` → `PermissionError: [Errno 1] Operation not permitted`입니다. `_common.txt` 7절의 명시 예외에 따라 completed로 기록합니다. A 시험을 고치거나 제외하지 않았습니다. 실행기가 샌드박스 밖에서 다시 검증합니다. 경고 7개는 기존 SWIG DeprecationWarning입니다.
- 보호 검증: 시작 시 기록한 122개 파일의 해시가 모두 같습니다. 기존 Python 함수의 이름·인자도 모두 같습니다. index.json은 step 8의 status·summary만 바꿉니다. 커밋하지 않았습니다.


### step 9

⚠️ DEGRADED: no browser in sandbox

Questions skipped: non-interactive. 승인된 화면의 정적 정리만 수행합니다.

- 시험 먼저: 새 audit UI와 DOM 시험을 실행했습니다. **32 failed, 20 passed**입니다. 기록은 `/tmp/to21-step9-red.log`입니다.
- 실패: 화면 안전 표시·기본 펼침 상태 16사례, 안내 기록 API 오류 원문 1사례, 화면 이동의 불러오기/표시 알림 10사례, native details 동기화, 브라우저 NodeList 형태, 색 토큰, 보존표 대표 위치, 옛 코드 제거입니다.
- 옛 polish의 마지막 오류 시험을 새 화면 10개의 실제 실패 요청 시험으로 옮긴 뒤 파일을 삭제했습니다. DOM 대역의 옛 실행 도우미도 제거했습니다.
- 기존 시험 변경: 정적 검사 대상에서 삭제 예정 app.js를 뺐습니다. text의 옛/새 글 합침 검사는 요구된 `POLISH_TEXT is UI_TEXT` 계약으로 바꿨습니다. 글의 비어 있음·COPY 대조·공개 API 검사와 정적 경로 보안 검사는 유지합니다.

#### 점검과 마감 결과

정적 구현의 일관성은 통과입니다. 화면 10개와 전용 구역 36개를 유지했습니다.
새 화면이나 카드나 서버 기능은 추가하지 않았습니다.
정보 보존표 94행의 대표 함수·DOM id를 확인한 뒤 app.js를 삭제했습니다.
옛 app.js의 시작 안내·점수·원문·비교·시험·실행·연결·도움말 경로를 표와 마지막으로 대조했습니다.
남은 I84는 공통 오류와 상태 알림으로 채웠습니다.
함수 존재 검사는 내용 보존 검토를 보조합니다. 자동 검사만으로 의미가 같다고 판정하지 않았습니다.

새로 확인한 제품 코드 문제는 P1 1개, P2 7개, P3 1개입니다. 아래 9개를 모두 고쳤습니다.
정적 검사에서 확인된 새 미해결 문제는 0개입니다. 브라우저의 실제 배치와 읽기·조작 품질은 아직 판정하지 않았습니다.

| 중요도 | 위치·문제 | 영향과 처리 | 검증 |
|---|---|---|---|
| P1 | jobsRenderTry의 NodeList.some | 브라우저의 요소 목록에는 some이 없어 기준 실행이 있으면 화면이 실패함; 배열로 변환 | Array 메서드가 없는 목록 대역으로 S03 진입·선택 유지 |
| P2 | jobsRenderTry/jobsRenderCompare 실행 이름 | label 객체가 `[object Object]`로 보임; title·문자열·원래 이름 순으로 읽음 | 구조화된 실행 이름을 S03·S10에서 확인 |
| P2 | helpRenderGlossary 선택적 자식 | 원래 replaceChildren은 null을 글자로 표시함; 없는 자식을 거르는 coreReplace 사용 | S07 자료 있음·없음 안전 표시 |
| P2 | journeyNotice 오류 원문 누락 | API 실패의 자세한 원인을 볼 수 없음; raw에 실제 오류 메시지 보존 | S08 실패 원문은 글자로 표시하고 기본 접힘 |
| P2 | 공통 details 펼침 상태 | summary의 aria-expanded가 없거나 programmatic open 뒤 낡음; native toggle에 맞춰 갱신 | 열 화면 summary 상태와 열기·닫기 시험 |
| P2 | jobsField 도움말 참조 | 설명 없는 칸의 aria-describedby가 없는 요소를 가리킴; 도움말이 있을 때만 연결 | 열 화면 ARIA 참조 대상 존재 확인 |
| P2 | go의 초기 로딩·완료 알림 | 첫 방문의 빈 구역과 화면 이동 상태 누락; role=status의 대기와 화면 표시 알림 | 열 화면의 지연 응답 중 글과 완료 글 확인 |
| P2 | S02 도움말 삽입 뒤 격자 행 | 자동 배치와 기존 고정 행이 충돌할 수 있음; 제목·도움말·선택을 전체 폭의 앞 세 행에 배치 | 실패를 먼저 확인한 CSS 순서·비중첩 시험; 실배치는 B009·B089 |
| P3 | dialog::backdrop 색 값 | root 밖의 색 중복; 같은 값을 --backdrop 토큰으로 옮김 | root 밖 실제 색 값 없음; 모양 변경 없음 |

추가 CSS 시험은 구현 전 **1 failed, 48 deselected**였습니다(`test_source_help_and_controls_precede_the_two_column_content`).
고친 뒤 audit+DOM은 **53 passed**입니다.
DOM 대역에는 details.open 변경 시 toggle 사건을 보내는 브라우저 동작을 보충했습니다.
기존 UI 시험을 지우거나 기대 행동을 낮추지 않았습니다.

#### audit의 다섯 축

점수는 소스와 DOM 대역으로 한정한 잠정 점수입니다. WCAG 적합성이나 실화면 수락 판정이 아닙니다.
휴대폰·다크 모드는 승인 범위 밖이므로 만들지 않았습니다.

| 축 | 잠정 점수(0~4) | 확인한 것 | 남긴 확인 |
|---|---|---|---|
| 접근성 | 2 | 네이티브 단추·이름표·유효 ARIA·상태 글·초점 테두리·색 옆 상태 글 | 실제 Tab 순서·보조기기 읽기·화면 끝 말풍선 |
| 성능 | 3 | 외부 요청·새 의존성·움직임 없음; 지시문 지연 조회·중복 polling 방지; 옛 120729바이트 제거 | 실제 렌더링 시간과 큰 문서 조작 지연 |
| 시각 토큰 | 3 | 실제 CSS 색은 root에만 있음; 간격과 테두리·글자 토큰 재사용 | 브라우저의 렌더된 색과 글꼴 및 줄높이 |
| 데스크톱 배치 | 2 | 1240px 초과 고정 width/min-width 없음; keep-all·허용 데이터 줄바꿈·S02 행 순서 | 1280·1440·1680px의 페이지와 표 넘침 |
| 구현 일관성 | 3 | 승인 10화면 유지·94정보 연결·한 API 계약·새 정적 지적 해소 | 처음 보는 사용자의 세 과제와 두 갈래 안내 |
| 합계 | 13/20 | 정적 근거만 있는 잠정값 | 브라우저 확인 전 최종 품질 점수로 사용하지 않음 |

색 토큰으로 계산한 대비는 본문/종이 13.24:1, 보조글/종이 6.26:1, 보조글/옅은 바탕 5.42:1입니다.
강조/종이 7.52:1, 오류/오류 바탕 6.33:1, 주의/종이 5.03:1, 주의/선택 바탕 4.53:1입니다.
이 값은 sRGB 토큰 계산입니다. 합성된 실제 픽셀이나 모든 중첩 상태를 측정한 결과는 아닙니다.

polish 점검에서는 간격·안쪽 여백·표준 조작 요소의 테두리를 기존 토큰과 대조했습니다.
크기만 다른 새 단추 스타일은 만들지 않았습니다. 화면별 단추·선택·펼침 의미를 유지했습니다.
표와 긴 원문은 숨겨 잘라내지 않았습니다. 실제 넘침 판정은 B083을 포함한 브라우저 목록에 남겼습니다.
요약 뒤 세부 펼침과 한 동작 단추의 승인 문구를 유지했습니다. 새 상태 글 한 줄만 COPY_EXCEPTIONS와 글 출처에 적었습니다.

#### detector와 범위 밖 항목

impeccable context는 시작할 때 한 번 성공했습니다. audit·polish·harden을 읽고 UI 편집 직전에 craft-floor를 읽었습니다.
impeccable detect는 편집 뒤 한 번 실행했습니다. 종료 코드 2이며 지적은 17개입니다.

| 남긴 항목 | 수 | 근거·처리 |
|---|---|---|
| 기존 wireframes.html | 15 | 색 14개·모서리 1개; 승인 구조 설명용 기존 파일이며 제품이 싣지 않음; 이번 변경과 무관해 그대로 둠 |
| guide.html 도구 오탐 | 2 | `/static/app.css`를 `b_app_static/static/app.css`로 잘못 해석하여 기본 검정과 16px만 읽음; 실제 링크는 공통 CSS이며 본문 16px·h1 28px·h2 20px 및 ink 토큰을 사용 |
| API 빈칸 | 2 | 개별 응답 key.updated_at 부재와 비교표 key 미전달은 기존 D09·D10; 정직한 표시를 유지하며 백엔드 변경 금지 |
| 실제 브라우저 확인 | 100줄 | B001~B100 모두 미실행; 각 줄 3너비이므로 확인 조합은 300회 |
| 실장비 확인 | 별도 | 모델 실제 시험·SSH 터널·키 재읽기·Pod 이어받기·실제 준비시간과 청구액은 미실행 |

새 제품 코드에 대한 detector 지적은 없습니다. 스타일 경로를 못 읽은 검사 결과를 렌더링 통과로 부르지 않습니다.
API 빈칸은 이번 정적 AC를 막지 않습니다. 같은 스텝의 범위를 벗어난 기존 파일은 고치지 않았습니다.
새로 확인된 정적 미해결 제품 문제는 없으므로 추가 기능 고침은 권하지 않습니다.
후속 브라우저 audit로 B001~B100을 확인하고, 확인된 문제만 마지막 polish로 다룹니다.

상수 제거 전 backend의 사용처를 검색했습니다. 제거한 Python 상수는 `_LEGACY_POLISH_TEXT` 하나뿐입니다.
이 상수는 자기 선언과 POLISH_TEXT 합침 외에는 사용되지 않았습니다. 이제 `POLISH_TEXT = UI_TEXT`입니다.
START_TEXT·FIELD_HELP·TRY_STAGE_HELP·JOB_UI_TEXT·GLOSSARY와 API 함수는 남겼습니다.
외부 참조가 없는 `_GLOSSARY_ALIASES`, `_ROW_LABELS`, `_CONDITIONS`, 오류 정규식과 LOADING_LATE_MIN도 내부 사용처가 있어 남겼습니다.
이 phase 전부터 있던 죽은 코드는 제거하지 않았습니다. 이번 대조에서 추가 삭제를 정당화할 상수는 확인하지 못했습니다.

#### CRITIQUE 24개 처리 추적

아래의 ‘처리’는 코드·계약 및 자동 시험의 상태입니다. 실제 화면의 해결 판정은 브라우저 목록에 남습니다.

| 문제 | 처리한 step | 처리 또는 범위 밖 이유 |
|---|---|---|
| 01 공통 맥락 없음 | 1 | 모든 화면의 문서 묶음·정답지·모델 상태와 P01 선택 |
| 02 서버가 고급 뒤에 숨음 | 1·5·6 | S06 메뉴 노출과 S03 제자리 연결 |
| 03 실행 목적·긴 이름 혼재 | 2·4·6·9 | run_kind 묶음·사람 말 표시 이름·원래 이름; label 객체 표시 수정 |
| 04 작업 순서 불명확 | 1·6 | 일곱 메뉴와 시험·여러 문서·작업 기록의 승인 분리 |
| 05 옛 입력 경로 | API 단계·3 | 실행 원문 경로 이동 정보와 현재 시험 묶음을 구분 |
| 06 기본 입력이 비거나 부적합 | API 단계·1·6 | 사용 가능한 묶음과 문서별 runnable·reason 사용 |
| 07 안내에 실제 시험 성공 없음 | 6·7 | 두 갈래와 결과 ok·dry_run을 확인한 성공 기록 |
| 08 다시 보기로 성공 지움 | 7 | journey v2의 outcomes 보존; 다시 보기와 닫기는 진행만 변경 |
| 09 같은 조건 차이를 개선·악화로 단정 | 4 | 조건을 먼저 보이고 같은 조건 차이는 중립·흔들림으로 표시 |
| 10 점수 카드 중복 | 2 | 총점과 목표 및 최대 손실을 요약하고 세부를 펼침 |
| 11 좁은 열과 큰 빈 공간 | 1·3·6·9 | 승인 데스크톱 격자·허용 데이터 줄바꿈·S02 행 충돌 수정; 실배치 미확인 |
| 12 합격처럼 보이는 점수 | 2·8 | 목표선·필수 달성 수와 정답지·초안 한계로 표시 |
| 13 미기록을 0건으로 표시 | 2 | counts null과 숫자 0을 다른 글로 보존 |
| 14 이해하기 어려운 용어 | 1~8 | 승인 COPY와 UI_TEXT·첫 등장 설명·40개 용어 |
| 15 긴 도움말의 진입점 부족 | 8 | 화면별 장 직접 연결·아홉 장·원래 선택으로 복귀 |
| 16 오류의 원인·복구 없음 | 1·6·9 | 굵은 사실·할 일·접힌 원문을 열 화면 실패 시험으로 확인 |
| 17 연결 실패 원인 혼동 | API 단계·5 | no_model·tunnel_closed·loading·ok 진단과 경과시간 |
| 18 재시작 뒤 기존 Pod 재사용 실패 | API 단계·5 | session.adopted와 설정 재읽기; 실제 재시작·접속은 미확인 |
| 19 남의 Pod 삭제 위험 | API 단계·5 | owned/deletable와 API 거부를 유지; 삭제 단추 미생성 |
| 20 비용을 모르는데 무료처럼 표시 | API 단계·5 | cost_est·uptime_s를 표시하고 없음은 알 수 없음 |
| 21 모델 준비 대기 불명확 | API 단계·5 | loading_since 경과·늦은 준비 안내; 기대 모델 응답으로 준비 판정 |
| 22 빈 자료와 잠김 혼동 | API 단계·1·3·6 | usable·runnable·reason으로 빈 상태와 잠금 분리 |
| 23 한국어 단어 중간 끊김 | 1·9 | 본문 keep-all·허용 데이터 class만 anywhere·break-all 금지 검사 |
| 24 좁은 휴대폰 화면 | 범위 밖 | 사용자 결정에 따라 데스크톱 1280~1680px만 다룸 |

#### 시험 이관과 경계

앱 회귀 첫 실행은 **1 failed, 993 passed**였습니다. 남아 있던 `test_app_js_calls_doc_api`가 삭제된 파일을 읽는 실패였습니다.
그 시험은 삭제하지 않았습니다. `test_source_calls_doc_api_and_uses_the_returned_page_route`로 옮겼습니다.
옛 파일의 `/api/doc`·`/pages/` 문자열 검사를 새 화면의 요청·문서 인자·API가 준 실제 그림 주소 검사로 강화했습니다.
다시 실행한 앱 시험은 **994 passed, 1194 deselected, 7 warnings**입니다.
옛 polish 파일의 마지막 동작과 DOM 대역은 같은 step의 audit 시험으로 대체했습니다.
`test_B_b_app.py`의 STATIC_FILES는 삭제된 파일만 제외했고 정적 경로 보안·HTML 주입·외부 주소 금지는 유지했습니다.
`test_B_b_app_text.py`는 요구된 UI_TEXT 별칭 계약으로 바꿨으며 API 문구 계산이나 기존 반환 키는 바꾸지 않았습니다.

아키텍처 체크: index.html + 일반 JS 10개 + app.css + guide.html 구조입니다. 새 패키지와 빌드 도구는 없습니다.
ADR-028의 전역 선택·정보 보존·두 갈래·서버 노출을 유지합니다. 승인 파일은 수정하지 않았습니다.
UI_GUIDE의 색+글·금지 효과·초점·한국어·데스크톱 범위를 정적 시험으로 확인했습니다.
테스트는 가짜 자료와 가짜 API만 사용합니다. C의 전처리 시험은 제외했습니다.
실제 문서·TO21 자료·.env·모델 서버·SSH를 사용하지 않았습니다. 런타임·다른 역할 코드·백엔드 API는 변경하지 않았습니다.
커밋하지 않습니다. 완료 기록 뒤 실행기가 다시 검증합니다.

#### 최종 검증

- AC의 파일 삭제·옛 이름 제거·금지 CSS·외부 주소 금지·기록 절·Node 존재 명령을 직접 실행했고 종료 코드 0입니다.
- audit/DOM은 **53 passed**입니다. 앱 전체는 **994 passed, 1194 deselected, 7 warnings**(28.29초)입니다.
- 전체 시험은 **2157 passed, 30 skipped, 7 warnings, 1 failed**(56.85초)입니다.
- 유일한 실패는 `tests/test_A_input.py::test_every_changing_route_answers_with_update`의 `socket.bind` → `PermissionError: [Errno 1] Operation not permitted`입니다. `_common.txt` 7절의 명시 예외에 따라 completed로 기록합니다. A 시험은 수정하거나 빼지 않았습니다. 실행기가 샌드박스 밖에서 다시 검증합니다.
- 경고 7개는 기존 SWIG 타입의 `__module__` 관련 DeprecationWarning입니다.
- JS 10개 문법 검사와 `git diff --check`를 통과했습니다. 기존 Python 함수 35개의 이름·인자는 같습니다.
- 시작 때 기록한 보호 파일 120개의 SHA-256이 같습니다. docs·CLAUDE·하네스·승인 설계는 바꾸지 않았습니다. index.json은 step 9의 status·summary만 바꿉니다.
- 최종 남은 수: 새 정적 제품 지적 0, 기존 wireframes 지적 15, detector 오탐 2, 기존 API 빈칸 2, 미실행 브라우저 확인 100줄입니다.
- 브라우저·실제 모델·장비 확인과 커밋은 수행하지 않았습니다.


## S5 고침

### fix step 0

⚠️ DEGRADED: no browser in sandbox

Questions skipped: non-interactive. 승인 구조와 모양은 유지한다.

| 고친 번호 | 시험 이름 | 확인 방법 |
|---|---|---|
| F01 | `test_dom_stringifies_non_node_arguments_like_browser`, `test_help_renders_nine_chapters_as_elements` | DOM 대역을 고친 뒤 도움말 0/9개 실패를 재현. coreReplace로 배열을 펼쳐 장 9개와 점수 기준 영역이 실제 요소로 붙음을 확인. |
| F02 | `test_model_lookup_failure_is_not_ai_off` | 개별 조회 실패를 꺼짐으로 표시하는 실패를 재현. shellModelState를 공통 줄과 S06에서 재사용해 실패·미확인·다른 모델·켜는 중·통로 닫힘·확인된 꺼짐을 구분. |
| F03 | `test_saved_results_do_not_wait_for_model_status` | 모델 미응답 중 S01·S02 조회 막힘과 종료 조건 부재를 재현. contextReady로 선택 준비를 분리해 S01·S02·갈래 1을 그림. 모델 요청은 60초에 중단하고 늦은 응답을 무시함. 채점 중 실행 수와 처음에는 수십 초 안내 확인. |
| F04 | `test_missing_key_name_shows_unknown_not_draft` | 이름 누락 시 목록 이름 대신 실버를 표시하는 실패를 재현. shellKeyLabel로 응답 id에 맞는 목록 이름을 찾고, 없으면 확인 안 됨. shellKeyMismatch로 전역 선택과 차이를 표시. |
| F05 | `test_try_success_requires_http_200` | 202·206 성공 오기록과 JSON 읽기 실패 시 복구 단추 없음 재현. api의 선택 인자 withStatus로 상태와 본문을 보존. resultStatus가 정확히 200일 때만 성공 사건을 내보냄. 202·204·206·읽기 실패는 성공 없음과 재조회 복구 확인. |
| F06 | `test_retest_focus_shows_plain_values_not_json` | S02에서 고른 숫자 묶음이 S03에서 JSON으로 보이는 실패를 재현. sourceRemember가 기존 표시 글을 메모리에 전달하고 jobsFocusValue는 raw 또는 표시 글을 사용. 정답과 AI 값 모두 확인. |

시험 선행: DOM 계약 시험은 대역 수정 전에 실패했다. 대역 수정 뒤 나머지 여섯 이름의 시험에서 실패를 확인했다(세부 경우 10 실패, 3 통과).


#### 배열 전달 전수 확인

`js/` 전체의 append·prepend·replaceChildren·before·after·replaceWith 호출을 읽었다. 배열이 직접 도달할 수 있던 곳은 **2곳**이다. `h`·`fill`·`coreReplace` 내부와 이미 전개한 호출은 그대로 둔다.

| 위치 | 원인 | 고침 |
|---|---|---|
| `help.js:helpRenderTopics` | 장 목록 배열을 replaceChildren의 인자로 전달 | `coreReplace`로 장 목록 전개 |
| `core.js:card`의 접기 옵션 없는 갈래 | content의 최상위만 전개해 그 안의 자식 배열은 문자열로 변환됨 | 기존 `coreReplace`로 자식 배열 전개 |

#### 기존 시험 변경과 이유

| 파일·시험 | 변경 | 이유 |
|---|---|---|
| `test_B_b_app_dom.py`의 Element | 여섯 DOM 메서드는 배열·객체도 String 값으로 삽입. AbortController를 실행 환경에 제공 | 실제 브라우저의 배열 문자열 변환과 요청 중단 계약을 검증하기 위함 |
| `test_B_b_app_dom.py:run_js` | 비동기 본문이 끝난 표식을 확인 | Node가 미완료 Promise를 남긴 채 종료 코드 0으로 끝내는 것을 시험 성공으로 세지 않음 |
| `test_B_b_app_jobs_ui.py:SETUP` | 선택 인자 withStatus 요청에 HTTP 상태와 본문을 반환 | 결과 응답 상태를 보존하는 새 요청 계약. 기존 api 호출은 본문만 반환. 기대값은 유지 |
| `test_result_race_does_not_overwrite_selected_job_and_whole_has_no_event` | 지연 응답 대역도 withStatus를 전달하고 상태 200을 포함 | 늦은 응답과 대상 교체 검증을 유지하며 실제 응답 계약에 맞춤. 기대값은 유지 |
| `test_model_connection_names_count_neutral_absence_and_error_recovery` | 빈 모델 목록의 기대를 꺼짐에서 준비 여부 미확인으로 변경 | 빈 목록만으로 모델이 꺼졌음을 확인하지 못함. F02와 승인 context 문구에 맞춘 변경 |
| `test_start_draws_navigation_before_pending_requests_and_polls_without_duplicates` | 시작 완료 뒤 별도 모델 조회 완료를 기다린 다음 타이머 비교 | F03에서 시작 준비와 모델 조회를 분리함. 중복 조회·타이머 수 검증의 기대값은 유지 |

기존 시험 삭제 없음. `test_B_b_app_journey_ui.py`와 `test_B_b_app_help_ui.py`의 기대값 변경 없음.

#### API·문구·경계 확인

- 백엔드 응답 키와 인자는 변경하지 않았다. 기존 `api(path, options)`의 반환값은 본문이다. `withStatus: true`일 때만 `{status, data}`를 반환하며 이 옵션은 fetch로 보내지 않는다.
- `session.ready=false`는 응답이 없다는 뜻이다. 이것만으로 빌린 서버가 켜지는 중이라고 추정하지 않는다. RNGD의 명시적 `diagnosis=loading`은 승인된 ‘켜는 중 · 회사 서버’로 표시한다.
- `score.basis.fallback`은 승인된 `jobs.external.unknown`의 ‘확인 안 됨’을 재사용한다. 기존 BUILD의 ‘이름 누락이면 실버’ 기록은 이 고침으로 대체한다. 해당 문장은 새 문구가 아니므로 COPY_EXCEPTIONS에서 제거한다.
- 신규 문장 1개는 아래 승인 대기 표에 등록했다. COPY.md는 수정하지 않았다.
- 원문 표시 글은 S.focus 메모리에만 남긴다. journey 저장 필드는 바꾸지 않았다.
- 화면 순서·배치·CSS·색은 변경하지 않았다. 상태는 기존 색과 글을 함께 사용한다. 채점 계산과 API 응답 키도 그대로다.
- 시험은 직접 만든 문서와 가짜 API·fetch·시계만 사용한다. 모델 서버·SSH·외부 네트워크를 호출하지 않는다. 평가 문서 내용과 비밀값은 쓰지 않았다. 전체 AC는 C 전처리 시험을 지정대로 제외한다.
- impeccable context와 harden·craft-floor를 읽었다. detect는 한 번 실행했다(종료 코드 2). 지적 17건은 수정하지 않은 wireframes.html 15건과 guide.html 2건이며 변경 파일은 0건이다. `/static/app.css`를 로컬 경로로 읽지 못한다는 경고가 있어 색 검사는 불완전하다. 다른 step의 모양 작업은 수행하지 않았다.

#### 최종 완료 기준 검증

- 지정 AC를 `/tmp/to21-fix-step0-ac.sh`에 그대로 적어 저장소 최상위에서 bash로 실행했다. 로그는 `/tmp/to21-fix-step0-ac.log`다.
- 파일·BUILD 제목·F01~F06 행·Node 존재 확인은 통과했다. 새로 지정한 시험 7개 이름의 세부 경우 **13 passed**(1.54초).
- 앱 관련 회귀: **1011 passed, 1194 deselected, 7 warnings**(30.67초).
- 전체 지정 시험: **1 failed, 2174 passed, 30 skipped, 7 warnings**(61.46초). AC 스크립트 종료 코드는 1이다.
- 유일한 실패: `tests/test_A_input.py::test_every_changing_route_answers_with_update`. `HTTPServer`의 `socket.bind`에서 `PermissionError: [Errno 1] Operation not permitted`가 발생했다. A 시험을 수정하거나 제외하지 않았다.
- `phases/app-redo/_common.txt` 7절이 이 단일 포트 제한 실패를 명시적으로 허용하므로 step 0을 completed로 기록한다. 실행기가 샌드박스 밖에서 다시 검증한다.
- 경고 7개는 기존 SWIG 타입의 `__module__` 관련 DeprecationWarning이다.
- `git diff --check` 통과. 추적 파일 변경 범위는 허용된 화면 JS·문구·BUILD·B 시험뿐이다. 새 파일은 `test_B_b_app_fix_ui.py` 하나다. docs·CLAUDE.md·실행기·승인 설계·CSS·백엔드 API는 수정하지 않았다.
- 브라우저·앱 서버·모델 서버 검증은 미실행이다. step 1~4는 pending을 유지한다. 커밋하지 않았다.

### ⑤ 승인 대기 문구

| 키 | 글 | 쓰는 곳 | 바꾼 까닭 |
|---|---|---|---|
| `context.answer_mismatch` | 이 결과의 정답지는 현재 선택과 다릅니다. 결과: {result_key}. 현재 선택: {selected_key}. | S01 점수 기준·S02 정답지 표시 | F04: 결과의 정답지와 전역 선택을 구분. 같은 뜻의 승인된 일반형 문구가 없어 추가. S5 결정 2: ⑤ 수락에서 승인 대기 |
