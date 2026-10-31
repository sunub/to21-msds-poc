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
지금은 모두 빈칸으로 둡니다.

| 번호 | 옛 정보 | 옛 자리 | 새 화면·구역 | 맡는 step | 새 자리 |
|---|---|---|---|---|---|
| I01 | 앱 이름, 탭, 시작 안내, 전체 상태 문장 | `index.html #status, setupTabs` | 공통 app-header·main-nav·global-context | 1 | `#app-heading`, `#main-nav`, `#global-context`, `#status`; `shellRenderHeader/go` |
| I02 | 화면 목적과 도움말 장 연결 | `index.html .tab 설명, guide.html 장 링크` | 공통 화면 설명 → S07 help-topics | 1, 8 | `#title-s01`~`#title-s10`, `#main-nav`의 S07 단추. 화면별 설명·장 연결은 step 8 |
| I03 | 용어 말풍선, 접힘 상태, 키보드 포커스 | `term, setupTip, card, loadCards` | 공통 core 도우미 | 1 | `core.js`: `term/setupTip/card/loadCards/coreRead/coreWrite`; 말풍선·접기 새 시험 통과 |
| I04 | 앱 목적, 서버 없이 결과 확인, 점수→문제→원문 3단계 | `renderStart, journeyStep` | S08 journey-choice, S01 journey-band | 7 | |
| I05 | 단계 완료, 첫 성공 시각, 실패 후 위치 | `advanceJourney, journeyPassed, focusJourneyValue` | S08 journey-records | 7 | |
| I06 | 다음에 할 일: 비교·시험·서버 | `renderStart, journeyStep` | S01 score-summary, S08 journey-choice | 2, 7 | |
| I07 | 안내 닫기, 처음부터 다시 보기 | `resetJourney, dismissJourney` | S08 journey-records | 7 | |
| I08 | 실행 목록·읽기 실패 수·다시 읽기·채점 로딩 | `loadAll, loadRun, renderScoreLoading, scoreLoadFailure` | S01 score-summary | 2 | |
| I09 | 현재 점수·부족 점수·필수 달성 수·상위 문제 3개·다음 행동 | `renderStatus, openScoreSource` | S01 score-summary·score-problems | 2 | |
| I10 | 총점·목표선·필수 막대·전체 판정 | `renderNow, goalBar` | S01 score-summary | 2 | |
| I11 | 실행 이름·원래 폴더명·모델 태그와 전체 이름·지시문 버전·입력 폴더·시각 | `runLabel, rawRun, modelName, renderNow` | S01 score-summary 실행 조건 | 2 | |
| I12 | 완료 문서 수·진행 중·채점 수·제외 수·정답 없는 수 | `progressLine, renderNow` | S01 score-summary 채점 범위 | 2 | |
| I13 | 값 없는 행을 뺀 점수·원점수와의 차이·계산 뜻 | `renderNow` | S01 score-rule | 2 | |
| I14 | 모델 연결 안내와 저장 결과의 오프라인 조회 | `connLine, renderConnNow` | 공통 global-context, S01 score-summary | 1, 2 | `#global-context #context-model`, `shellRenderModels/shellPollServers`; 저장 결과 안내와 현재 연결 분리. S01 세부는 step 2 |
| I15 | 23개 항목의 등급 수·무게·목표·측정 방법·정답 초안 한계 | `renderRule` | S01 score-rule, S07 help-topics | 2, 8 | |
| I16 | 항목별 점수·목표선·달성 여부·미달만/모두·숨긴 수 | `renderItems, itemRow, scoreBar` | S01 score-problems | 2 | |
| I17 | 빠뜨림·지어냄·틀림의 뜻과 건수 | `renderItems, itemRow` | S01 score-problems | 2 | |
| I18 | 오류 상세 문서·종류·내용·현재 표시 제한 안내 | `detailList` | S01 score-problems → S02 source-values | 2, 3 | |
| I19 | 정답 초안의 빈 곳·출처·발견 시점 | `itemRow, /api/silver_gaps` | S01 score-gaps | 2 | |
| I20 | 항목별 값 없는 행 제외 점수 | `itemRow` | S01 score-problems | 2 | |
| I21 | 실행 이력 그래프·날짜·모델 범례·현재 실행·목표선·최고 점수 | `renderHistory` | S01 score-history | 2 | |
| I22 | 두 점 선택 순서·선택 해제·A/B로 보내기 | `savePick, renderHistory` | S01 score-history → S04 compare-summary | 2, 4 | |
| I23 | 문서별 점수·필수 미달 항목·시간·300초 목표·시간 기록 없음 | `renderDocs` | S01 score-docs | 2 | |
| I24 | 문서×16항 호출 격자·한 문서의 여러 MSDS | `renderGrid` | S01 score-grid | 2 | |
| I25 | 성공·재추출·출력 한도·실패·기록 없음·시도 수·시간·방식·한도 원인 | `gridCell, renderGrid` | S01 score-grid | 2 | |
| I26 | 표별 결과/정답 행 수·비율·남는 값(extras) | `renderRows` | S01 score-rows | 2 | |
| I27 | A/B 선택·실행 원래 이름·순서 교환·비교 중/실패 | `diffSelect, loadDiff, renderDiffTop` | S04 compare-summary | 4 | |
| I28 | 모델·지시문 버전·입력·동시 호출 수·코드 커밋·변경 조건 | `renderDiffTop` | S04 compare-conditions | 4 | |
| I29 | 총점 전후·차이·값 없는 행 제외 점수 전후 | `renderDiffTop, changeLine` | S04 compare-summary | 4 | |
| I30 | 공통 문서 수·A에만/B에만 있는 수·다른 평균의 주의 | `renderDiffTop` | S04 compare-conditions | 4 | |
| I31 | 23개 점수 차·등급·관련 항·하락만/모두·숨긴 수 | `renderDiffItems` | S04 compare-items | 4 | |
| I32 | 2점 이상 하락의 원인 후보·후보 없음 | `renderDiffItems` | S04 compare-items | 4 | |
| I33 | 지시문 변경 항·전후 줄 수·행/JSON 형식·차이 줄·재구성 해시 불일치 | `togglePrompt, promptView` | S04 compare-prompts | 4 | |
| I34 | 새로 맞춘 값·새로 틀린 값·문서·종류·내용·표시 수 | `renderDiffValues, valueTable` | S04 compare-values → S02 source-values | 4 | |
| I35 | A/B/정답 표 행 수·가까워짐/멀어짐/차이 유지 | `renderDiffRows` | S04 compare-rows | 4 | |
| I36 | 실행·문서 선택·정답 없는 개발 문서 | `initDoc, docsOf, renderDocTop` | S02 source-top | 3 | |
| I37 | 자료 불러오기 실패·할 일·예외 원문 | `renderDocTop, loadFailure` | S02 source-top | 3 | |
| I38 | 쪽 선택·16항 이름·구간 시작/끝·제목 못 찾음 | `renderDocTop, goSection` | S02 source-top·source-page | 3 | |
| I39 | 결과 값 수·같음/다름/정답에만 수·정답 없음·문서 경고 | `renderDocTop` | S02 source-top·source-values | 3 | |
| I40 | 쪽 그림·원문 줄·근거 상자·항 구간 띠·줄별 연결 값 수 | `renderDocLeft, drawBoxes` | S02 source-page | 3 | |
| I41 | 결과의 항→표→행→칸 구조·기술 경로·칸 수·항 모름 | `renderDocRight, tableBlock, rowHead` | S02 source-values | 3 | |
| I42 | 결과 값·정답 값·정답에만 있는 행/칸·근거 줄 참조·비교 상태 | `valueRow, pickSilverOnly` | S02 source-values | 3 | |
| I43 | 선택한 값/줄·연결 값 수·근거 없음·좌표 없는 줄·스크롤 위치 | `noteSel, pickValue, pickLine, scrollInto` | S02 source-selection | 3 | |
| I44 | 모델 선택·연결·다시 조회·기술 태그 | `modelSelect, connNote, loadOptions` | 공통 global-context, S03 jobs-connection, S06 servers-models | 1, 5, 6 | |
| I45 | 문서·입력 폴더·한 항/여러 항/전체 16항·기준 실행 자동/수동 | `renderJobTry` | S03 jobs-try | 6 | |
| I46 | 지시문 기본/고쳐 쓰기·불러오기·다른 모델/항에서 온 글·한 항 제한 | `renderJobTry, loadPrompt` | S03 jobs-try | 6 | |
| I47 | 지시문 임시 보관·새로고침 유실·전송 뒤 임시 파일 삭제·해시만 기록 | `renderJobTry, startTry` | S03 jobs-try, S07 help-topics | 6, 8 | |
| I48 | 모델 미호출 연습(dry-run)·실제 보내기·연결 없음 안내 | `renderJobTry, startTry` | S03 jobs-try | 6 | |
| I49 | 결과 선택·작업 번호·완료 대기·결과 JSON 없음·저장 경로 | `renderJobResult, loadResult, watchTry` | S03 jobs-result, S05 jobs-detail | 6 | |
| I50 | ① 입력: 문서·모델·폴더·분할법·MSDS 수·첫 자료만·항·형식·줄 머리·구간·쪽·이미지·경고 | `tryStages ①` | S03 jobs-result 입력 | 6 | |
| I51 | ② 지시문: 항별 해시·수정 여부·전문 비기록 | `tryStages ②` | S03 jobs-result 지시문 기록 | 6 | |
| I52 | ③ 모델 원문 답·방식·종료 이유·시간·응답 없음 | `tryStages ③` | S03 jobs-result 원래 답 | 6 | |
| I53 | ④ 읽은 결과: 성공·버린 줄·재추출·시도·입출력 토큰·오류·줄 검사·읽은 JSON | `tryStages ④` | S03 jobs-result 해석한 값 | 6 | |
| I54 | ⑤ 최종 칸의 표 행 수·객체 칸 수·해당 항 서술/남는 값 | `tryStages ⑤` | S03 jobs-result 최종 형식 | 6 | |
| I55 | ⑥ 총점 전후·기준 실행·바뀐 항목·점수 생략 사유·경고 | `scoreView, tryStages ⑥` | S03 jobs-result 점수 전후 | 6 | |
| I56 | 문서 전체의 성공/실패 항·재추출·시간·원문 답 폴더 연결 | `tryStages 문서 전체 갈래` | S03 jobs-result 전체 결과 | 6 | |
| I57 | 연습에는 ③~⑥이 없음 | `tryStages 연습 갈래` | S03 jobs-result 연습 결과 | 6 | |
| I58 | 본 실행 모델·입력·문서 모두/없음·선택 수·반복·이름·추천 이름·회차 접미사 | `renderJobRun, suggestName` | S09 jobs-run | 6 | |
| I59 | 개발 전체/탐색 이름 규칙·자동 기준 실행·잠자기 방지·서버가 요구하는 확인·시작 상태 | `renderJobRun, startRun` | S09 jobs-run, P02 action-confirm | 6 | |
| I60 | 비교표 선택 순서·실행별 이름·선택 수·목록 갱신·제목·기본 라벨·출력 경로 | `renderJobCompare, startCompare` | S10 jobs-compare, S05 jobs-detail | 6 | |
| I61 | 작업 종류·내용·시작·상태·회차 진행·외부 프로세스·중단 가능 여부 | `renderJobList, progressText` | S05 jobs-list | 6 | |
| I62 | 작업 결과·로그·닫기·종료 코드·스크롤 유지·갱신·중단 경고 | `openLog, refreshLog, stopJob` | S05 jobs-detail, P02 action-confirm | 6 | |
| I63 | 현재 연결 모델·태그·조회 시각·재조회·서버 작업 진행과 마지막 결과 | `renderSrvTop, pollServers` | 공통 global-context, S06 servers-summary | 1, 5 | |
| I64 | 세션 Pod 번호·준비 여부·자동 삭제 감시·작업에 전달되는 연결 | `renderSrvTop, srvDetail` | S06 servers-summary·servers-runpod | 5 | |
| I65 | 태그·기대 모델·서버 종류·주소 설정 여부·응답 여부·응답 모델·일치·오류 | `renderSrvModels` | S06 servers-models | 5 | |
| I66 | 서버 변경 잠금·잠긴 이유·최신 조회 실패의 조작 금지 | `srvBtn, lockNote` | S06 servers-summary | 5 | |
| I67 | Pod ID·이름·앱 소유 여부·상태·자동 삭제까지·시간당 요금·가동시간·추정 비용 | `renderSrvRunpod` | S06 servers-runpod | 5 | |
| I68 | Pod 생성·삭제·계정 오류·네트워크 볼륨 수와 비용 | `renderSrvRunpod` | S06 servers-runpod, P02 action-confirm | 5 | |
| I69 | RNGD 카드 수·실행 모델·프로세스·사용 카드·올릴 모델 선택·올리기/내리기 | `renderSrvRngd` | S06 servers-rngd | 5 | |
| I70 | 가린 장비 명령 출력·진단 오류·15~25분 대기·프로세스와 준비 완료의 차이 | `renderSrvRngd, srvDetail` | S06 servers-rngd | 5 | |
| I71 | 서버 기록 마지막 10줄·기록 경로·수동 사용기록 이관 안내 | `renderSrvLog` | S06 servers-log, S07 help-topics | 5, 8 | |
| I72 | 변경 요약·주의·확인 만료·한 번 사용·취소·실패·삭제 후 남은 Pod·모델 내린 PID | `openSrvDialog, closeSrvDialog, srvExecute` | P02 action-confirm, S06 servers-summary | 5 | |
| I73 | 도움말 전체 9장·장 링크·안내 재시작 | `index.html #help-frame, guide.html #s1~#s9` | S07 help-topics, S08 journey-choice | 7, 8 | |
| I74 | 도구 역할·PDF→쪽 글자→16항→결과→채점·실행 이름 해설 | `guide.html #s1` | S07 help-topics flow | 8 | |
| I75 | 점수 해석·가중치·필수 목표·정답 초안 한계·원인 후보 기준 | `guide.html #s2, #s3` | S07 help-topics score | 8 | |
| I76 | 설정 변수 6개의 이름과 뜻·예제 파일·로컬 앱 시작 명령 | `guide.html #s4` | S07 help-topics setup | 8 | |
| I77 | 시험 순서·6단계 뜻·터미널 실행과 7개 옵션 | `guide.html #s5` | S07 help-topics retest | 8 | |
| I78 | 지시문 출처 3곳·수정 반영 파일·버전 증가·해시·임시성·반복 시험 | `guide.html #s6` | S07 help-topics prompt | 8 | |
| I79 | 출력 한도 원인 3종·열 수 불일치·300초 초과·연결 오류 | `guide.html #s7` | S07 help-topics recovery | 8 | |
| I80 | 평가 보호·비밀값 보호·문서 보호·Pod 비용·전처리 시험 제외 명령 | `guide.html #s8` | S07 help-topics protection | 8 | |
| I81 | 용어 뜻·예, 용어 로딩 실패, 채점 항목 23개의 이름·등급·설명 | `guide.html #s9, /api/glossary` | S07 help-glossary | 8 | |
| I82 | 값 말풍선의 쉬운 칸 이름과 알려지지 않은 값과 0·false 보존 | `valueRow, tipOf` | S02 source-values | 3 | |
| I83 | 결과·정답·정답에만 있는 값의 원래 JSON과 안전한 글자 표시 | `noteSel, pickValue, pickSilverOnly` | S02 source-selection | 3 | |
| I84 | 조회 실패의 사실·할 일·접힌 원문과 불러오는 중 표시 | `loadFailure, friendlyError, rawError` | 공통 오류 → 각 화면 상태 구역 | 1, 9 | |
| I85 | 원문 범례의 네 상태와 색·글과 선택 구간 요약 | `renderDocMain, renderDocRight` | S02 source-top·source-values | 3 | |
| I86 | 도움말 1장: 이 도구는 무엇을 하나 | `guide.html #s1` | S07 help-topics: help.guide.flow | 8 | |
| I87 | 도움말 2장: 점수는 어떻게 읽나 | `guide.html #s2` | S07 help-topics: help.guide.score | 8 | |
| I88 | 도움말 3장: 탭마다 무엇을 보나 | `guide.html #s3` | S07 help-topics: flow·source·retest·servers와 S08 링크 | 8 | |
| I89 | 도움말 4장: 처음 한 번 준비 | `guide.html #s4` | S07 help-topics: help.guide.setup | 8 | |
| I90 | 도움말 5장: 시험 하나 돌리기 | `guide.html #s5` | S07 help-topics: help.guide.retest | 8 | |
| I91 | 도움말 6장: 안내문을 바꿔 보기 | `guide.html #s6` | S07 help-topics: help.guide.prompt | 8 | |
| I92 | 도움말 7장: 자주 보는 실패 네 가지 | `guide.html #s7` | S07 help-topics: help.guide.recovery | 8 | |
| I93 | 도움말 8장: 하지 말 것 | `guide.html #s8` | S07 help-topics: help.guide.protection | 8 | |
| I94 | 도움말 9장: 용어 풀이와 채점 항목 23개 | `guide.html #s9, /api/glossary` | S07 help-glossary와 help-topics score | 8 | |

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
| `test_B_b_app_start_ui.py::test_start_optional_children_never_render_null` | 선택적 자식이 없어도 null·undefined·false 글자가 노출되지 않음 | `test_B_b_app_journey_ui.py` | 7; 파일 삭제 |
| `test_B_b_app_start_ui.py::test_start_state_restore_reset_and_storage_denied` | 해시 우선과 저장 실패 복구 보존. 첫 화면은 S01 띠로 변경. 재시작은 v2 성공 기록 보존으로 교체 | `test_B_b_app_journey_ui.py` | 7; 파일 삭제 |
| `test_B_b_app_start_ui.py::test_start_score_requires_loaded_visible_current_run` | 현재 실행의 점수가 실제 보이는 상태에서만 안내 단계 진전 | `test_B_b_app_journey_ui.py` | 7; 파일 삭제 |
| `test_B_b_app_start_ui.py::test_start_tabs_hash_advanced_status_link_and_help_replay` | 해시 이동과 상태 링크와 도움말 재시작 유지. 서버 숨김은 승인에 따라 제거 | `test_B_b_app_journey_ui.py` | 7; 파일 삭제 |
| `test_B_b_app_start_ui.py::test_start_navigation_buttons_never_complete_and_no_drops_offer_diff` | 이동 단추 클릭만으로 완료하지 않음. 실행 없음과 문제 없음에도 정직한 다음 행동 | `test_B_b_app_journey_ui.py` | 7; 파일 삭제 |
| `test_B_b_app_start_ui.py::test_start_success_needs_mismatched_value_in_selected_section_and_rendered_line` | 고른 항의 다른 값과 실제 표시된 근거 줄이 함께 선택되어야 성공. 중복 열기는 최초 시각 보존 | `test_B_b_app_journey_ui.py` | 7; 파일 삭제 |
| `test_B_b_app_polish_ui.py::test_server_log_copy_instruction_only_appears_with_lines` | 서버 기록이 있을 때만 수동 이관 안내. 없으면 빈 상태 | `test_B_b_app_servers_ui.py` | 5 |
| `test_B_b_app_polish_ui.py::test_item_toggle_is_button_and_preserves_focus_and_expansion` | 항목 펼침은 button과 aria-expanded. 펼침 후 초점과 상세 보존 | `test_B_b_app_score_ui.py` | 2 |
| `test_B_b_app_polish_ui.py::test_changed_values_toggle_is_button_and_keeps_both_lists` | 바뀐 값 펼침은 button. 초점 유지. 고친 값과 새로 틀린 값 두 목록 보존 | `test_B_b_app_compare_ui.py` | 4 |
| `test_B_b_app_polish_ui.py::test_history_points_are_buttons_and_storage_denial_keeps_selection` | 이력의 점은 키보드 button과 aria-pressed. 저장 거부에도 선택과 초점 유지 | `test_B_b_app_score_ui.py` | 2 |
| `test_B_b_app_polish_ui.py::test_source_lines_are_buttons_with_selection_and_no_page_is_empty` | 원문 줄은 button. 선택 상태 표시. 그림 대체 글. 쪽 없음도 빈 화면으로 두지 않음 | `test_B_b_app_source_ui.py` | 3 |
| `test_B_b_app_polish_ui.py::test_grid_states_and_silver_status_have_visible_text` | 호출 실패·재추출·기록 없음과 정답 비교 상태에 글 표시 | `test_B_b_app_score_ui.py`<br>`test_B_b_app_source_ui.py` | 2 격자 이관, 3 나머지 이관 후 삭제 |
| `test_B_b_app_polish_ui.py::test_errors_share_fact_action_and_collapsed_raw_on_each_tab` | 모든 화면 오류에 사실·할 일·접힌 원문. 원문 글자 그대로 안전하게 표시 | `test_B_b_app_audit_ui.py` | 9; 파일 삭제 |
| `test_B_b_app_polish_ui.py::test_tooltip_targets_get_keyboard_access_without_nested_tab_stops` | 독립 말풍선은 키보드로 접근. 단추 안에 중복 tab 정지점 금지 | `test_B_b_app_shell_ui.py` | 1 |
| `test_B_b_app_polish_ui.py::test_start_pending_and_jobs_refresh_error_do_not_leave_blank_or_stale_states` | 안내 로딩을 빈 화면으로 두지 않음. 옵션 갱신 오류가 나면 오래된 양식을 그대로 내보내지 않음 | `test_B_b_app_journey_ui.py`<br>`test_B_b_app_jobs_ui.py` | 6 jobs 부분 이관, 7 삭제 |
| `test_B_b_app_polish_ui.py::test_start_shows_run_list_failure_after_guide_has_loaded` | 안내가 먼저 로드돼도 실행 목록 조회 실패를 사실·할 일로 표시 | `test_B_b_app_journey_ui.py` | 7 |
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

## 글 출처

고정 글은 `b_app_text.py`의 `UI_TEXT`에 모읍니다.
점으로 나눈 COPY 키를 같은 중첩 경로로 옮깁니다.
JS는 `T("nav.recent")` 같은 경로 조회만 합니다.
실제로 없는 키는 `⟦키⟧`로 드러나게 합니다.
`POLISH_TEXT`는 옛 키와 새 `UI_TEXT`를 함께 담습니다.
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
| D11 | COPY 설명은 용어 40개. `help.terms.title`은 38개 | term 키 40개를 모두 보존. step 8이 수량 문구를 고쳐야 하면 COPY_EXCEPTIONS에 근거를 남김 | 8 |
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

## 브라우저로 볼 것

각 구현 step이 가로 1280·1440·1680px에서 사람이 확인할 항목을 여기에 추가합니다.

step 1의 브라우저 확인 목록입니다. 이번에는 실측하지 않았습니다.

- 1280·1440·1680px에서 머리와 왼쪽 메뉴와 세 칸 맥락 줄의 정렬을 확인합니다. 페이지 가로 스크롤이 없어야 합니다.
- 긴 묶음 이름·정답 이름·모델 이름과 날짜를 넣어 겹침과 잘림을 확인합니다.
- 한국어 단어가 중간에서 끊기지 않는지 확인합니다. 긴 경로·태그만 허용 class에서 줄바꿈해야 합니다.
- 메뉴·카드·선택창을 키보드로 이동해 포커스 테두리와 선택창 취소 후 복귀를 확인합니다.
- 묶음·정답지 선택의 적용과 취소를 확인합니다. 쓸 수 없는 후보의 이유와 현재 수정 시각은 보여야 합니다. 내용 지문은 접힌 상세에 있어야 합니다.
- 말풍선 포커스·Escape·포인터 이동과 스크롤 중 맥락 줄 유지를 실제 브라우저에서 확인합니다.


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
