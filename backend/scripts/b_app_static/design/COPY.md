# 관문 ④ 문구 정본

문구 시안은 그대로 두고 구현용 표로 정리했습니다.

## 적용 계약
- 아래 표의 `키`와 `글`을 `backend/scripts/b_app_text.py`의 `UI_TEXT`로 옮깁니다. 점으로 나눈 이름은 중첩 경로입니다. 같은 글은 한 키만 정의합니다.
- `{score}`, `{count}`, `{section}` 등은 API 응답으로 채울 자리입니다. 자리 이름을 화면에 출력하지 않습니다. 예: `compare.score_value`에 `score=82.4`를 넣으면 시안의 `82.4 / 100점`입니다.
- 표의 HTML 문자 표기는 화면 글자로 풀어 읽습니다. 줄바꿈 표기 `<br>`는 실제 줄바꿈입니다. 키 순서에 동작을 연결하지 않습니다.
- 문서명·수치·원문 줄·모델 답·실행명·지시문 본문은 API 데이터입니다. 고정 문장을 데이터로 넘기지 않습니다.
- `쓰는 곳`은 STRUCTURE 화면 번호 또는 기존 문구 생성 함수입니다. 모든 사용 장면과 자리값은 검토 전용 `COPY-coverage.md`에 있습니다. UI 구현 단계에서는 그 파일을 읽지 않습니다.
- 시안 목록, 목록으로 가는 링크, 시안 제목, 장면 설명용 속성, 디자인 확인용 바닥글은 앱 문구에서 제외합니다.
- 쉬운 말 뒤에 원래 용어를 씁니다. 오류는 사실 뒤에 할 일을 보입니다. 색만으로 뜻을 전달하지 않습니다. 시험을 다시 하는 행동 이름은 유지합니다.
- 비용과 대기는 응답값을 씁니다. 앱이 만든 서버만 생성 후 4시간 자동 삭제 대상입니다. 예약 확인에는 앱 실행이 필요합니다.
- 점수 없음은 0점이 아닙니다. 문제 건수는 손실 점수로 환산하지 않습니다. 목표 달성은 제품 안전 판정이 아닙니다.

## 첫 사용 안내 두 갈래

진행·실제 성공·연습을 따로 기록합니다. 버튼을 누른 사실만으로 성공 처리하지 않습니다.

|단계|화면|완료 조건|
|---|---|---|
|첫 선택|S08|저장 결과가 있으면 결과 읽기를 먼저 권함. AI 없이 가능.|
|1-1|S01, S08|최근 점수와 두 목표를 읽음.|
|1-2|S01 → S02|총점 손실이 가장 큰 기준의 문제 값을 엶.|
|1-3|S02|문제 값과 실제 원문 줄이 함께 선택됨. 추정 줄만 열면 미완료.|
|2-1|S03|시험 가능한 개발 문서 하나와 부분 하나 선택.|
|2-2|S03, S06|새 모델 응답으로 준비 확인. 없으면 준비 또는 연습.|
|2-3|S03|실제 전송 후 대기. 응답이 불명확해도 자동 재전송 금지.|
|2-4|S03|작업 정상 종료와 선택 부분 해석 성공. 대상이 같은 결과 요약을 엶.|
|2-P|S03|AI 없이 입력만 확인. 연습만 기록하고 모델 준비 단계 유지.|
|재시작·복구|S08|성공 이력 보존. 안내를 닫아도 작업은 계속됨. 취소한 시도의 늦은 응답은 성공에 포함하지 않음.|

## 용어표 — 47개

아래 `glossary` 표에 용어와 설명을 한 번씩 정의했습니다.
시안의 38개 용어를 유지합니다. 허용 농도와 농도 단위 두 용어는 S01·S02 첫 등장에서도 설명합니다.
11/2 step 6에서 일곱 개를 더했습니다. TWA, STEL, ACGIH, LD50, LC50, EC50은 원문 맞춰 보기의 행 제목에 나옵니다. 서버를 끄는 순서는 AI 켜기와 비용 ④의 말풍선입니다.

## 이름 바꾸기

|이전 말|정본 키|
|---|---|
|안내문 / 지시문|jobs.fields.prompt|
|입력 판|glossary.input.term|
|실버|context.answer_draft|
|골드|glossary.gold.term|
|목표선|score.summary.headline_below|
|꼭 맞춰야 하는 기준|score.summary.must_some|
|기준 실행|glossary.base_run.term|
|한 부분 교체 점수|jobs.result.partial_score|
|입력 확인 연습|jobs.actions.preview|
|보호 조건과 만료|servers.confirm.conditions|
|채점|score.summary.unscored|
|연결 안 됨|context.model.state_off|
|미리 쓴 확인 정보|servers.confirm.once|
|문서 바꾸기|context.change_documents|
|정답 바꾸기|context.change_answer|
|AI 상태 보기|context.prepare_model|

## guide.html 구성

각 장의 제목과 설명은 `help.guide.<장>.title`, `help.guide.<장>.summary`입니다.

|순서|장 키|답하는 일|
|---|---|---|
|1|flow|앱의 처리 순서|
|2|score|점수 읽기|
|3|source|원문 확인|
|4|setup|설정 준비|
|5|retest|한 부분 시험|
|6|prompt|지시문 수정|
|7|servers|연결과 비용|
|8|recovery|문제 복구|
|9|protection|자료 보호|

## 잘못된 접속 주소 안내 교정

`friendly_error(env)`는 누락된 주소의 종류에 맞춰 안내합니다.

|설정|주소 형식 키|복구 키|
|---|---|---|
|RUNPOD_VLLM_BASE_URL|help.settings.runpod_url_pattern|errors.env.runpod_url|
|RNGD_BASE_URL|help.settings.company_url_pattern|errors.env.company_url|
|그 밖의 주소|모델 설정에서 확인|errors.env.unknown_url|

빌린 서버에는 회사 서버의 터널 예를 붙이지 않습니다. 주소 형식 두 개만 문구표에 남깁니다. 실제 주소와 비밀값은 표시하지 않습니다.

## 기존 문구 생성부 이관표

계산과 판별은 유지합니다. 표의 키 묶음으로 문구만 이관합니다.

|기존 이름|새 키 묶음|주의|
|---|---|---|
|POLISH_TEXT|common.legacy|색 외의 상태 설명 유지|
|START_TEXT|journey.start, journey|두 갈래 안내|
|FIELD_HELP, TRY_STAGE_HELP, JOB_UI_TEXT|jobs.fields, jobs.stages, jobs.actions|연습과 실제 시험 구분|
|order_models, try_hint|context.model, jobs.try_hint|준비 안 됨과 조회 실패 구분|
|GLOSSARY, glossary_entries, explain|glossary|40개. 검색 별칭 유지 가능|
|diff_headline, diff_ui_text|compare|차이를 원인으로 단정하지 않음|
|connection_note, connection_notes|context.model|연결 없이 저장 결과 읽기|
|VALUE_FIELD_LABELS, value_tip_lines|source.fields, source.value|미지의 키와 0 및 false 보존. 원래 값은 API 데이터|
|doc_legend, doc_ui_text|source.legend, source.doc|추정과 실제 근거 구분|
|score_status|score.summary|가장 큰 문제는 top_problem 사용|
|card_summary, _ROW_LABELS|score.summary, score.tables|없음과 0 구분|
|MODEL_LABELS, model_label|context.models|모르는 이름은 API 데이터로 표시|
|RUN_KIND_LABELS, run_kind_label|jobs.kinds|평가용 내용 열람 금지|
|_CONDITIONS, _condition, _date, run_label|common.conditions, common.run|없는 기록을 추정하지 않음|
|SET_TEXT, set_label|context.set_reason, context.set|문서별 runnable/reason 사용|
|KEY_TEXT, key_label|context.key_reason, context.key|사람 확인 정답은 일부 개발 문서|
|friendly_error, env_problem|errors.connection, errors.env, help.settings|서버별 주소 안내|
|JOB_ERROR_TEXT, job_error|errors.job|원문 오류는 비밀값을 가린 상세로 표시|
|PROBLEM_TEXT, problem|errors.request|오류 식별자와 설명 구분|
|JOURNEY_TEXT, journey_problem|journey.record|성공 이력 보존|
|SERVER_TEXT, server_controls|servers.messages, servers.controls|앱 소유 서버만 삭제|
|rngd_diagnosis, server_ui_text|servers.diagnosis, servers.status|시간만으로 완료·실패 판정 금지|
|_number, item_section, _doc_losses, score_losses, score_targets, _prompt, _input_version|고정 문구 없음|기존 계산과 판별 유지|

## 막힘 → 바꾼 글

|막힘|정본 키|화면|
|---|---|---|
|건수와 손실 점수의 관계|score.summary.counts_meaning, score.summary.loss_meaning|S01, S08|
|사람 확인 전 점수의 신뢰|context.answer_trust, context.answer_draft|전역|
|서버 선택과 요금·대기|servers.choice, servers.confirm.once, servers.confirm.expires, errors.confirm_expired.todo|S06, P02|
|연결 안 됨이 오류인지|context.model.state_off, context.model.off_normal, context.model.saved_readable|전역|
|한 부분 교체 점수|jobs.result.partial_score, jobs.result.partial_meaning|S03|
|AI에게 시킬 일|jobs.prompt.hint, jobs.fields.prompt|S03|
|전역 변경 링크의 시점|context.change_documents, context.change_answer, context.prepare_model|전역|
|처음 듣는 말|common.document_definition, source.unit_first_use, score.summary.exposure_section, glossary|S01, S02, S07|

## 화면과 상태별 문구

### nav — 전역 메뉴

키|글|쓰는 곳
---|---|---
nav.app_name|화학 안전문서 AI 결과 검토|전역
nav.purpose|AI가 안전 문서에서 뽑은 값을 정답과 비교합니다.|전역
nav.open_guide|처음 사용 안내 열기|전역
nav.open_jobs|진행 중 작업 보기|전역
nav.recent|최근 결과|전역
nav.source|원문과 맞춰 보기|전역
nav.retest|다시 시험|전역
nav.compare|두 결과 비교|전역
nav.jobs|작업 기록|전역
nav.servers|AI 켜기와 비용|전역
nav.help|도움말|전역
nav.current|보고 있음|전역
nav.a11y|작업 메뉴|전역
nav.group_flow|작업 순서|전역
nav.group_other|그 밖의 화면|전역

### context — 전역 상태 · P01 자료 기준

키|글|쓰는 곳
---|---|---
context.model.option|{model} — {state}|P01
context.model.state_ready|연결됨|P01
context.model.state_unknown|연결 상태 확인 안 됨|P01
context.model.state_off|AI 꺼짐|P01,E01
context.model.default_name|AI 모델|S01
context.model.checking|{model}의 연결을 확인하고 있습니다.|connection_note
context.model.failed|{model}의 연결 상태를 확인하지 못했습니다.|connection_note
context.model.ready|{model}이 응답했습니다.|connection_note
context.model.off|{model}이 연결되지 않았습니다. AI가 꺼져 있을 때는 정상 상태입니다.|connection_note
context.model.reading|저장된 점수와 원문은 AI 없이 볼 수 있습니다.|connection_note
context.model.action|할 일: 다시 시험하려면 AI 켜기와 비용에서 모델을 준비하세요.|connection_note
context.set.label_new|새 문서 폴더 · data/pages 바로 아래|P01
context.key.claude|AI 정답 초안 · Claude|P01
context.key.silver|AI 정답 초안 · {name}|P01
context.key.gold|사람이 확인한 정답 · {name}|P01
context.key.gold_main|사람이 확인한 정답|P01
context.models.qwen36_35b_runpod|Qwen3.6 35B · 빌린 서버|P01
context.models.qwen3_30b_a3b_rngd|Qwen3 30B · 회사 서버|P01
context.models.gpt_oss_20b_rngd|gpt-oss 20B · 회사 서버|P01
context.models.nuextract2_8b_runpod|NuExtract 2.0 8B · 빌린 서버|P01
context.models.qwen3vl4b_rngd|Qwen3-VL 4B · 회사 서버|P01
context.models.qwen38|Qwen3.8 27B (vLLM)|P01
context.models.claude|Claude · AI 정답 초안|P01
context.models.gpt|GPT|P01
context.set_reason.eval_locked|평가용 문서라 개발 중에는 열 수 없습니다.|P01
context.set_reason.unknown_doc|문서 목록과 문서 정보 파일에서 용도를 확인하지 못했습니다.|P01
context.set_reason.empty|이 폴더에 문서 폴더가 없습니다.|P01
context.set_reason.eval_only|평가용 문서만 있는 묶음은 고를 수 없습니다.|P01
context.set_reason.no_line_numbers|원문 줄 번호가 없어 새 시험에는 쓸 수 없습니다. 지난 결과는 읽을 수 있습니다.|P01
context.set_reason.nothing_open|열 수 있는 문서가 없습니다.|P01
context.set_reason.run_moved|실행에 쓴 {recorded} 폴더가 옮겨졌습니다. 지금은 {id}에서 읽습니다.|P01
context.set_reason.run_missing|실행에 쓴 {recorded} 폴더를 찾지 못했습니다. 지금은 {name}에서 읽습니다. 원문 줄 번호가 다를 수 있습니다.|P01
context.set_reason.no_line_numbers_doc|이 문서에 원문 줄 번호가 없습니다. 할 일: 줄 번호가 있는 묶음을 고르세요.|P01
context.set_reason.outside_try|현재 실행기는 목록 밖 문서의 한 부분 시험을 지원하지 않습니다. 할 일: 시험 가능한 개발 문서를 고르세요.|P01
context.set_reason.outside_wait|현재 실행기는 이 문서를 시험할 수 없습니다. 할 일: 시험 가능한 개발 문서를 고르세요.|P01
context.set_reason.dev_only|개발용 문서만 시험할 수 있습니다.|P01
context.key_reason.key_empty|정답 폴더에 파일이 없습니다.|P01
context.key_reason.key_no_doc_files|문서별 정답 파일이 없습니다. 파일 이름은 T21-S003.json 같은 문서 번호여야 합니다.|P01
context.key_reason.key_not_to21|정해진 결과 형식(TO21 JSON)의 정답 파일이 없습니다.|P01
context.key_reason.key_eval_only|평가용 문서의 정답만 있어 고를 수 없습니다.|P01
context.key_reason.unknown_key|정답지 {id}를 찾지 못했습니다. 할 일: 정답지 목록에서 다시 고르세요.|P01
context.key_reason.unusable_key|이 정답지를 쓸 수 없습니다. 이유: {reason}|P01
context.documents.label|시험할 문서 묶음(폴더)|전역
context.documents.short|문서 묶음|전역
context.documents.count|개발용 문서 {count}건|전역
context.change_documents|필요할 때 문서 바꾸기|전역
context.answer.label|비교한 정답|전역
context.answer.short|정답|전역
context.answer_draft|AI 정답 초안 · 사람 확인 전|전역
context.change_answer|필요할 때 정답 바꾸기|전역
context.answer_trust|점수는 개선 방향을 보는 참고용입니다. 값은 원문과 맞춘 뒤 믿으세요.|전역
context.prepare_model|시험할 때 AI 준비하기|전역
context.model.off_normal|AI가 꺼져 있을 때는 정상 상태입니다.|P01,E01
context.model.saved_readable|저장된 결과는 AI 없이 읽을 수 있습니다. 다시 시험할 때만 AI가 필요합니다.|전역
context.model.company_ready|연결됨 · 회사 서버|P01,E02
context.model.expected_reply|기대한 {model}의 응답을 확인했습니다.|P01,E02
context.set.previous_version|이전 개발 자료 {version}판|P01,S01
context.set.selected|선택한 묶음 · {set_id}|P01,S01
context.answer.gold_count|사람이 확인한 정답 · {count}건|P01,E02
context.answer.gold_scope|정답이 있는 문서만 점수를 매깁니다.|P01,E02
context.answer.doc_missing|선택 문서의 정답 없음|E05,S03
context.model.rented_ready|연결됨 · 빌린 서버|P02,S02
context.model.rented_cost|시간당 약 ${cost_per_hour} (예시). 가동 {hours}시간.|P02,S02
context.model.rented_loading|켜는 중 · 빌린 서버|S01,S06
context.model.rented_elapsed|{minutes}분 경과. 준비 중에도 요금이 나갑니다.|S01,S06
context.model.deleting|서버 삭제 확인 중|S06
context.model.deleting_cost|완료 전까지 요금이 나갈 수 있습니다.|S06
context.model.query_failed|상태 확인 실패|P02,S06
context.model.readiness_unknown|준비 여부를 확인하지 못했습니다.|P02,S06
context.model.query_pending|응답 확인 중|S06
context.model.wait_before_send|확인 전에는 시험을 보내지 않습니다.|S06
context.model.wrong_reply|고른 AI와 다른 AI가 답함|S06
context.model.mismatch|기대한 {expected_model}와 응답 {actual_model}가 다릅니다.|S06
context.model.company_loading|켜는 중 · 회사 서버|E08,S01
context.model.company_elapsed|{minutes}분 경과. 보통 15~25분이 걸립니다.|E08,S01
context.picker.title|문서와 정답을 함께 검토한 뒤 적용하세요.|P01
context.picker.set_count|이전 개발 자료 {version}판 · {count}건|P01
context.picker.draft_count|AI가 먼저 만든 정답 · {count}건|P01
context.picker.draft_origin|AI가 먼저 작성|P01
context.picker.select_draft|정답 초안 {count}건 고르기|P01
context.picker.select_gold|사람 확인 정답 {count}건 고르기|P01
context.picker.apply|선택한 기준 적용하기|P01
context.picker.cancel|변경하지 않고 돌아가기|P01
context.picker.alternatives|다른 후보와 사용할 수 없는 이유|P01
context.picker.usable|사용 가능|P01
context.picker.dev_count|개발 {count}건|P01
context.picker.draft_short|초안 {count}건|P01
context.picker.open_empty|결과 없음 상태 보기|P01
context.picker.gold_name|사람이 확인한 정답|P01
context.picker.dev_scope|개발 {count}건 중|P01
context.picker.review_gold|{count}건의 정답으로 검토하기|P01
context.picker.empty_folder|빈 자료 폴더|P01,E03
context.picker.no_text|원문 글자 없음|P01
context.picker.no_lines|줄 번호 없는 묶음|P01
context.picker.no_lines_reason|원문 근거를 확인할 줄 번호 없음|P01
context.picker.eval_set|평가용 묶음|P01
context.picker.restricted|열람 제한|P01
context.picker.dev_forbidden|개발 중 사용 금지|P01
context.picker.unreadable_key|읽을 수 없는 정답|P01
context.picker.key_format|문서별 결과 형식 확인 필요|P01
context.picker.doc_keys|문서별 정답과 출처|P01
context.picker.gold_short|사람 확인 정답|P01
context.picker.remaining_docs|나머지 개발 문서 {count}건|P01
context.picker.modified|현재 파일 수정 시각: {time}.|P01
context.picker.fingerprint|이 지문은 현재 파일 내용의 구분값입니다. 과거 점수를 복원하지는 않습니다.|P01
context.picker.effects|적용하면 바뀌는 정보|P01
context.picker.effect_set|문서 묶음을 바꾸면 해당 묶음의 실행 후보를 찾습니다.|P01
context.picker.effect_key|정답을 바꾸면 저장 결과를 새 정답으로 점수를 다시 계산합니다.|P01
context.picker.no_model_call|AI를 다시 호출하지 않습니다.|P01
context.picker.hide_stale_score|새 기준을 읽는 동안 이전 점수는 숨깁니다.|P01
context.picker.running_context|이미 보낸 작업은 시작 당시 기준을 사용합니다.|P01
context.picker.absent_selection|문서가 새 묶음에 없으면 빈 선택으로 남깁니다.|P01
context.picker.keep_valid|유효한 문서와 부분과 편집한 설명은 유지합니다.|P01
context.picker.gold_origin|사람이 검토|P01
context.applied.title|사람이 확인한 정답으로 기준을 바꿨습니다.|P01
context.applied.scope|개발용 {total}건 중 정답이 있는 {count}건만 점수를 매깁니다.|P01
context.applied.missing_count|나머지 {count}건은 정답 없음으로 표시합니다.|P01
context.applied.hide_stale|점수를 읽기 전에는 이전 {count}건의 점수를 표시하지 않습니다.|P01
context.applied.open_result|새 기준으로 결과 읽기|P01
context.absent.title|새 문서 묶음에는 보던 문서가 없습니다.|P01
context.absent.selection_cleared|문서 선택을 비웠습니다. 다른 문서를 자동으로 고르지 않았습니다.|P01
context.absent.select_doc|개발용 문서 고르기|P01,E04
context.model.tunnel_closed|연결 통로 닫힘|E07,P02
context.model.still_running|회사 서버의 모델은 실행 중입니다.|E07,P02
context.set.no_text|원문 글자 없음 · {set_id}|E03
context.a11y|현재 문서와 정답과 모델|전역

### common — 공통 상태와 표시

키|글|쓰는 곳
---|---|---
common.run.date|{month}/{day}|전역
common.run.prompt|AI에게 시킨 일 {version}|run_label
common.run.input|원문 자료 {version}|run_label
common.run.manual|앱에서 시작 · {title}|run_label
common.run.document|문서 {doc} 한 건|전역
common.run.probe|일부 문서 시험 {round}회|전역
common.run.diagnostic|문제 확인 {run_id}|전역
common.run.repeat|{round}회차|전역
common.run.eval|평가용 문서 한 건 · 열람 제한|전역
common.run.title|{date} {model} · {conditions}|run_label
common.legacy.load_error.message|자료를 읽지 못했습니다.|전역
common.legacy.load_error.fix|할 일: 앱을 켠 터미널의 오류를 보고 화면을 다시 여세요.|전역
common.legacy.request_error.message|요청을 완료하지 못했습니다.|전역
common.legacy.request_error.fix|할 일: 현재 화면의 입력과 연결 상태를 확인한 뒤 다시 시도하세요.|전역
common.legacy.cell_labels.c_none|기록 없음|S01
common.legacy.cell_labels.c_ok|성공|전역
common.legacy.cell_labels.c_re|다시 뽑아 성공|전역
common.legacy.cell_labels.c_limit|길이 제한 뒤 성공|전역
common.legacy.cell_labels.c_fail|실패|S01,S05
common.legacy.silver_labels.diff|정답과 다름|S02,S08
common.legacy.silver_labels.only|정답에만 있음|S02,S08
common.legacy.silver_labels.missing|정답에 없음|전역
common.legacy.row_change.up|정답에 가까워짐|S04
common.legacy.row_change.down|정답에서 멀어짐|S04
common.legacy.row_change.same|차이 유지|S04
common.legacy.changed|조건 다름|전역
common.legacy.no_pages|원문 쪽 자료가 없습니다. 할 일: 원문이 있는 문서 묶음을 고르세요.|전역
common.legacy.no_lines|이 쪽에는 줄 글자가 없습니다.|전역
common.legacy.no_models|등록된 모델이 없습니다.|전역
common.legacy.time_over|목표 초과|전역
common.legacy.loading|자료를 읽고 있습니다.|전역
common.conditions.dev10|개발 10건|P01
common.conditions.eval|평가 10건|전역
common.conditions.probe|일부 시험|전역
common.conditions.cls|분류 검사|전역
common.conditions.optonly|선택 항목만|전역
common.conditions.wsonly|빈칸 줄이기만|전역
common.conditions.diag|문제 확인|전역
common.conditions.none|AI에게 시킬 일 없음|전역
common.conditions.ex|예시 포함|전역
common.conditions.w1|동시 1개|전역
common.conditions.p3|AI에게 시킬 일 p3|전역
common.document_definition|화학제품 안전 설명서(MSDS)입니다. 성분과 응급조치 등 16개 주제로 나뉩니다.|전역
common.local_only|내 컴퓨터에서 쓰는|전역
common.tool_kind|문서 검토 도구|전역
common.item|항목|S01,S04
common.score|점수|S01,S04
common.target|목표|S01
common.priority|중요도|S01
common.required|필수|S01
common.important|중요|S01
common.ordinary|일반|S01
common.document|문서|P01,S01
common.tier|등급|S01
common.count|수|S01,S02
common.weight|무게|S01
common.record|기록|S01,S03
common.done|완료|S01,S05
common.display|표시|S01
common.close|닫기|S01
common.selected|선택됨|S02,S08
common.wrong|틀림|S02,S08
common.subject|대상|S02,S05
common.run_label|실행|S02,S04
common.section|부분|S02,S03
common.blank|빈칸|S02
common.made|만듦|S02
common.answer_key|정답지|S03,S08
common.input|입력|S03,S08
common.content|내용|S03,S08
common.format|형식|S03,S08
common.image|이미지|S03,S08
common.warning|경고|S03,S08
common.none|없음|P01,S03
common.result|결과|S03
common.category|구분|S03
common.set|묶음|S03
common.basis|기준|S04
common.change|변화|S04
common.same|같음|S04
common.table|표|S04
common.answer|정답|P01,S04
common.shared|공통|S04
common.started|시작|S05,S08
common.model|모델|S05
common.no|아님|S05
common.used|사용|S05
common.job|작업|S05
common.progress|진행|S05
common.stop|중단|S05
common.method|방법|S06,S08
common.server|서버|S06
common.manage|관리|S06
common.action|할 수 있는 일|S08
common.scope|범위|S09
common.selection|선택|P01
common.current|현재|P01
common.candidate|후보|P01
common.available|가능|P01
common.present|있음|P01
common.ai|AI|S01,S03
common.run.prompt_round|{round}번째 판|실행 이름(run_label)
common.run.input_round|{round}판|실행 이름(run_label)
common.run.input_temp|임시판|실행 이름(run_label)
common.run.input_new|새 문서 폴더|실행 이름(run_label)
common.run.dev_docs|개발 {count}건|실행 이름(run_label)

### errors — E01–E09 복구

키|글|쓰는 곳
---|---|---
errors.empty.fact|아직 저장된 실행이 없습니다.|E01
errors.loading.fact|고른 정답지로 실행 결과를 읽고 있습니다.|E02
errors.pages_missing.title|고른 묶음에서 이 문서의 쪽 글자를 찾지 못했습니다.|E03
errors.eval_locked.fact|평가용 {count}건은 개발 과정에서 열 수 없습니다.|E04
errors.key_missing.fact|이 문서에 대응하는 정답지가 없습니다.|E05
errors.model_none.fact|회사 서버에 켜진 모델이 없습니다.|E06
errors.tunnel_closed.fact|회사 서버로 가는 연결 통로가 닫혀 있습니다.|E07
errors.model_loading.fact|회사 서버에서 {model}를 켜고 있습니다.|E08
errors.job_pages.fact|시험할 문서의 쪽 글자를 읽지 못했습니다.|E09
errors.pages_missing.fact|{where}에서 원문 쪽 자료를 찾지 못했습니다.|E01–E09
errors.pages_missing.todo|할 일: 이 문서의 원문이 있는 묶음을 고르세요.|E01–E09
errors.env.line|설정 파일(.env)의 {line}번째 줄을 읽지 못했습니다.|E01–E09
errors.env.line_todo|할 일: 해당 줄의 따옴표와 = 표시를 고친 뒤 설정 다시 읽기를 누르세요.|E01–E09
errors.env.missing|설정 파일(.env)에 {variable} 설정이 없습니다.|E01–E09
errors.env.runpod_url|할 일: RUNPOD_VLLM_BASE_URL에 빌린 서버의 중계 주소를 넣으세요.|E01–E09
errors.env.company_url|할 일: RNGD_BASE_URL에 보안 연결을 거친 내 컴퓨터 쪽 주소를 넣으세요.|E01–E09
errors.env.unknown_url|할 일: 모델 설정에서 {variable}에 필요한 주소 형식을 확인하세요.|E01–E09
errors.connection.ssh_prefix.fact|RNGD_SSH 설정에 ssh 명령어까지 들어 있습니다.|E01–E09
errors.connection.ssh_prefix.todo|할 일: 앞의 ssh를 빼고 접속 옵션만 적으세요.|E01–E09
errors.connection.ssh_missing.fact|회사 서버 접속 설정(RNGD_SSH)이 없습니다.|E01–E09
errors.connection.ssh_missing.todo|할 일: .env.example의 RNGD_SSH 항목을 설정 파일에 채우세요.|E01–E09
errors.connection.certificate.fact|빌린 서버 주소의 인증서를 확인하지 못했습니다.|E01–E09
errors.connection.certificate.todo|할 일: Python 3.11을 쓴다면 인증서 설치 파일을 실행한 뒤 앱을 다시 켜세요.|E01–E09
errors.connection.model_key.fact|모델 서버가 접속 키를 거절했습니다.|E01–E09
errors.connection.model_key.todo|할 일: 설정 파일의 모델 접속 키와 서버를 켤 때 쓴 키를 맞추세요.|E01–E09
errors.connection.account_key.fact|빌린 서버 관리 키가 거절됐습니다.|E01–E09
errors.connection.account_key.todo|할 일: RunPod에서 관리 키를 다시 만든 뒤 설정 파일에 넣으세요.|E01–E09
errors.connection.no_response.fact|모델 서버가 응답하지 않습니다.|E01–E09
errors.connection.no_response.todo|할 일: AI 켜기와 비용에서 연결 통로와 모델 준비 상태를 확인하세요.|E01–E09
errors.connection.other.fact|서버 상태를 읽지 못했습니다.|E01–E09
errors.connection.other.todo|할 일: 오류 기록을 열어 설정과 연결 상태를 확인하세요.|E01–E09
errors.connection.model_key_changed|서버를 만든 뒤 접속 키를 바꿨다면 서버를 다시 만들어야 합니다. 비용을 확인한 뒤 진행하세요.|E01–E09
errors.job.pages.message|원문 쪽 글자가 있는 폴더나 파일을 찾지 못했습니다.|E01–E09
errors.job.pages.fix|할 일: 해당 문서의 원문이 있는 묶음을 다시 고르세요.|E01–E09
errors.job.outside.message|현재 실행기는 이 문서를 시험할 수 없습니다.|E01–E09
errors.job.outside.fix|할 일: 시험 가능한 개발 문서를 고르세요.|E01–E09
errors.job.connect.message|모델 서버에 연결하지 못했습니다.|E01–E09
errors.job.connect.fix|할 일: AI 켜기와 비용에서 모델 상태를 확인하세요.|E01–E09
errors.job.key.message|모델 서버가 키를 거절했습니다.|E01–E09
errors.job.key.fix|할 일: 모델 접속 키가 서버를 켤 때 쓴 키와 같은지 설정 파일에서 확인하세요.|E01–E09
errors.job.eval.message|평가용 문서는 시험할 수 없습니다.|E01–E09
errors.job.eval.fix|할 일: 개발용 문서를 고르세요.|E01–E09
errors.job.other.message|작업이 오류로 끝났습니다.|E01–E09
errors.job.other.fix|할 일: 마지막 오류 기록을 확인하세요.|E01–E09
errors.job.no_line.fix|할 일: 작업 기록을 열어 마지막 오류를 확인하세요.|E01–E09
errors.request.unknown_set.message|없는 문서 묶음입니다: {id}.|E01–E09
errors.request.unknown_set.fix|할 일: 문서 묶음 목록에서 다시 고르세요.|E01–E09
errors.request.unusable_set.message|고를 수 없는 묶음입니다: {reason}|E01–E09
errors.request.unusable_set.fix|할 일: 문서 묶음 목록에서 다른 묶음을 고르세요.|E01–E09
errors.request.unknown_key.message|없는 정답지입니다: {id}.|E01–E09
errors.request.unknown_key.fix|할 일: 정답지 목록에서 다시 고르세요.|E01–E09
errors.request.unusable_key.message|고를 수 없는 정답지입니다: {reason}|E01–E09
errors.request.unusable_key.fix|할 일: 정답지 목록에서 다른 정답지를 고르세요.|E01–E09
errors.request.missing_pages.message|{where}의 쪽 자료가 없습니다.|E01–E09
errors.request.missing_pages.fix|할 일: 이 문서가 있는 문서 묶음을 다시 고르세요.|E01–E09
errors.request.missing_run.message|없는 실행입니다: {name}.|E01–E09
errors.request.missing_run.fix|할 일: 실행 목록에서 다시 고르세요.|E01–E09
errors.request.doc_not_in_run.message|이 실행에서 열 수 없는 문서입니다: {doc}.|E01–E09
errors.request.doc_not_in_run.fix|할 일: 이 실행의 문서 목록에서 다시 고르세요.|E01–E09
errors.request.doc_not_in_set.message|이 묶음에서 열 수 없는 문서입니다: {doc}.|E01–E09
errors.request.doc_not_in_set.fix|할 일: 이 묶음의 문서 목록에서 다시 고르세요.|E01–E09
errors.request.bad_query.fix|할 일: 입력을 고친 뒤 다시 보내세요.|E01–E09
errors.confirm_expired.fact|이 확인 화면에서 실행할 수 있는 시간이 지났습니다.|P02
errors.confirm_expired.todo|할 일: 상태를 다시 읽은 뒤 확인 화면을 다시 여세요.|P02
errors.state|현재 상태|E01,E02
errors.empty.todo|시험 결과가 생기면 점수와 문제를 볼 수 있습니다. 할 일: 시험할 문서를 고르세요.|E01
errors.loading.available|새 기준 아래 이전 점수는 숨겼습니다. 메뉴와 모델 관리는 계속 사용할 수 있습니다.|E02
errors.loading.open_result|읽은 결과 보기|E02
errors.pages_missing.keep_target|{doc}의 {section}번 부분을 유지했습니다. 할 일: 원문이 있는 묶음을 고르세요.|E03
errors.pages_missing.details|오류 원문과 읽은 자료|E03
errors.pages_missing.set|조회한 묶음: 빈 자료 폴더 ·|E03
errors.pages_missing.no_lines|줄 번호 없는 묶음은 자료 없음과 사유를 구분합니다.|E03
errors.pages_missing.status_not_lock|직접 요청의 {status_code}만으로 평가 잠금이라고 판단하지 않습니다.|E03
errors.eval_locked.todo|최종 성능을 공정하게 재려고 잠가 두었습니다. 할 일: 개발용 문서를 고르세요.|E04
errors.eval_locked.no_read|원문과 그림을 요청하지 않습니다.|E04
errors.eval_locked.no_run|시험과 점수 계산도 제한합니다.|E04
errors.key_missing.todo|정답이 없어 점수를 계산하지 않았습니다. 할 일: 정답지를 고르거나 점수 없이 원문을 읽으세요.|E05
errors.key_missing.select|정답지 고르기|E05
errors.key_missing.read_source|점수 없이 원문 읽기|E05
errors.key_missing.can_extract|추출 실행 자체는 정답 유무와 별개입니다.|E05
errors.model_none.todo|회사 서버까지 연결은 됐습니다. 할 일: 시험할 AI 모델을 고르세요.|E06
errors.model_none.select|모델 고르기|E06
errors.tunnel_closed.todo|회사 서버의 {model}는 켜져 있습니다. 할 일: 이 컴퓨터의 연결 통로를 여세요.|E07
errors.tunnel_closed.open|연결 통로 열기|E07
errors.model_loading.elapsed|{minutes}분이 지났습니다. 준비에는 보통 15~25분이 걸립니다.|E08
errors.model_loading.late|{minutes}분이 지나면 서버 기록을 확인하세요. 시간이 지났다고 실패한 것은 아닙니다.|E08
errors.model_loading.no_resend|모델 준비 중 · 중복 요청 불가|E08
errors.model_loading.open_ready|준비가 끝난 상태 보기|E08
errors.model_loading.ready_condition|기대한 모델의 응답이 확인되면 다음 행동이 바뀝니다.|E08
errors.job_pages.todo|할 일: 원문 폴더를 확인한 뒤 같은 문서로 다시 시험하세요.|E09
errors.job_pages.retry|입력 확인 후 다시 시험하기|E09
errors.job_pages.record|실패한 작업의 기록|E09
errors.job_pages.target|작업: {doc}의 {section}번 부분 시험.|E09
errors.job_pages.log_path|로그 위치:|E09
errors.gold_loading.title|사람이 확인한 정답으로 점수를 읽고 있습니다.|E02
errors.gold_loading.scope|개발용 {total}건 중 {count}건을 점수를 매길 수 있습니다.|E02
errors.gold_loading.hide_stale|이전 정답의 점수는 표시하지 않습니다.|E02
errors.gold_loading.open_failed|새 기준 조회 실패 상태 보기|E02
errors.tunnel_and_model.title|연결 통로가 닫혀 있습니다.|E07
errors.tunnel_and_model.no_model|회사 서버에 켜진 모델도 없습니다.|E07

### score — S01 결과 · S08 결과 읽기

키|글|쓰는 곳
---|---|---
score.criteria.hint|23가지 기준의 점수와 목표를 확인하세요.|S01
score.history.hint|최근 결과와 지난 최고점을 구분해서 보세요.|S01
score.documents.hint|문서별 점수와 AI 요청 기록을 확인하세요.|S01
score.rows.hint|표에 담긴 행 수를 정답과 비교하세요.|S01
score.summary.headline_below|목표 점수 {line}점보다 {gap}점 낮습니다.|score_status
score.summary.headline_met|목표 점수 {line}점에 도달했습니다.|score_status
score.summary.value|전체 점수는 {score}점입니다.|score_status
score.summary.must_some|23개 점수 기준 중 꼭 맞아야 하는 {total}개가 필수 기준입니다. {met}개가 각자의 목표를 채웠습니다.|S01,S08
score.summary.must_all|필수 기준 {total}개가 모두 각자의 목표에 닿았습니다.|score_status
score.summary.unscored|이 결과는 점수를 계산하지 않았습니다.|score_status
score.summary.unscored_todo|할 일: 비교할 AI 결과와 정답이 있는지 확인하세요.|score_status
score.summary.drop|{item}은 {score}점입니다. 목표는 {goal}점입니다. 가장 많은 문제 유형은 {cause} {count}건입니다.|score_status
score.summary.next_trial|할 일: {section}번 부분을 다시 시험하세요.|score_status
score.summary.next_source|할 일: {item}의 문제 값을 원문과 맞춰 보세요.|score_status
score.summary.next_compare|두 목표에 모두 도달했습니다. 할 일: 두 결과를 비교해 반복할 때의 차이를 보세요.|score_status
score.summary.next_items|할 일: 모든 기준의 점수와 목표를 확인하세요.|score_status
score.summary.counts_meaning|{counts}건은 이 기준에서 찾은 문제 값 수입니다. 값 하나가 몇 점인지는 따로 계산하지 않습니다.|S01,S08
score.summary.loss_meaning|100점에서 {total_loss}점이 깎여 {score}점입니다. 그중 {item_loss}점이 이 기준에서 깎였습니다. 23개 기준 중 가장 많습니다.|S01,S08
score.summary.history|저장된 결과 {count}개 중 최고점은 {score}점입니다. 해당 결과는 {run}입니다.|S01
score.summary.docs|문서 {count}건입니다. {score_detail} {time_detail}|S01
score.summary.lowest|가장 낮은 점수는 {doc}의 {score}점입니다.|S01
score.summary.slowest|가장 오래 걸린 문서는 {doc}입니다. {seconds}초 걸렸습니다.|S01
score.summary.no_scores|문서별 점수 기록이 없습니다.|S01
score.summary.no_times|문서별 시간 기록이 없습니다.|S01
score.summary.grid|AI 요청 {count}개의 상태입니다.|S01
score.summary.grid_count|{state} {count}개|S01
score.summary.rows|표 {count}개 중 정답보다 행이 적은 표는 {short}개입니다.|S01
score.summary.rows_shortest|행이 가장 부족한 표는 {table}입니다. AI 결과는 {pred}행입니다. 정답은 {answer}행입니다.|S01
score.tables.components|성분 (3번 부분)|S01
score.tables.exposure_limits|노출기준 (8번 부분)|S01
score.tables.physchem|물리·화학 성질 (9번 부분)|S01
score.tables.toxicity|독성 (11번 부분)|S01
score.tables.cmr|발암성 등 CMR (11번 부분)|S01
score.tables.ecotox|생태 독성 (12번 부분)|S01
score.tables.regulations|규제 (15번 부분)|S01
score.tables.intl_class|국제 분류 (15번 부분)|S01
score.tables.extras|표 밖에 남은 값|S01
score.summary.headline_model|{model}의 최근 점수는 목표보다 낮습니다.|S01,S08
score.summary.scope|{model} · 개발용 문서 {count}건의 점수|S01,S08
score.summary.denominator|/ 100점|S01,S08
score.summary.gap_short|목표 {line}점보다 {gap}점 낮음|S01,S08
score.summary.target|목표 점수 {line}점|S01,S08
score.summary.below_best|지난 최고점 {best}점보다 {gap}점 낮습니다.|S01,S08
score.summary.finished|{time}에 끝난 가장 최근 결과입니다.|S01,S08
score.summary.top_problem_exposure|가장 큰 문제는 공기 속 물질의 허용량(허용 농도)입니다.|S01,S08
score.summary.exposure_section|8번 부분 · 작업장 공기 기준(노출기준)|S01,S08
score.problem.counts.missing|정답에 있는 값을 못 뽑음 {count}건|S01,S08
score.problem.counts.made|정답에 없는 값을 만듦 {count}건|S01,S08
score.problem.counts.wrong|정답과 다른 값을 뽑음 {count}건|S01,S08
score.problem.open_wrong|틀린 값 {count}건의 원문 보기|S01,S08
score.problem.evidence_hint|AI가 적은 원문 줄이 있어 바로 확인할 수 있는 틀린 값부터 봅니다. 못 뽑은 {count}건의 추정 줄은 목록에서 봅니다.|S01
score.criteria.expand|점수가 깎인 곳 모두 보기 · 23가지 기준|S01
score.criteria.title|점수를 매기는 기준 23개|S01
score.criteria.below_count|목표 아래인 항목은 {count}개입니다.|S01
score.criteria.filter_below|목표 아래 {count}개 먼저 보기|S01
score.criteria.show_all|모든 항목 23개 보기 · 숨긴 항목 없음|S01
score.criteria.loss|깎인 점수|S01
score.criteria.method|측정 방법|S01
score.criteria.met|목표 이상|S01
score.criteria.method_msds|자료를 몇 건으로 나눴는지 비교|S01
score.criteria.below|목표 아래|S01
score.criteria.method_management|번호와 날짜와 개정 횟수 비교|S01
score.criteria.method_product|이름과 긴급 전화 비교|S01
score.criteria.method_signal|위험·경고 같은 말 비교|S01
score.criteria.method_pictogram|선택한 위험 그림 종류 비교|S01
score.criteria.method_hazard|위험 문구 번호의 목록 비교|S01
score.criteria.method_precaution|예방 문구 번호의 목록 비교|S01
score.criteria.method_classification|위험 종류와 단계의 짝 비교|S01
score.criteria.method_components|성분 식별 번호로 목록 비교|S01
score.criteria.method_component_fields|성분별 이름과 국내 번호 비교|S01
score.criteria.method_content|부등호와 수치와 단위 비교|S01
score.criteria.method_exposure|성분과 기준 종류와 수치 비교|S01
score.criteria.method_physchem_required|끓는점 등 주요 성질 비교|S01
score.criteria.method_physchem_other|색과 냄새 등 나머지 성질 비교|S01
score.criteria.method_acute|먹음·피부·흡입 독성 비교|S01
score.criteria.method_toxicity_other|자극과 과민 반응 비교|S01
score.criteria.method_cmr|세 종류 독성의 분류 비교|S01
score.criteria.method_ecology|생물 독성과 분해성 비교|S01
score.criteria.method_domestic|규제 항목과 해당 여부 비교|S01
score.criteria.method_regulation_concentration|규제가 적용되는 농도 비교|S01
score.criteria.method_foreign|해외 규제 항목과 해당 여부 비교|S01
score.criteria.method_transport|운송 번호와 위험 등급 비교|S01
score.criteria.method_narrative|응급조치 등 문장의 글자 유사도 비교|S01
score.problem.scope|문제 종류와 기록 범위|S01
score.problem.missing_meaning|못 뽑음: 정답에는 있고 AI 결과에는 없는 값|S01
score.problem.made_meaning|만듦: 정답에는 없고 AI 결과에는 있는 값|S01
score.problem.wrong_meaning|틀림: 같은 칸의 값이 정답과 다름|S01
score.problem.answer_warning|정답 자체의 오류 가능성은 원문과 함께 검토합니다.|S01
score.problem.section_count|{section}번 부분 문제는 총 {count}건입니다.|S01
score.problem.linked_count|연결된 근거의 대표 {count}건을 먼저 보여 줍니다.|S01
score.problem.other_counts|나머지 {count}건은 못 뽑음 {missing}건과 없는 값을 만듦 {made}건입니다.|S01
score.problem.unrecorded|문제 상세를 수집하지 않은 항목은 ‘기록 없음’입니다.|S01
score.problem.checked_empty|확인해서 문제가 없던 항목은 ‘0건’입니다.|S01
score.problem.answer_gap|현재 정답 초안에서 확인할 빈 곳: 예시 {component}의 출처 칸 {count}개.|S01
score.problem.found_at|발견 시각: {time}.|S01
score.problem.nonempty_score|해당 항목의 빈 행 제외 보조 점수는 {score}%입니다.|S01
score.problem.open_remaining|나머지 문제 {count}건 모두 보기|S01
score.problem.kind|문제 종류|S01,S02
score.problem.record|기록된 내용|S01
score.problem.missing|못 뽑음|S01,S02
score.problem.missing_value|{component}의 기준 값이 결과에 없음|S01
score.problem.made|없는 값을 만듦|S01
score.problem.made_value|원문에 없는 {concentration} mg/m³를 채움|S01
score.problem.open_linked|연결된 문제 값 보기|S01
score.summary.back|최근 결과로 돌아가기|S01,S04
score.calculation.title|점수 계산 방법|S01
score.calculation.weighted|중요도를 반영한 전체 점수(가중 종합)입니다.|S01
score.calculation.must|꼭 맞춰야 함(필수)|S01
score.calculation.weight_total|무게 합은 61입니다.|S01
score.calculation.formula|손실 = 무게 × (1 − 기준 점수) ÷ 61 × 100|S01
score.calculation.exposure_example|허용 농도: 3 × (1 − 0.40) ÷ 61 × 100 = 약 2.95점.|S01
score.calculation.total_loss|총손실은 반올림 전 합으로 계산한 {loss}점입니다.|S01
score.calculation.rounded_sum|각 행을 따로 반올림한 합은 {loss}점입니다.|S01
score.calculation.counts_not_points|문제 값 {missing}/{made}/{wrong}건을 점수로 환산하지 않습니다.|S01
score.history.expand|실행 이력 · {count}개 결과 중 최고 {best}점|S01
score.history.caption|완료 시각 순 점수 · 목표 점수 {line}점|S01
score.history.a11y|{date} {first_score}점, {middle_day}일 {middle_score}점과 최고 {best}점, {latest_day}일 최근 {latest_score}점. 모두 목표 점수 {line}점 아래입니다.|S01
score.history.model_date|{month}/{day} · {model}|S01
score.history.best_point|{score} · 최고|S01
score.history.latest_point|{score} · 최근|S01
score.history.title|지난 결과|S01
score.history.latest_meaning|현재 화면은 최고 점수가 아니라 가장 늦게 끝난 결과를 보여 줍니다.|S01
score.history.finished|끝난 시각|S01
score.history.score|점수 / {maximum}|S01,S04
score.history.current|현재 · 가장 최근|S01
score.history.best|지난 최고점|S01,S10
score.history.previous|이전 결과|S01
score.history.comparable|네 결과는 같은 문서 {count}건과 같은 정답으로 비교했습니다.|S01
score.history.target|목표 점수은 모두 {line}점입니다.|S01
score.history.exclude_answer|정답을 만들기 위한 실행은 최고점과 추세에서 제외합니다.|S01
score.history.answer_records|정답 생성 기록도 아래 목록에서 따로 열 수 있습니다.|S01
score.history.select_record|조회할 기록|S01
score.history.run_option|문서 처리 · {time} · {score}점|S01
score.history.answer_option|정답 생성 · {time} · 비교 대상 아님|S01
score.history.select_a|먼저 비교할 결과 A|S01
score.history.option|{time} · {score}점|S01
score.history.select_b|나중에 비교할 결과 B|S01
score.history.selection_order|표의 선택 순서가 A와 B의 순서입니다.|S01
score.history.compare|선택한 두 결과 비교하기|S01
score.history.clear|선택 해제하기|S01
score.documents.expand|문서와 호출 · 개발용 {count}건 완료|S01
score.documents.title|문서별 점수와 AI 요청 기록|S01
score.documents.completed|개발용 {count}건을 완료했습니다.|S01
score.documents.time_target|처리 시간의 목표는 문서 한 건당 {seconds}초입니다.|S01
score.documents.must_below|목표 아래 필수 항목|S01
score.documents.duration|처리 시간|S01
score.documents.time_state|시간 상태|S01
score.documents.recorded|기록 있음|S01
score.documents.within_time|{minutes}분 목표 이내|S01
score.documents.time_unknown|시간 비교 불가|S01
score.calls.title|문서 안 첫 번째 안전자료 · 16개 부분의 AI 요청|S01
score.calls.section|{section}번 부분|S01,S03
score.calls.multiple_msds|한 파일에 안전자료가 여럿이면 자료 순번으로 나눠 표시합니다.|S01
score.calls.example_scope|이 예시는 첫 번째 안전자료의 기록입니다.|S01
score.calls.legend|요청 상태의 뜻|S01
score.calls.parsed|AI의 답을 값으로 읽음|S01
score.calls.reextract|다시 뽑음|S01,S03
score.calls.reextract_meaning|첫 답의 문제를 알려 다시 요청|S01
score.calls.output_limit|출력 한도|S01
score.calls.output_limit_meaning|답변 길이 제한에 도달|S01
score.calls.failed|요청을 완료하지 못함|S01
score.calls.unknown|성공 여부를 확인할 기록이 없음|S01
score.calls.expand_section|{section}번 부분 요청 자세히|S01
score.calls.attempts|시도 {count}회 · {seconds}초 · 표 형식으로 요청했습니다.|S01
score.calls.not_limited|출력 길이 제한에 걸리지 않았습니다.|S01
score.calls.failure_count|실패한 요청은 {count}개입니다.|S01
score.calls.slow_threshold|시간이 {seconds}초를 넘으면 느린 처리로 표시합니다.|S01
score.calls.no_time_inference|시간 기록이 없으면 초과라고 추정하지 않습니다.|S01
score.rows.expand|표 행 수 · {count}종을 정답과 비교|S01
score.rows.title|표에 담긴 행 수|S01
score.rows.meaning|같은 종류의 값이 몇 줄씩 들어 있는지 비교합니다.|S01
score.rows.kind|표 종류|S01
score.rows.prediction|AI 결과|S01
score.rows.answer|정답|S01,P01
score.rows.ratio|정답 대비 비율|S01
score.rows.physchem|물리·화학 성질|S01,S02
score.rows.cmr|암·유전·생식 독성|S01
score.rows.intl_class|국제 위험 분류|S01
score.rows.not_applicable|해당 없음|S01,P01
score.conditions.expand|처리 조건과 보조 점수 보기|S01
score.conditions.value|저장된 값|S01
score.conditions.run_name|실행 이름|S01,S09
score.conditions.raw_name|원래 이름|S01
score.conditions.prompt|AI에게 시킨 일(지시문)|S01
score.conditions.prompt_version|{version}번째 버전 ·|S01
score.conditions.pages|원문 글자 묶음|S01
score.conditions.previous|이전 개발 자료 ·|S01,S03
score.conditions.score_scope|점수를 매긴 범위|S01,P01
score.conditions.score_counts|{total}건 중 {scored}건. 정답 없음 {missing}건. 제외 {excluded}건.|S01
score.conditions.kind|실행 분류|S01
score.conditions.comparable|문서 여러 건 처리. 비교 가능.|S01
score.conditions.nonempty_score|값 없는 행을 뺀 보조 점수는 {score}점입니다.|S01
score.conditions.nonempty_gain|원래 점수보다 {gap}점 높습니다.|S01
score.conditions.keep_components|성분 목록은 다른 표에서 참조하므로 제외하지 않습니다.|S01
score.conditions.exclude_answer|정답을 만드는 실행은 최고점과 추세에서 제외합니다.|S01
score.first.hint|처음이라면 결과 읽기부터 시작하세요.|S01
score.first.open_guide|처음 사용 안내 열기|S01
score.missing_only.fact|이 변형에는 못 뽑은 값만 있습니다.|S01
score.missing_only.open_first|못 뽑은 첫 값의 원문 보기|S01
score.missing_only.estimated|못 뽑은 값은 내용이 맞는 줄을 추정으로 찾아 보여 줍니다.|S01
score.missing_only.section_count|{section}번 부분 문제는 못 뽑은 값 {count}건입니다.|S01
score.missing_only.first|첫 누락 값의 추정 줄을 먼저 보여 줍니다.|S01
score.missing_only.all_available|못 뽑은 {count}건은 모두 목록에서 열 수 있습니다.|S01
score.missing_only.open_all|못 뽑은 문제 {count}건 모두 보기|S01
score.empty.title|이 문서 묶음으로 만든 결과가 없습니다.|S01
score.empty.state|결과 없음|S01
score.empty.fact|현재 선택한 개발 자료에는 저장된 실행이 없습니다.|S01
score.empty.prepare|시험 준비하기|S01,E01
score.empty.filters|결과 필터 확인하기|S01
score.empty.set|입력 묶음은 이전 개발 자료 {version}판입니다.|S01
score.empty.no_mixing|다른 묶음의 점수는 여기에 섞지 않습니다.|S01
score.empty.change_set|문서 묶음 바꾸기|S01,E03
score.partial.title|실행 기록 {total}개 중 {failed}개를 읽지 못했습니다.|S01
score.partial.state|일부 읽기 실패|S01
score.partial.todo|읽은 결과만 표시했습니다. 할 일: 기록을 다시 읽으세요.|S01
score.partial.reload|다시 읽기|S01
score.key_failed.title|새 정답지로 점수를 읽지 못했습니다.|S01
score.key_failed.state|점수 확인 실패|S01
score.key_failed.todo|이전 점수는 숨겼습니다. 할 일: 선택한 사람 확인 정답을 다시 읽으세요.|S01
score.key_failed.reload|정답지 다시 확인하기|S01
score.no_problem.title|총점에서 깎인 점수가 없습니다.|S01
score.no_problem.state|열어 볼 문제 없음|S01
score.no_problem.journey|문제의 근거를 확인하는 갈래 1은 여기서 끝낼 수 없습니다.|S01
score.no_problem.open_items|항목별 점수 보기|S01
score.no_problem.no_fallback|가장 큰 문제는 없음으로 표시합니다. 다른 값을 대신 열지 않습니다.|S01
score.waiting.company|AI를 켜는 동안 저장된 결과를 읽을 수 있습니다.|S01
score.waiting.back_company|준비 중인 모델 상태로 돌아가기|S01
score.waiting.target|시험 대상: {doc} · {section}번 부분.|S01
score.waiting.rented|빌린 서버가 준비되는 동안 저장된 결과를 읽습니다.|S01
score.waiting.back_rented|서버 상태와 비용으로 돌아가기|S01
score.waiting.cost|시간당 약 ${cost_per_hour}의 요금이 나갑니다(예시).|S01,S09
score.rows.components|성분|S01,S02
score.rows.exposure|노출기준|S01,S04
score.rows.toxicity|독성|S01,S02
score.rows.ecology|생태|S01
score.rows.regulations|규제|S01,S02

#### S01, S04, S07 — 채점 기준 23개

두 키는 각각 독립 문자열입니다. S04에서는 쉬운 이름과 원래 이름을 공백 하나로 이어 씁니다. 노출기준의 S04 설명은 `compare.criteria.exposure`를 씁니다.

키|글|원래 이름 키|원래 이름
---|---|---|---
score.criteria.msds|문서 안 안전자료 수|score.criteria.msds_original|(MSDS 건수)
score.criteria.management|작성일과 개정 정보|score.criteria.management_original|(관리정보)
score.criteria.product|제품과 회사 정보|score.criteria.product_original|(제품명)
score.criteria.signal|위험을 알리는 말|score.criteria.signal_original|(신호어)
score.criteria.pictogram|위험 표시 그림|score.criteria.pictogram_original|(그림문자)
score.criteria.hazard|위험 문구 번호|score.criteria.hazard_original|(H 코드)
score.criteria.precaution|예방 문구 번호|score.criteria.precaution_original|(P 코드)
score.criteria.classification|위험의 종류와 정도|score.criteria.classification_original|(유해성 분류)
score.criteria.components|들어 있는 성분 목록|score.criteria.components_original|(구성성분(CAS))
score.criteria.component_fields|성분 이름과 번호|score.criteria.component_fields_original|(구성성분 필드)
score.criteria.content|성분이 들어 있는 양|score.criteria.content_original|(함유량)
score.criteria.exposure|작업장 공기 중 허용 농도|score.criteria.exposure_original|(8번 부분 · 노출기준)
score.criteria.physchem_required|주요 물리·화학 성질|score.criteria.physchem_required_original|(9번 부분 필수 물성)
score.criteria.physchem_other|그 밖의 물리·화학 성질|score.criteria.physchem_other_original|(9번 부분 기타 물성)
score.criteria.acute|짧은 노출의 독성|score.criteria.acute_original|(11번 부분 급성독성)
score.criteria.toxicity_other|그 밖의 독성|score.criteria.toxicity_other_original|(11번 부분 기타 독성)
score.criteria.cmr|암·유전·생식 관련 독성|score.criteria.cmr_original|(11번 부분 CMR)
score.criteria.ecology|환경에 미치는 영향|score.criteria.ecology_original|(12번 부분 생태)
score.criteria.domestic|국내 규제 해당 여부|score.criteria.domestic_original|(15번 부분 국내 규제)
score.criteria.regulation_concentration|국내 규제의 기준 농도|score.criteria.regulation_concentration_original|(15번 부분 국내 규제 기준농도)
score.criteria.foreign|해외 규제 해당 여부|score.criteria.foreign_original|(15번 부분 해외)
score.criteria.transport|운송에 필요한 정보|score.criteria.transport_original|(14번 부분 운송)
score.criteria.narrative|문장으로 쓰인 설명|score.criteria.narrative_original|(서술형)

### source — S02 원문

키|글|쓰는 곳
---|---|---
source.value.field|{label}: {value}|value_tip_lines
source.value.true|예|value_tip_lines
source.value.false|아니요|value_tip_lines
source.legend.same|정답과 같음|S02,S08
source.legend.different|정답과 다르거나 정답에 없음|S02
source.legend.missing|정답에만 있음 · AI가 못 뽑음|S02
source.legend.selected|선택한 값과 원문 줄|S02
source.doc.howto|목록에서 값을 고르면 해당 원문 줄이 선택됩니다. 줄을 고르면 그 줄을 근거로 쓴 값이 선택됩니다.|S02
source.doc.guess|정답의 근거 글과 글자가 같은 줄을 찾았습니다. AI가 남긴 근거가 아닌 추정 위치입니다.|S02
source.doc.no_guess|정답의 근거 글을 이 묶음에서 찾지 못했습니다. 할 일: 해당 부분의 원문을 직접 읽으세요.|S02
source.doc.counts|AI가 채운 값은 {total}개입니다. 정답과 다른 값은 {different}개입니다. 정답에만 있는 값은 {missing}개입니다.|S02
source.rows.mix|제품 전체|S02
source.rows.row_no|{no}행|S02
source.rows.gold_row_no|정답 {no}행|S02
source.row_parts.standard.국내|국내기준|S02
source.row_parts.standard.생물학적|생물학적 노출기준|S02
source.row_parts.prop_code.APPEARANCE_STATE|외관(성상)|S02
source.row_parts.prop_code.APPEARANCE_COLOR|외관(색상)|S02
source.row_parts.prop_code.ODOR|냄새|S02
source.row_parts.prop_code.ODOR_THRESHOLD|냄새 역치|S02
source.row_parts.prop_code.PH|pH|S02
source.row_parts.prop_code.MELT_FREEZE|녹는점/어는점|S02
source.row_parts.prop_code.BOILING|끓는점|S02
source.row_parts.prop_code.FLASH_POINT|인화점|S02
source.row_parts.prop_code.EVAP_RATE|증발 속도|S02
source.row_parts.prop_code.FLAMMABILITY|인화성(고체, 기체)|S02
source.row_parts.prop_code.UEL|폭발 범위 상한|S02
source.row_parts.prop_code.LEL|폭발 범위 하한|S02
source.row_parts.prop_code.VAPOR_PRESSURE|증기압|S02
source.row_parts.prop_code.SOLUBILITY|용해도|S02
source.row_parts.prop_code.VAPOR_DENSITY|증기 밀도|S02
source.row_parts.prop_code.RELATIVE_DENSITY|비중(상대 밀도)|S02
source.row_parts.prop_code.LOG_KOW|n-옥탄올/물 분배계수|S02
source.row_parts.prop_code.AUTOIGNITION|자연발화 온도|S02
source.row_parts.prop_code.DECOMPOSITION|분해 온도|S02
source.row_parts.prop_code.VISCOSITY|점도|S02
source.row_parts.prop_code.VISCOSITY_KIN|동점도|S02
source.row_parts.prop_code.MOL_WEIGHT|분자량|S02
source.row_parts.endpoint.TX_ORAL|급성 독성(경구)|S02
source.row_parts.endpoint.TX_DERMAL|급성 독성(경피)|S02
source.row_parts.endpoint.TX_INHAL|급성 독성(흡입)|S02
source.row_parts.endpoint.TX_SKIN|피부 부식성/자극성|S02
source.row_parts.endpoint.TX_EYE|심한 눈 손상/자극성|S02
source.row_parts.endpoint.TX_RESP_SENS|호흡기 과민성|S02
source.row_parts.endpoint.TX_SKIN_SENS|피부 과민성|S02
source.row_parts.endpoint.TX_CARC|발암성|S02
source.row_parts.endpoint.TX_MUTA|생식세포 변이원성|S02
source.row_parts.endpoint.TX_REPRO|생식독성|S02
source.row_parts.endpoint.TX_STOT_SE|특정 표적장기 독성(1회)|S02
source.row_parts.endpoint.TX_STOT_RE|특정 표적장기 독성(반복)|S02
source.row_parts.endpoint.TX_ASP|흡인 유해성|S02
source.row_parts.endpoint.ECO_FISH|어류 독성|S02
source.row_parts.endpoint.ECO_CRUST|갑각류 독성|S02
source.row_parts.endpoint.ECO_ALGAE|조류 독성|S02
source.row_parts.endpoint.ECO_OTHER|기타 생물 독성|S02
source.row_parts.endpoint.ECO_PERSIST|잔류성과 분해성|S02
source.row_parts.endpoint.ECO_BIOACC|생물 농축성|S02
source.row_parts.endpoint.ECO_SOIL|토양 이동성|S02
source.row_parts.endpoint.ECO_OZONE|오존층 유해성|S02
source.row_parts.law.OSH|산업안전보건법|S02
source.row_parts.law.KREACH|화평법|S02
source.row_parts.law.CCA|화관법|S02
source.row_parts.law.DG|위험물안전관리법|S02
source.row_parts.law.WASTE|폐기물관리법|S02
source.row_parts.law.POPS|잔류성오염물질 관리법|S02
source.row_parts.law.KR_ETC|기타 국내법|S02
source.row_parts.law.INTL|외국법·국제협약|S02
source.row_parts.agency.KR_OSH|산업안전보건법|S02
source.row_parts.agency.KR_CCA|화학물질관리법|S02
source.row_parts.agency.EU_CLP|EU CLP|S02
source.row_parts.system.EU_CLP|EU CLP|S02
source.row_parts.system.JP|일본|S02
source.value_titles.meta.msds_no|제출번호|S02
source.value_titles.meta.first_issue_date|최초 작성일|S02
source.value_titles.meta.last_revision_date|최종 개정일|S02
source.value_titles.meta.revision_no|개정 횟수|S02
source.value_titles.meta.revision_label|개정 표기|S02
source.value_titles.meta.doc_code|문서 코드|S02
source.value_titles.meta.header_product_name|머리글의 제품명|S02
source.value_titles.meta.page_start|시작 쪽|S02
source.value_titles.meta.page_end|끝 쪽|S02
source.value_titles.meta.source_note|자료 메모|S02
source.value_titles.product.name|제품명|S02
source.value_titles.product.uses|용도|S02
source.value_titles.product.restrictions|사용 제한|S02
source.value_titles.product.synonyms|제품의 다른 이름|S02
source.value_titles.hazard.classified|유해성 분류 여부|S02
source.value_titles.hazard.signal_word|신호어|S02
source.value_titles.hazard.nfpa.fire|NFPA 화재 위험|S02
source.value_titles.hazard.nfpa.health|NFPA 건강 위험|S02
source.value_titles.hazard.nfpa.reactivity|NFPA 반응 위험|S02
source.value_titles.composition.type|조성 종류|S02
source.value_titles.composition.no_hazardous_component|유해 성분 없음 표시|S02
source.fields.value|값|S03,S05
source.fields.text|원문 글|S02
source.fields.refs|근거 줄|S02
source.fields.cond|조건|S01,S03
source.fields.std_code|표준 코드|S02
source.fields.match_score|맞춤 점수|S02
source.fields.seq|순서|S10
source.fields.key|이름|S02
source.fields.raw|원래 표기|S02
source.fields.unit|단위|S02
source.fields.status|상태|S01,S05
source.fields.code|코드|S02
source.fields.source_text|근거 원문|S02
source.fields.page|쪽|S02,S08
source.fields.source|출처|P01
source.fields.note|비고|S02
source.fields.type|종류|S05
source.fields.lower|최솟값|S02
source.fields.upper|최댓값|S02
source.fields.lower_op|최솟값 비교 기호|S02
source.fields.upper_op|최댓값 비교 기호|S02
source.fields.approx|근삿값 여부|S02
source.fields.dp|소수 자릿수|S02
source.fields.cas_no|물질 식별 번호(CAS)|S02
source.fields.ke_no|국내 물질 번호(KE)|S02
source.fields.comp_ref|성분 번호|S02
source.title|원문과 AI의 값을 비교하세요.|S02,S08
source.problem_count|문서 {count}건에서 찾은 문제 값|S02,S08
source.unit_first_use|값을 누르면 원문이 바뀝니다. mg/m³는 공기 1세제곱미터에 든 물질의 양(밀리그램)입니다.|S02,S08
source.filter.all|전체 {count}건|S02,S08
source.filter.missing|못 뽑음 {count}칸|S02,S08
source.filter.made|만듦 {count}칸|S02,S08
source.filter.wrong|틀림 {count}칸|S02,S08
source.value.wrong|틀림 · {concentration} mg/m³|S02,S08
source.value.missing|못 뽑음 · {concentration} mg/m³|S02,S08
source.value.made|만듦 · {concentration} mg/m³|S02,S08
source.wrong.title|AI가 원문의 {expected}를 {actual}로 잘못 옮겼습니다.|S02,S08
source.value.context|{doc} · {component} · {section}번 부분 · 허용 농도|S02,S08
source.evidence.title|원문에 적힌 줄|S02,S08
source.evidence.location|{page}쪽 {line_no}번째 줄|S02,S08
source.evidence.recorded|AI 결과에 기록된 근거 위치입니다.|S02,S08
source.value.model_label|{model}가 쓴 값|S02,S08
source.value.concentration_label|공기 속 물질의 허용량(허용 농도)|S02,S08
source.value.draft|정답: {concentration} mg/m³.|S02,S08
source.value.draft_warning|정답도 틀릴 수 있습니다. 값을 믿기 전에 원문과 맞춰 보세요.|S02,S08
source.wrong.risk|허용 농도를 높게 적으면 더 많이 노출되어도 안전하다고 오해할 수 있습니다.|S02,S08
source.wrong.count_origin|앞 화면의 ‘틀림 {count}건’에 속한 값입니다.|S02,S08
source.retest.open|이 부분 다시 시험하기|S02,S08
source.retest.target|다시 시험 화면에 {doc}의 {section}번 부분과 ‘AI에게 시킬 일’ 입력란을 채웁니다.|S02,S08
source.retest.duration|시험은 약 {seconds}초~{minutes}분입니다(예시). AI 준비 시간은 별도입니다.|S02,S08
source.retest.cost|회사 서버는 추가 임대료가 없습니다. 빌린 서버는 켜 둔 시간만큼 요금이 나갑니다.|S02,S08
source.selection.expand|문서와 쪽과 부분 바꾸기|S02,S08
source.selection.current|현재 값|S02,S06
source.selection.dev_doc|개발용 문서|S02,P01
source.selection.section|{section}번 부분 · 노출 방지와 보호구|S02,S08
source.selection.source_set|원문 묶음|S02,S08
source.selection.recorded_set|실행 당시 묶음 ·|S02,S08
source.selection.next_set|다음 시험 묶음|S02,S08
source.selection.selected_set|선택 묶음 ·|S02,S08
source.selection.raw|실행 없이 원문만 보기|S02,S08
source.selection.eval_reason|평가 문서 잠금 이유 보기|S02,S08
source.evidence.range|원문은 {page}쪽 {first_line}번째 줄부터 {last_line}번째 줄까지입니다.|S02,S08
source.selection.restore|선택한 값과 쪽과 읽던 위치는 돌아올 때 복원합니다.|S02,S08
source.selection.set_mismatch|원문과 다음 시험 묶음이 다른 경우 보기|S02,S08
source.page.expand|원문 그림과 줄 글자 보기|S02,S08
source.page.caption|{doc} · {page}쪽의 글자|S02,S08
source.page.no_image|그림이 없는 경우에도 줄 글자는 남습니다.|S02,S08
source.page.no_coordinates|좌표가 없는 줄은 글자만 확인할 수 있습니다.|S02,S08
source.page.section_unknown|부분의 시작 줄을 못 찾은 경우 보기|S02,S08
source.structure.expand|값의 구조와 비교 범위 보기|S02,S08
source.structure.path|{section}번 부분 → 노출기준 표 → 행 → 기준 값|S02,S08
source.structure.raw_path|원래 경로:|S02,S08
source.structure.line_ref|줄 표기:|S02,S08
source.structure.unit|mg/m³는 공기 1세제곱미터에 든 물질의 양(밀리그램)입니다.|S02,S08
source.structure.doc_comparison|문서 전체의 비교|S02,S08
source.structure.filled|AI가 채운 값|S02,S08
source.structure.count_scope|앞 화면의 {count}건은 문서 {documents}건의 허용 농도 기준에 속합니다.|S02,S08
source.structure.extras|표 밖에 남은 값은 {count}개입니다.|S02,S03
source.structure.unknown_section|어느 부분인지 모르는 값은 ‘문서 부분 확인 필요’에 남깁니다.|S02,S08
source.estimation.expand|정답 값의 추정 줄과 근거 없는 상태|S02,S08
source.estimation.coverage|이 문서의 정답 값 {total}개 중 {matched}개에서 후보 줄을 찾았습니다.|S02,S08
source.estimation.method|추정 방식은 글자 맞춤입니다.|S02,S08
source.estimation.count_meaning|이 수는 정답 전체의 줄 찾기 범위입니다. 못 뽑은 값의 건수와는 다릅니다.|S02,S08
source.estimation.verify|원문이 맞는지는 직접 확인해야 합니다.|S02,S08
source.estimation.open_unlinked|근거 줄 없음 보기|S02,S08
source.selection.open_gone|새 결과에서 값이 사라진 경우 보기|S02,S08
source.missing.title|AI가 원문에 있는 값을 옮기지 않았습니다.|S02
source.missing.evidence_title|원문 줄(추정)|S02
source.missing.location|{page}쪽 {line_no}번째 줄 · 추정 위치|S02
source.missing.estimated|정답 내용과 글자가 맞는 줄을 찾았습니다. AI가 남긴 근거는 아닙니다.|S02
source.missing.risk|값이 빠지면 작업장 공기 기준을 확인할 수 없습니다.|S02
source.missing.count_origin|앞 화면의 ‘못 뽑음 {count}건’에 속한 값입니다.|S02
source.made.title|AI가 원문에 없는 숫자를 넣었습니다.|S02
source.made.no_data|자료 없음|S02
source.made.draft|정답: 자료 없음.|S02
source.made.risk|없는 숫자를 넣으면 확인되지 않은 농도를 안전 기준으로 오해할 수 있습니다.|S02
source.made.count_origin|앞 화면의 ‘만듦 {count}건’에 속한 값입니다.|S02
source.unlinked.title|원문 줄을 찾지 못했습니다.|S02
source.unlinked.line_absent|AI가 적은 줄 번호가 현재 원문에 없습니다.|S02
source.unlinked.no_fallback|다른 줄을 근거로 대신 선택하지 않았습니다.|S02
source.unlinked.read_section|이 부분 원문 읽기|S02
source.unlinked.todo|할 일: {section}번 부분의 원문을 직접 읽으세요. 연결된 근거를 찾기 전에는 안내 완료로 세지 않습니다.|S02
source.raw.title|저장된 결과 없이 원문만 보고 있습니다.|S02
source.sections.product|제품과 회사|S02
source.sections.fire|화재 대처|S02
source.sections.release|누출 대처|S02
source.sections.handling|취급과 저장|S02
source.sections.exposure|노출 방지와 보호구|S02
source.sections.stability|안정성과 반응|S02
source.sections.environment|환경 영향|S02
source.sections.other|그 밖의 정보|S02
source.raw.read_page|{page}쪽 글자 읽기|S02
source.section_unknown.title|{section}번 부분의 시작 줄을 찾지 못했습니다.|S02
source.section_unknown.state|부분 구간 확인 필요|S02
source.section_unknown.available|근거 줄과 값은 볼 수 있습니다. 부분 구간 띠는 표시하지 않습니다.|S02
source.section_unknown.open_value|선택 값과 줄 보기|S02
source.value_gone.title|이 값은 새 결과에 없습니다.|S02
source.value_gone.returned|{section}번 부분으로 돌아왔습니다.|S02
source.value_gone.path_absent|{doc}의 새 결과에는 선택했던 값 경로가 없습니다.|S02
source.sections.hazards|위험성|S02
source.sections.first_aid|응급조치|S02
source.sections.disposal|폐기|S02
source.sections.transport|운송|S02

### compare — S04 비교 · S10 비교표

키|글|쓰는 곳
---|---|---
compare.headline.none|비교할 기준별 점수가 없습니다.|diff_headline
compare.headline.unscored|B({b})와 A({a})의 전체 점수를 비교할 수 없습니다.|diff_headline
compare.headline.equal|B({b})와 A({a})의 전체 점수가 같습니다.|diff_headline
compare.headline.lower|B({b})가 A({a})보다 {gap}점 낮습니다.|diff_headline
compare.headline.higher|B({b})가 A({a})보다 {gap}점 높습니다.|diff_headline
compare.headline.biggest|가장 크게 달라진 기준은 {item}입니다. 점수 차이는 {delta}점입니다.|diff_headline
compare.conditions.same|비교 조건이 모두 같습니다.|S04
compare.conditions.changed|달라진 조건: {condition}|S04
compare.conditions.variation|같은 조건을 반복할 때 생긴 차이일 수 있습니다.|S04
compare.items.hidden|점수가 내려가지 않았거나 없는 기준 {count}개를 숨겼습니다.|S04
compare.items.empty|점수가 내려간 기준이 없습니다. 할 일: 모두 보기에서 다른 기준을 확인하세요.|S04
compare.items.candidate|원인은 아직 추정입니다. 할 일: 원문과 값을 맞춰 확인하세요.|S04
compare.conditions.prompt_text|AI에게 시킨 글|S04
compare.headline.below_best|최근 결과는 지난 최고점보다 {gap}점 낮습니다.|S04
compare.result_a|결과 A|S04
compare.result_b|결과 B|S04
compare.total_score|전체 점수|S04
compare.score_value|{score} / 100점|S04
compare.target|목표 점수|S04
compare.below_target|{line}점보다 {gap}점 낮음|S04
compare.must|필수 기준|S04
compare.must_met|{met}/{total}가지 목표 달성|S04
compare.common_docs|공통 문서|S04
compare.dev_count|개발용 {count}건|S04
compare.recalculated|두 결과의 점수는 현재 선택한 정답으로 다시 계산했습니다.|S04
compare.open_wrong|새로 틀린 값의 원문 보기|S04
compare.selection.expand|실행 선택과 순서 바꾸기|S04
compare.selection.swap|A와 B 순서 바꾸기|S04
compare.selection.open_different|문서 구성이 다른 비교 보기|S04
compare.detail.expand|비교 조건과 항목별 차이와 AI에게 시킬 일|S04
compare.headline.decreased|이전 결과보다 점수가 {gap}점 낮아졌습니다.|S04
compare.detail.result_a|결과 A · 먼저 비교|S04
compare.detail.run|{time} · {model} · {score}점|S04
compare.detail.result_b|결과 B · 나중에 비교|S04
compare.detail.common_count|같은 문서 {count}건으로 비교했습니다.|S04
compare.detail.only_a|A에만 있는 문서는 {count}건입니다.|S04
compare.detail.only_b|B에만 있는 문서도 {count}건입니다.|S04
compare.detail.both_below|두 결과 모두 전체 목표 점수 {line}점 아래입니다.|S04
compare.detail.basis|비교 기준|S04
compare.detail.must_met|필수 17개 중 목표 이상|S04
compare.detail.nonempty_score|빈 행 제외 보조 점수|S04
compare.detail.pages|문서 자료|S04
compare.detail.concurrency|동시에 보내는 요청|S04
compare.detail.code|코드 기록|S04
compare.detail.example_answer|예시 답안|S04
compare.interpretation.title|조건과 점수의 해석|S04
compare.interpretation.loading|비교 결과를 읽는 중에는 ‘두 결과를 비교하고 있습니다’를 표시합니다.|S04
compare.interpretation.keep_selection|비교를 읽지 못하면 고른 A와 B를 유지합니다.|S04
compare.interpretation.retry|‘비교 결과를 다시 불러오기’로 재시도합니다.|S04
compare.interpretation.changed_prompt|바뀐 조건은 AI에게 준 AI에게 시킨 일입니다.|S04
compare.interpretation.causality|AI에게 시킬 일 변경만으로 점수 차이가 생겼다고 확정하지 않습니다.|S04
compare.interpretation.same|조건이 모두 같으면 ‘같은 조건의 반복’으로 표시합니다.|S04
compare.interpretation.common_first|문서 구성이 다르면 공통 문서부터 확인합니다.|S04
compare.interpretation.key_unknown|정답 기준을 확인할 수 없으면 ‘기록 당시 기준 미확인’으로 표시합니다.|S04
compare.criteria.title|항목별 차이 · 23개|S04
compare.criteria.direction|A → B|S04
compare.criteria.increased|높아짐 · 원인은 미확정|S04
compare.criteria.decreased|낮아짐 · 원인은 미확정|S04
compare.criteria.exposure|작업장 공기 중 허용 농도 (8번 부분 · 노출기준(작업장 공기 기준))|S04
compare.criteria.hidden_count|하락한 항목만 보는 경우 숨긴 수를 함께 표시합니다.|S04
compare.criteria.cause_threshold|{gap}점 이상 내려간 항목에는 원인 후보를 제시합니다.|S04
compare.criteria.no_cause|확인할 근거가 없으면 ‘원인 후보 없음’입니다.|S04
compare.prompt.title|AI에게 시킨 일의 차이|S04
compare.prompt.lines_a|{section}번 부분 설명: A는 {count}줄입니다.|S04
compare.prompt.lines_b|B는 {count}줄입니다.|S04
compare.prompt.changed_line|바뀐 줄: “{prompt_line}”|S04
compare.prompt.format|답변 형식은 두 결과 모두 표입니다.|S04
compare.prompt.hash_warning|이 설명을 다시 만든 확인값(해시)이 기록과 다르면 경고합니다.|S04
compare.prompt.full_text|설명 전문은 화면에서만 읽습니다.|S04
compare.values.title|바뀐 값과 표 행 수|S04
compare.values.correct_count|새로 맞춘 값 {total}개 중 {shown}개를 표시합니다.|S04
compare.values.product|{doc} · 제품 이름: {before} → {after}.|S04
compare.values.company|{doc} · 회사 이름: {before} → {after}.|S04
compare.values.wrong_count|새로 틀린 값 {total}개 중 {shown}개를 표시합니다.|S04
compare.values.scope|공통 문서의 필수 항목 상세에서 찾은 값입니다.|S04
compare.values.exposure|{doc}의 허용 농도: {before} mg/m³ → {after} mg/m³.|S04
compare.values.open_source|이 값의 원문 보기|S04
compare.table.title|여러 결과를 한 비교표로 만들기|S04
compare.table.column_order|선택한 순서대로 표의 열이 만들어집니다.|S04
compare.table.caption|표 제목|S04,S10
compare.table.name_a|결과 A의 표시 이름|S04
compare.table.before|수정 전|S04
compare.table.name_b|결과 B의 표시 이름|S04
compare.table.after|수정 후|S04
compare.table.selection_summary|선택 {count}개 · 각 결과의 점수를 매긴 문서 {documents}건 · 비교 가능|S04
compare.table.reload|결과 목록 새로 불러오기|S04
compare.table.create_ordered|선택한 순서로 비교표 만들기|S04
compare.table.open_job|만든 비교표의 작업 기록 보기|S04
compare.table.default_name|기본 표시 이름은 실행 이름입니다.|S04
compare.table.result_path|결과 파일:|S04
compare.table.open_title|여러 실행을 한 표로 모으기|S04
compare.table.open|비교표 만들기|S04,S05
compare.swapped.title|B는 A보다 {gap}점 높습니다.|S04
compare.swapped.order|선택 순서|S04
compare.swapped.swap_again|A와 B 순서 다시 바꾸기|S04
compare.different.title|두 실행의 점수를 매긴 문서 구성이 다릅니다.|S04
compare.different.common_first|공통 문서부터 확인하세요.|S04
compare.different.counts|A에만 {only_a}건이 있습니다. B에만 {only_b}건이 있습니다. 공통은 {common}건입니다.|S04
compare.different.open_common|공통 문서 확인하기|S04
compare.different.no_inference|각 실행의 전체 평균 차이만으로 개선을 단정하지 않습니다.|S04
compare.different.conditions|조건 차이 보기|S04
compare.different.set|자료 묶음|S04
compare.different.prompt|설명 버전|S04
compare.different.concurrency|동시 호출 수|S04
compare.different.code|코드 확인값|S04
compare.common.title|공통 개발 문서 {count}건을 비교합니다.|S04
compare.common.scope|비교 범위|S04
compare.common.values_scope|두 결과에 모두 있는 문서만 바뀐 값 비교에 사용합니다.|S04
compare.common.back|두 결과 비교로 돌아가기|S04,S10
compare.same.title|같은 조건을 반복한 두 결과입니다.|S04
compare.same.variation|실행마다 생기는 차이일 가능성이 있습니다.|S04
compare.same.no_inference|점수 변화만으로 설명 수정의 효과라고 판단하지 않습니다.|S04
compare.same.open_items|항목별 차이 보기|S04
compare.hash_mismatch.title|지금 복원한 설명이 실행 기록과 다릅니다.|S04
compare.hash_mismatch.state|설명 확인 필요|S04
compare.hash_mismatch.todo|기록의 확인값과 다릅니다. 할 일: 당시 보낸 글인지 작업 기록에서 확인하세요.|S04
compare.hash_mismatch.back|비교 조건으로 돌아가기|S04
compare.builder.title|고른 순서대로 결과를 한 표에 모으세요.|S10
compare.builder.display_name|표시 이름|S10
compare.builder.conditions|조건과 점수를 매긴 범위|S10
compare.builder.first_name|첫째 이름|S10
compare.builder.scope|이전 개발 자료. 같은 정답. 개발용 {count}건. 비교 가능.|S10
compare.builder.second_name|둘째 이름|S10
compare.builder.disabled|선택 불가|S10
compare.builder.answer_run|정답 생성 기록|S10
compare.builder.answer_excluded|정답 생성 실행은 비교 대상 아님.|S10
compare.builder.selected_count|선택한 결과는 {count}개입니다.|S10
compare.builder.selection_output|선택과 출력 위치|S10
compare.builder.swap|두 실행의 순서 바꾸기|S10
compare.builder.reload|실행 목록 다시 읽기|S10
compare.builder.empty_name|이름을 비워 두면 실행 이름을 씁니다.|S10
compare.builder.path|파일 위치:|S10
compare.builder_swapped.title|최근 결과를 첫 번째 열로 옮겼습니다.|S10
compare.builder_swapped.order|열 순서|S10
compare.builder_swapped.latest|최근 결과 · {score}점|S10
compare.builder_swapped.best|지난 최고점 · {score}점|S10
compare.builder_swapped.create|이 순서로 비교표 만들기|S10
compare.builder_running.title|두 실행으로 비교표를 만들고 있습니다.|S10
compare.builder_running.state|표 생성 중|S10
compare.builder_running.no_model|모델을 새로 부르지 않습니다.|S10
compare.builder_running.open_output|완성된 비교표 위치 보기|S10
compare.builder_done.title|두 실행의 비교표를 만들었습니다.|S10
compare.builder_done.columns|표의 열|S10
compare.side_a|A|S04
compare.side_b|B|S04
compare.values.expand|새로 맞춘 값과 새로 틀린 값|S04 바뀐 값 카드

### servers — S06 연결 · P02 확인

키|글|쓰는 곳
---|---|---
servers.confirm.load.title|회사 서버에서 {model}를 켤까요?|P02
servers.confirm.create.title|요금을 내고 새 서버를 만들까요?|P02
servers.confirm.delete.title|예시 서버 {server}을 삭제할까요?|P02
servers.confirm.unload.title|회사 서버의 모델을 끌까요?|P02
servers.confirm.tunnel_open.title|회사 서버로 가는 연결 통로를 열까요?|P02
servers.confirm.tunnel_close.title|회사 서버로 가는 연결 통로를 닫을까요?|P02
servers.confirm.batch.title|여러 문서 시험에 쓸 서버를 확인하세요.|P02
servers.diagnosis.ready.fact|회사 서버의 AI 모델이 응답했습니다.|rngd_diagnosis
servers.diagnosis.ready.todo|다시 시험에서 이 모델을 고르세요.|rngd_diagnosis
servers.diagnosis.no_model.fact|회사 서버에 켜진 AI 모델이 없습니다.|rngd_diagnosis
servers.diagnosis.no_model.todo|할 일: 모델을 켜세요. 준비에는 보통 15~25분 걸립니다.|rngd_diagnosis
servers.diagnosis.tunnel_closed.fact|회사 서버로 가는 연결 통로(SSH 터널)가 닫혀 있습니다.|rngd_diagnosis
servers.diagnosis.tunnel_closed.todo|할 일: 연결 통로를 여세요.|rngd_diagnosis
servers.diagnosis.loading.elapsed|AI 모델을 켜고 있습니다. {minutes}분 지났습니다.|rngd_diagnosis
servers.diagnosis.loading.unknown|AI 모델을 켜고 있습니다. 시작 시각은 확인하지 못했습니다.|rngd_diagnosis
servers.diagnosis.loading.todo|보통 15~25분 걸립니다. 기다리는 동안 저장된 결과를 읽을 수 있습니다.|rngd_diagnosis
servers.diagnosis.loading.late|{minutes}분을 넘겼습니다. 할 일: 서버 기록을 확인하세요.|rngd_diagnosis
servers.diagnosis.loading.log|회사 서버 기록 위치: /root/to21-bc/{tag}.log|rngd_diagnosis
servers.controls.busy|시험 중에는 서버를 바꿀 수 없습니다. 할 일: 작업이 끝난 뒤 다시 확인하세요.|S06
servers.controls.create|빌린 서버 목록을 확인하지 못해 새 서버를 만들 수 없습니다. 할 일: 서버 상태를 다시 확인하세요.|S06
servers.controls.delete|빌린 서버 목록을 확인하지 못해 삭제할 수 없습니다. 할 일: 서버 상태를 다시 확인하세요.|S06
servers.controls.up|회사 서버 상태를 확인하지 못해 AI를 켤 수 없습니다. 할 일: 서버 상태를 다시 확인하세요.|S06
servers.controls.down|회사 서버 상태를 확인하지 못해 AI를 끌 수 없습니다. 할 일: 서버 상태를 다시 확인하세요.|S06
servers.controls.no_ssh|회사 서버 접속 설정(RNGD_SSH)이 없습니다. 할 일: 설정 파일에서 준비하세요.|S06
servers.controls.no_port|회사 모델 주소가 내 컴퓨터 쪽 주소가 아닙니다. 할 일: RNGD_BASE_URL 설정을 확인하세요.|S06
servers.controls.open|연결 통로가 이미 열려 있습니다.|S06
servers.controls.closed|연결 통로가 이미 닫혀 있습니다.|S06
servers.controls.not_owned|이 앱이 연 연결이 아닙니다. 할 일: 연결을 연 터미널에서 닫으세요.|S06
servers.status.guide|AI 켜기와 비용에서 모델을 준비하세요.|S06
servers.status.busy|서버를 바꾸고 있습니다. 끝날 때까지 기다리세요.|S06
servers.status.unavailable|서버 상태를 확인하지 못해 변경을 막았습니다. 할 일: 상태를 다시 확인하세요.|S06
servers.status.failure.fact|서버 변경을 마치지 못했습니다.|S06
servers.status.failure.todo|할 일: 오류 기록에서 연결 상태와 진행 중인 작업을 확인하세요.|S06
servers.messages.pod_key_missing|빌린 모델의 접속 키가 설정되지 않았습니다. 할 일: 설정 파일의 RUNPOD_VLLM_API_KEY를 채운 뒤 설정 다시 읽기를 누르세요.|S06
servers.messages.pod_not_ours|이 앱이 만든 서버가 아니라 여기서 삭제할 수 없습니다. 할 일: 서버를 만든 사람에게 묻거나 RunPod 웹 화면에서 확인하세요.|S06
servers.messages.env_file_unknown|설정 파일의 위치를 찾지 못했습니다. 할 일: 앱을 다시 켜세요.|S06
servers.messages.tunnel_no_port|회사 모델 주소가 내 컴퓨터 쪽 주소가 아닙니다. 할 일: RNGD_BASE_URL을 확인한 뒤 설정을 다시 읽으세요.|S06
servers.messages.tunnel_already_open|내 컴퓨터의 {port}번 연결이 이미 열려 있습니다. 할 일: 모델이 응답하는지 확인하세요.|S06
servers.messages.tunnel_closed|내 컴퓨터의 {port}번 연결이 닫혀 있습니다. 할 일: 서버 상태를 다시 확인하세요.|S06
servers.messages.tunnel_not_ours|내 컴퓨터의 {port}번 연결은 이 앱이 열지 않았습니다. 할 일: 연결을 연 터미널에서 닫으세요.|S06
servers.messages.tunnel_exited|보안 연결 프로그램이 통로를 열기 전에 끝났습니다. 종료 코드는 {code}입니다. 할 일: RNGD_SSH 설정과 키 파일을 확인하세요.|S06
servers.messages.tunnel_timeout|연결 통로가 {seconds}초 안에 열리지 않았습니다. 할 일: 터미널에서 회사 서버에 접속되는지 확인하세요.|S06
servers.messages.tunnel_spawn_failed|보안 연결 프로그램을 시작하지 못했습니다. 할 일: 터미널에서 ssh 명령을 쓸 수 있는지 확인하세요.|S06
servers.messages.tunnel_still_open|닫기를 요청한 {port}번 연결이 아직 열려 있습니다. 할 일: 잠시 뒤 서버 상태를 다시 확인하세요.|S06
servers.choice.recommendation|추가 임대료 없는 회사 서버를 권합니다.|S06
servers.compare.cost|추가 임대료|S06,S08
servers.compare.wait|준비 시간|S06,S08
servers.compare.limits|사용 제한과 정리|S06,S08
servers.choice.company|추천 · 회사 서버(RNGD)|S06,S08
servers.compare.company.wait|15~25분|S06,S08
servers.compare.company.limit|한 번에 모델 하나|S06,S08
servers.choice.rented|다른 방법 · 빌린 서버(RunPod)|S06,S08
servers.compare.rented.cost|시간당 약 ${cost_per_hour} (예시)|S06,S08
servers.compare.rented.wait|준비 시간은 매번 다릅니다. 준비 중에는 기다린 시간을 보여 줍니다.|S06,S08
servers.compare.rented.cleanup|사용 뒤 삭제하세요. 잊어도 요청이 20분 없으면 앱이 지우고, 서버 안 타이머가 4시간에 지웁니다.|S06,S08
servers.compare.company.cost_meaning|추가 임대료가 없다는 뜻입니다. 회사 장비의 운영비까지 없다는 뜻은 아닙니다.|S06,S08
servers.company.connected|회사 서버로 가는 연결 통로는 열려 있습니다.|S01,S02,S03,S06,S08
servers.company.off|이 서버의 AI는 꺼져 있습니다. 켜는 데 보통 15~25분 걸립니다.|S06
servers.company.confirm_load|{model} 켜기 확인하기|S06
servers.company.read_while_waiting|기다리는 동안 저장된 결과를 읽을 수 있습니다.|S06
servers.company.return_target|돌아갈 대상: {doc} · {section}번 부분.|S06
servers.company.alternative|다른 방법|S06
servers.company.rented_fallback|회사 서버를 쓸 수 없으면 빌린 서버를 확인하세요.|S06
servers.company.open_rented|기존 임대 서버와 비용 보기|S06
servers.connection.title|컴퓨터 연결과 모델 응답 확인|S06
servers.connection.item|확인 항목|S06
servers.connection.selected|선택한 모델|S06
servers.connection.last_check|마지막 확인|S06
servers.connection.received_at|{time} · 이 컴퓨터가 응답을 받은 시각|S06
servers.connection.expected|기대한 모델|S06
servers.connection.responding|응답한 모델|S06
servers.connection.unknown|아직 확인되지 않음|S06
servers.connection.address|주소 설정|S06
servers.connection.configured|설정됨. 실제 주소와 키는 표시하지 않음|S06
servers.connection.ready_condition|기대한 모델의 응답이 와야 준비 완료입니다.|S06
servers.connection.details|AI 켜기와 비용 보기|S06
servers.connection.ssh_meaning|다른 컴퓨터에 암호화된 명령을 보내는 방법이 보안 접속(SSH)입니다.|S06
servers.connection.tunnel_meaning|AI 요청을 전달하는 연결 통로가 SSH 터널입니다.|S06
servers.connection.devices|계산 부품은 {count}장입니다. 한 번에 모델 하나를 올립니다.|S06
servers.connection.tunnel_owned|통로: 열림. 포트 {port}. 이 앱이 열었습니다.|S06
servers.connection.no_process|모델 프로세스는 없습니다. 사용 중인 계산 부품은 {count}장입니다.|S06
servers.connection.reload|설정 다시 읽기|S06
servers.connection.confirm_close|연결 닫기 확인하기|S06
servers.logs.summary|서버 기록 · 최근 {limit}줄 중 기록 {count}줄|S06
servers.logs.path|runs/manual/server-events.log|S06
servers.logs.redaction|명령 출력의 비밀값은 가립니다.|S06
servers.logs.manual_record|운영용 수동 기록에도 사용 내역을 옮겨 둡니다.|S06
servers.ready.title|{model}가 준비됐습니다.|S06
servers.ready.expected|기대한 모델이 응답했습니다.|S06
servers.ready.company_cost|회사 서버를 사용합니다. 추가 임대료는 없습니다.|S06
servers.ready.return_trial|시험으로 돌아가기|S06
servers.ready.target_preserved|{doc}의 {section}번 부분을 그대로 보관했습니다.|S06
servers.ready.prompt_preserved|편집 중 설명도 같은 화면 메모리에 남습니다.|S06
servers.ready.check|응답 확인|S06
servers.ready.checked_at|마지막 확인: {time}.|S06,E08
servers.ready.expected_model|기대한 모델: {model}.|S06
servers.ready.responding_model|응답한 모델: {model}.|S06
servers.ready.confirm_unload|모델 끄기 확인하기|S06
servers.rented.title|기존 빌린 서버를 이어 쓰고 있습니다.|S06
servers.rented.responded|{model}가 응답했습니다.|S06
servers.rented.adopted|앱이 만든 예시 서버 {server}을 자동으로 이어받았습니다.|S06
servers.rented.cost|실제 요금이 나갑니다: 시간당 약 ${cost_per_hour} (예시).|S06
servers.rented.estimated_cost|가동 {hours}시간의 추정 비용은 ${cost}입니다.|S06
servers.rented.deletion_hours|생성 후 4시간에 자동 삭제합니다. 지금은 {hours}시간 남았습니다.|S06
servers.rented.scheduler|요청이 20분 없으면 앱이 지웁니다. 이 감시는 앱이 켜져 있을 때만 돕니다. 4시간 타이머는 서버 안에서 돌아 앱이 꺼져도 지웁니다.|S06
servers.rented.list_storage|서버 목록과 저장공간 비용|S06
servers.rented.ownership|소유와 상태|S06
servers.rented.uptime|가동 시간|S06
servers.rented.hourly_rate|시간당 요금|S06
servers.rented.total_cost|추정 비용|S06
servers.rented.owned_running|앱이 만듦. 실행 중.|S06
servers.rented.confirm_delete|삭제 확인하기|S06
servers.rented.external_stopped|앱이 만든 서버 아님. 정지됨.|S06
servers.rented.unknown|알 수 없음|S06
servers.rented.delete_forbidden|삭제 권한 없음|S06
servers.rented.estimate_warning|추정 비용은 최종 청구액과 다를 수 있습니다.|S06
servers.rented.unknown_cost|확인하지 못한 비용을 무료로 표시하지 않습니다.|S06
servers.rented.volumes|별도 저장공간(네트워크 볼륨)은 {count}개입니다.|S06
servers.rented.storage_cost|저장공간은 서버 삭제 뒤에도 비용이 남을 수 있습니다.|S06
servers.rented.use_company|회사 서버 사용하기|S06
servers.rented.confirm_create|새 서버 요금 확인하기|S06
servers.rented.adoption_details|모델과 인계 확인|S06
servers.rented.expected_reply|기대한 모델과 응답한 모델은 {model}입니다.|S06
servers.rented.adopted_id|자동 인계된 번호는 {pod_id}입니다.|S06
servers.rented.other_id|다른 서버 번호는 {pod_id}입니다.|S06
servers.rented.no_manual_adoption|임의 서버를 고르는 인계 단추는 제공하지 않습니다.|S06
servers.creating.title|새 빌린 서버에서 {model}를 켜고 있습니다.|S06
servers.creating.elapsed|{minutes}분 경과|S06
servers.creating.last_check|완료될 시각은 아직 모릅니다. 마지막 확인은 {time}입니다.|S06
servers.creating.read_results|기다리는 동안 최근 결과 보기|S06,E08
servers.creating.estimated_cost|가동 {minutes}분의 추정 비용은 약 ${cost}입니다.|S06
servers.creating.deletion_remaining|생성 후 4시간에 자동 삭제합니다. {hours}시간 {minutes}분 남았습니다.|S06
servers.creating.cost_running|준비 중인 시간에도 요금이 나갑니다.|S06
servers.creating.target|보관한 시험: {doc} · {section}번 부분.|S06
servers.creating.details|서버와 준비 상태|S06
servers.creating.server_id|새로 만든 번호: {pod_id}.|S06
servers.creating.no_reply|앱이 만든 서버입니다. 아직 모델 응답이 없습니다.|S06
servers.creating.open_ready|준비 완료 상태 보기|S06,E08
servers.creating.open_company|회사 서버 확인하기|S06
servers.deleting.title|예시 서버 {server}의 삭제를 확인하고 있습니다.|S06
servers.deleting.requested|삭제 요청을 보냈습니다.|S06
servers.deleting.cost|삭제 완료가 확인되기 전에는 요금이 계속 나갈 수 있습니다.|S06
servers.deleting.refresh|삭제 결과 확인하기|S06
servers.deleting.uptime|마지막 확인 가동 시간: {hours}시간.|S06
servers.deleting.estimated_cost|마지막 확인 추정 비용: ${cost}.|S06
servers.deleting.no_resend|같은 삭제 요청을 다시 보내지 않습니다.|S06
servers.deleted.title|예시 서버 {server}을 삭제했습니다.|S06
servers.deleted.external_remaining|남은 서버는 앱이 만들지 않은 예시 서버 {server}입니다.|S06
servers.deleted.no_permission|이 서버에는 삭제 권한이 없습니다.|S06
servers.deleted.estimated_cost|마지막 추정 비용은 ${cost}입니다. 최종 청구액은 아닙니다.|S06
servers.deleted.storage_cost|별도 저장공간이 남으면 그 비용은 계속 나갈 수 있습니다.|S06
servers.deleted.prepare|다시 시험할 모델 준비하기|S06
servers.empty.title|이어 쓸 빌린 서버가 없습니다.|S06
servers.empty.count|서버 목록 {count}개|S06
servers.empty.new_cost|새 서버를 만들면 시간당 실제 요금이 발생합니다.|S06
servers.empty.recommendation|추천 방법|S06
servers.empty.open_company|회사 서버 먼저 확인하기|S06
servers.failed.title|모델 상태를 확인하지 못했습니다.|S06
servers.failed.stale|마지막 상태를 현재 상태로 쓰지 않습니다.|S06
servers.failed.todo|할 일: 다시 확인하기를 누르세요. 계속되면 자세히 보기의 오류 기록을 보세요. 그동안 서버 변경은 막아 둡니다.|S06
servers.failed.retry|다시 확인하기|S06
servers.failed.target|대상은 {doc}의 {section}번 부분으로 유지합니다.|S06
servers.failed.error|조회 오류|S06
servers.failed.no_reply|서버 상태 요청에 응답이 없었습니다.|S06
servers.failed.no_inference|준비됨이나 모델 없음으로 추정하지 않습니다.|S06
servers.checking.title|모델의 응답을 확인하고 있습니다.|S06
servers.checking.wait|확인이 끝날 때까지 기다리세요.|S06
servers.checking.state|상태 확인 중|S06
servers.checking.results|확인 결과 상태 보기|S06
servers.checking.open_ready|준비된 모델 보기|S06
servers.checking.open_failed|조회 실패 보기|S06
servers.busy.title|시험 중에는 모델을 바꿀 수 없습니다.|S06
servers.busy.running|{doc} 시험이 진행 중입니다.|S06
servers.busy.restricted|모델 끄기와 교체와 연결 닫기를 제한했습니다.|S06
servers.busy.open_job|진행 작업 보기|S06
servers.busy.allow_tunnel|닫힌 연결 통로를 여는 행동은 허용합니다.|S06
servers.busy.open_tunnel|연결 열기 확인하기|S06,E07
servers.mismatch.title|서버에 다른 AI 모델이 켜져 있습니다.|S06
servers.mismatch.limit|회사 서버는 한 번에 모델 하나만 사용합니다.|S06
servers.mismatch.unload|기존 모델 끄기 확인하기|S06
servers.env.title|설정 파일의 {line_no}번째 줄을 읽지 못했습니다.|S06
servers.env.state|설정 확인 필요|S06
servers.env.todo|할 일: 설정 파일(.env)의 해당 줄을 고친 뒤 설정을 다시 읽으세요.|S06
servers.env.names|필요한 설정 이름|S06
servers.env.company_name|RNGD_BASE_URL|S06,S07
servers.env.company_meaning|: 회사 모델의 응답 주소.|S06
servers.env.rented_name|RUNPOD_VLLM_API_KEY|S06,S07
servers.env.rented_meaning|: 빌린 모델의 접속 키.|S06
servers.env.hidden_values|설정 값은 이 화면에 표시하지 않습니다.|S06
servers.account_failed.title|빌린 서버 목록을 읽지 못했습니다.|S06
servers.account_failed.state|계정 확인 실패|S06
servers.account_failed.todo|할 일: 설정 파일의 관리 키와 계정 권한을 확인하세요.|S06
servers.account_failed.cost_unknown|가동 시간과 비용은 알 수 없습니다.|S06
servers.create_unknown.title|새 서버 생성 결과를 확인하지 못했습니다.|S06
servers.create_unknown.state|생성 여부 확인 필요|S06
servers.create_unknown.todo|할 일: 다시 만들기 전에 서버 목록부터 확인하세요.|S06
servers.create_unknown.reload|서버 목록 다시 확인하기|S06
servers.confirm.summary|실행할 내용|P02
servers.confirm.load.target|{model}. 계산 부품 {count}장. 한 번에 모델 하나.|P02
servers.confirm.load.cost|추가 임대료 없음. 준비 15~25분.|P02
servers.confirm.once|이 확인 화면에서는 한 번만 실행할 수 있습니다.|P02
servers.confirm.expires|{time}까지 실행할 수 있습니다(예시). 시간이 지나면 확인 화면을 다시 여세요.|P02
servers.confirm.load.action|확인하고 모델 켜기|P02
servers.confirm.cancel|취소하고 돌아가기|P02
servers.confirm.conditions|실행할 수 있는 조건 보기|P02
servers.confirm.recheck|실행 직전에 상태와 권한을 다시 확인합니다.|P02
servers.confirm.changed_state|상태가 바뀌면 이전 확인으로 실행하지 않습니다.|P02
servers.confirm.open_expired|실행 시간이 지난 경우 보기|P02
servers.confirm.open_busy|진행 작업 때문에 잠긴 경우 보기|P02
servers.confirm.create.target|{model}. 기존 서버가 있으면 비용이 추가됩니다.|P02
servers.confirm.create.cost|켜진 동안 시간당 약 ${cost_per_hour}가 듭니다(예시). 준비 완료 시각은 모릅니다. 요청이 20분 없으면 앱이 지우고, 앱이 꺼져 있어도 서버 안 타이머가 4시간에 지웁니다.|P02
servers.confirm.create.action|시간당 약 ${cost_per_hour} 서버 만들기|P02
servers.confirm.delete.target|{pod_id}. 이 앱이 만든 서버입니다. 진행 작업은 없습니다.|P02
servers.confirm.delete.cost|가동 {hours}시간. 추정 비용 ${cost}. 별도 저장공간 비용은 남을 수 있습니다.|P02
servers.confirm.delete.action|예시 서버 {server} 삭제하기|P02
servers.confirm.unload.target|{model}. 진행 중인 작업은 없습니다.|P02
servers.confirm.unload.effect|모델을 끈 뒤 새 모델을 켤 수 있습니다.|P02
servers.confirm.unload.action|확인하고 모델 끄기|P02
servers.confirm.tunnel_open.effect|이 컴퓨터에서 회사 모델에 요청을 전달하는 길을 엽니다.|P02
servers.confirm.tunnel_open.allowed|모델을 새로 올리는 작업은 아닙니다. 진행 중에도 열 수 있습니다.|P02
servers.confirm.tunnel_open.action|확인하고 연결 열기|P02
servers.confirm.tunnel_close.state|진행 작업은 없습니다. 현재 켜진 모델은 없습니다.|P02
servers.confirm.tunnel_close.effect|닫으면 이 컴퓨터에서 시험을 보낼 수 없습니다.|P02
servers.confirm.tunnel_close.action|확인하고 연결 닫기|P02
servers.confirm.batch.target|개발용 {count}건. 반복 {repeats}회. {model}.|P02
servers.confirm.batch.cost|빌린 서버를 쓰면 시간당 약 ${cost_per_hour}입니다(예시).|P02
servers.confirm.batch.action|확인하고 시험 시작하기|P02
servers.confirm.expired.not_executed|아직 실행하지 않았습니다.|P02
servers.confirm.expired.reload|상태 다시 읽기|P02
servers.unloaded.title|회사 서버의 {model}를 내렸습니다.|S06
servers.unloaded.process|종료한 프로세스 번호: {pid} (예시).|S06
servers.unloaded.tunnel|연결 통로는 열려 있습니다.|S06
servers.unloaded.select_model|새 모델 고르기|S06
servers.confirm.tunnel_open.no_load|모델을 켜는 작업은 아닙니다.|P02
servers.confirm.expires_once|{time}까지 한 번만 실행할 수 있습니다(예시). 시간이 지나면 확인 화면을 다시 여세요.|P02
servers.confirm.unload.model_title|{model}를 끌까요?|P02
servers.confirm.unload.no_jobs|진행 중인 작업은 없습니다.|P02
servers.confirm.unload.no_trial|모델을 끄면 새 시험을 보낼 수 없습니다.|P02

### jobs — S03 시험 · S05 기록 · S09 여러 문서

키|글|쓰는 곳
---|---|---
jobs.result_missing.fact|작업은 끝났지만 결과 파일이 없습니다.|S03
jobs.target_mismatch.fact|받은 결과가 보낸 시험 대상과 다릅니다.|S03
jobs.send_unknown.fact|시험이 보내졌는지 확인하지 못했습니다.|S03
jobs.stopped.fact|시험을 멈췄습니다.|S03
jobs.no_runnable.fact|지금 묶음에는 시험할 수 있는 문서가 없습니다.|S03
jobs.confirm.stop.title|진행 중인 시험을 멈출까요?|P02
jobs.confirm.stop.target|{doc}의 {section}번 부분. 작업 번호 {job_id}.|P02
jobs.confirm.stop.loss|아직 저장되지 않은 결과를 잃을 수 있습니다.|P02
jobs.confirm.stop.action|확인하고 시험 멈추기|P02
jobs.try_hint.ready|응답한 모델이 {count}개 있습니다. 모델을 고른 뒤 실제 시험을 시작하세요.|S03
jobs.try_hint.off|응답한 모델이 없습니다. AI 없이 보낼 내용만 확인할 수 있습니다. 실제 시험을 하려면 AI 켜기와 비용에서 모델을 준비하세요.|S03
jobs.fields.model|문서에서 값을 뽑을 모델입니다. 연결된 모델부터 보여 줍니다.|S03
jobs.fields.doc|시험할 개발용 문서입니다. 평가용 문서는 고를 수 없습니다.|S03
jobs.fields.pages|AI에게 보낼 원문 글자를 모은 폴더입니다.|S03
jobs.fields.scope|다시 시험할 부분을 고릅니다. 문서 전체를 고르면 16개 부분을 보냅니다.|S03
jobs.fields.prompt|AI에게 시킬 일을 적습니다. 한 부분만 시험할 때 고칠 수 있습니다.|S03
jobs.fields.base_run|새 답을 끼워 넣어 점수를 비교할 이전 결과입니다. 자동 선택은 같은 모델의 최근 개발용 10건 결과를 씁니다.|S03
jobs.fields.dry_run|AI 없이 보낼 원문과 시킬 일만 확인합니다.|S03
jobs.fields.repeat|같은 조건으로 실행할 횟수입니다. 1~10회로 정합니다.|S03
jobs.fields.run_name|결과를 모아 둘 폴더 이름입니다. 회차마다 _r1, _r2가 붙습니다.|S03
jobs.fields.compare_label|비교표에서 실행을 부를 이름입니다. 비우면 실행 이름을 씁니다.|S03
jobs.stages.input|AI에게 보낸 원문 글자입니다. 앞에 붙은 p2:L23은 2쪽 23번째 줄입니다.|S03
jobs.stages.prompt|AI에게 시킨 일입니다. 글 전체를 기록 파일에 남기지 않습니다.|S03
jobs.stages.raw_answer|AI가 쓴 답을 그대로 보여 줍니다.|S03
jobs.stages.parsed|AI의 답에서 읽어 낸 값입니다. 표로 읽지 못해 버린 줄 수도 보입니다.|S03
jobs.stages.to21|읽어 낸 값을 정해진 결과 칸(TO21 JSON)에 넣은 내용입니다.|S03
jobs.stages.score|이전 결과에서 시험한 부분의 답만 바꿔 다시 계산한 점수입니다. 전체를 새로 시험한 점수는 아닙니다.|S03
jobs.actions.send|실제 시험 시작하기|S03,S08
jobs.actions.preview|AI 없이 보낼 내용 확인하기|S03,S05
jobs.actions.run_unavailable|응답한 모델을 고르면 시험할 수 있습니다.|S03
jobs.actions.more_summary|여러 문서 시험과 비교표 만들기를 펼쳐 보세요.|S03
jobs.kinds.dev10|개발용 10건 시험|S03
jobs.kinds.single|문서 한 건 시험|S03
jobs.kinds.probe|일부 문서 시험|S03
jobs.kinds.silver|AI 정답 초안 만들기|S03
jobs.kinds.eval|평가용 기록 · 열람 제한|S03
jobs.kinds.outside|새 문서 시험 · 점수 없음|S03
jobs.kinds.models|비교표|S03
jobs.trial.title|같은 부분을 AI에게 다시 읽힐 준비가 됐습니다.|S03,S08
jobs.trial.target|{doc} · {section}번 부분 · 작업장 공기 중 허용 농도|S03,S08
jobs.trial.base_result|비교할 결과: {time} · {score}점|S03,S08
jobs.prompt.hint|예: “숫자와 단위를 원문 그대로 옮기세요.” 고친 글은 새로고침하면 사라집니다.|S03,S08
jobs.prompt.retest_hint|고쳐서 점수를 비교하세요. 그대로 같은 부분을 다시 시험해도 됩니다.|S03,S08
jobs.focus.title|원문 화면에서 고른 문제 값|S03 (관문 ④ 결정 10/31)
jobs.focus.pair|비교한 정답: {key_value} · AI가 쓴 값: {ai_value}|S03
jobs.focus.missing|비교한 정답: {key_value} · AI가 쓴 값: 없음(못 뽑음)|S03
jobs.focus.made|비교한 정답: 없음 · AI가 쓴 값: {ai_value}(만듦)|S03
jobs.focus.line|원문 {page}쪽 {line_no}번째 줄: {line_text}|S03
jobs.focus.line_estimated|원문 {page}쪽 {line_no}번째 줄(추정): {line_text}|S03
jobs.focus.none|원문 화면에서 고른 값이 없습니다. 이 부분 전체를 다시 시험합니다.|S03
jobs.trial.company_ready|{model}가 응답했습니다. 회사 서버를 사용합니다.|S03,S08
jobs.trial.company_cost|회사 서버는 추가 임대료가 없습니다.|S03,S08
jobs.trial.duration|시험은 약 {seconds}초~{minutes}분입니다(예시). 준비 시간은 별도입니다.|S03,S08
jobs.trial.practice_meaning|AI 없이 보낼 내용만 확인하는 연습입니다. 실제 시험 기록과 점수는 생기지 않습니다.|S03,S08
jobs.scope.expand|시험 범위와 이전 결과 바꾸기|S03,S08
jobs.scope.label|다시 읽힐 범위|S03,S08
jobs.scope.single|한 부분 · {section}번 부분|S03,S08
jobs.scope.multiple|여러 부분 · {section}번과 {other_section}번 부분|S03,S08
jobs.scope.whole|문서 전체 · 16개 부분|S03,S08
jobs.scope.prompt_limit|설명 수정은 한 부분 시험에서만 사용합니다.|S03,S08
jobs.scope.open_multiple|여러 부분 시험 화면 보기|S03,S08
jobs.scope.open_whole|문서 전체 시험 화면 보기|S03,S08
jobs.scope.doc_id|문서 관리 번호|S03,S08
jobs.scope.sets|원문과 다음 시험 자료|S03,S08
jobs.scope.base_run|새 답을 끼워 넣을 이전 결과|S03,S05
jobs.scope.auto_selected|자동 선택 ·|S03,S08
jobs.scope.check_runnable|고른 문서를 시험할 수 있는지 확인합니다.|S03,S08
jobs.scope.open_mismatch|묶음이 다른 경우 보기|S03,S08
jobs.prompt.details|설명의 출처와 보관 방식 보기|S03,S08
jobs.prompt.origin|기본 설명은 모델별 기본 설정에서 가져옵니다.|S03,S08
jobs.prompt.mode|설명 사용 방식|S03,S08
jobs.prompt.edit|기본 설명 고쳐 쓰기|S03,S08
jobs.prompt.default|기본 설명 그대로|S03,S08
jobs.prompt.review_foreign|다른 모델이나 다른 부분의 글을 가져오면 전송 전에 재검토합니다.|S03,S08
jobs.prompt.memory_only|고친 글 전체는 현재 화면에만 보관합니다.|S03,S08
jobs.prompt.delete_temp|전송 임시 파일은 보낸 뒤 지웁니다.|S03,S08
jobs.prompt.hash_only|기록에는 내용 확인값(해시)만 남깁니다.|S03,S08
jobs.prompt.open_review|출처가 다른 설명 재검토 보기|S03,S08
jobs.off.title|다시 시험하려면 AI 모델이 켜져 있어야 합니다.|S03,S06
jobs.off.model|{model}는 아직 준비되지 않았습니다.|S03
jobs.off.connect|AI 연결하기|S03
jobs.running.title|시험이 진행 중입니다.|S03,S08
jobs.running.elapsed|{minutes}분 {seconds}초 경과|S03,S08
jobs.running.target|{doc}의 {section}번 부분을 {model}가 읽고 있습니다.|S03,S08
jobs.running.open_jobs|작업 기록 보기|S03,S08
jobs.running.leave_screen|다른 화면으로 가도 시험은 계속됩니다.|S03,S08
jobs.running.no_resend|같은 시험을 자동으로 다시 보내지 않습니다.|S03,S08
jobs.running.details|보낸 조건과 중단|S03,S08
jobs.running.sent|보낸 값|S03,S08
jobs.running.set|문서 묶음|S03,P01
jobs.running.previous_set|이전 개발 자료|S03,S04
jobs.running.answer|AI가 먼저 만든 정답 · 보낼 때 고른 기준|S03,S08
jobs.running.job_id|작업 번호|S03,S08
jobs.running.real_call|실제 호출|S03,S08
jobs.running.real_trial|실제 시험. 연습 아님.|S03,S08
jobs.running.stop|시험 멈추기|S03,S05
jobs.running.open_finished|완료 상태 보기|S03,S08
jobs.running.open_success|성공 결과 보기|S03,S08
jobs.running.open_parse_failure|값을 읽지 못한 결과 보기|S03,S08
jobs.done.title|이 부분의 실제 시험이 끝났습니다.|S03,S08
jobs.done.success|실제 시험 성공|S03,S08
jobs.done.target|{doc} · {section}번 부분 · {model}|S03,S08
jobs.result.partial_score|이 부분만 바꿔 계산한 점수: {before}점 → {after}점.|S03,S08
jobs.result.partial_meaning|이전 결과에서 {section}번 부분의 답만 바꿔 다시 계산했습니다. 전체를 새로 시험한 점수는 아닙니다.|S03,S08
jobs.result.batch_effect|이번 점수 차이는 한 문서의 한 부분만 반영합니다. 전체 문서에 미친 효과는 ‘여러 문서 시험하기’로 확인하세요.|S03,S08
jobs.done.keep_base|저장된 이전 결과는 그대로 남아 있습니다.|S03,S08
jobs.done.open_source|같은 위치의 원문 보기|S03,S08
jobs.detail.input|1. 보낸 입력|S03,S08
jobs.detail.pages|원문 폴더|S03,S08
jobs.detail.split|나눈 방법|S03,S08
jobs.detail.heading_based|제목 기준|S03,S08
jobs.detail.msds_count|안전자료 수|S03,S08
jobs.detail.first_only|{count}개. 첫 번째 자료만 사용.|S03,S08
jobs.detail.range_label|부분과 범위|S03,S08
jobs.detail.range|{section}번 부분. {page}쪽 {first_line}~{last_line}번째 줄.|S03,S08
jobs.detail.line_count|글자 {count}줄. 쪽과 줄 번호를 앞에 붙임.|S03,S08
jobs.detail.unused|사용 안 함|S03,S08
jobs.detail.prompt|2. AI에게 시킨 일 기록|S03,S08
jobs.detail.prompt_edited|{section}번 부분의 설명을 수정했습니다.|S03,S08
jobs.detail.prompt_hash|내용 확인값(해시):|S03,S08
jobs.detail.no_full_text|전문은 기록 파일에 남기지 않습니다.|S03,S08
jobs.detail.raw_answer|3. AI의 원래 답|S03,S08
jobs.detail.response|표 형식. 정상 종료. 응답 시간 {seconds}초.|S03,S08
jobs.detail.no_answer|응답이 없을 때는 ‘답변 없음’을 표시합니다.|S03,S08
jobs.detail.parsed|4. 읽어 낸 값|S03,S08
jobs.detail.parse_stats|해석 성공. 버린 줄 {discarded}개. 다시 뽑음 {retries}회. 시도 {attempts}회.|S03,S08
jobs.detail.tokens|입력 길이 {input_tokens}토큰. 출력 길이 {output_tokens}토큰.|S03,S08
jobs.detail.token_meaning|AI가 글을 처리하는 길이 단위가 토큰입니다.|S03,S08
jobs.detail.evidence_checked|오류 없음. 근거 줄 검사 완료.|S03,S08
jobs.detail.converted|5. 정해진 형식으로 바꾼 값|S03,S08
jobs.detail.fields|노출기준 표 {rows}행. 객체 칸 {fields}개.|S03,S08
jobs.detail.no_extra|해당 부분의 추가 설명은 없습니다.|S03,S08
jobs.detail.score|6. 시험 전후 점수|S03,S08
jobs.detail.partial_score|이 부분만 바꿔 계산하면 {before}점에서 {after}점이 됩니다.|S03,S08
jobs.detail.base_run|새 답을 끼워 넣은 이전 결과:|S03,S08
jobs.detail.key|보낼 때 고른 정답: AI가 먼저 만든 정답.|S03,S08
jobs.detail.key_hash|정답 파일 내용의 확인값:|S03,P01
jobs.detail.hash_meaning|확인값은 현재 정답 파일을 구분하는 표시입니다. 과거 정답을 복원할 수는 없습니다.|S03,S08
jobs.detail.changed_criterion|바뀐 점수 기준: 작업장 공기 중 허용 농도.|S03,S08
jobs.detail.no_causality|한 번의 결과로 개선 원인을 확정하지 않습니다.|S03,S08
jobs.completion.title|결과 기록과 완료 판정|S03,S08
jobs.completion.job_id|작업 번호:|S03,S08
jobs.completion.path|결과 위치:|S03,S08
jobs.completion.evidence|확인 근거|S03,S08
jobs.completion.value|이 장면의 값|S03,S08
jobs.completion.state|작업 상태|S03,S08
jobs.completion.exit_code|종료 코드|S03,S08
jobs.completion.practice|연습 여부|S03,S05
jobs.completion.shape|결과 모양|S03,S08
jobs.completion.fields|plan, results, fields, base_run, score, score_skipped, saved|S03,S08
jobs.completion.parse|선택 부분의 해석 결과|S03,S08
jobs.completion.target_match|대상 일치|S03,S08
jobs.completion.same_section|보낸 문서와 {section}번 부분이 같음|S03,S08
jobs.completion.record|성공 기록|S03,S08
jobs.completion.real_success|실제 성공 기록|S03,S08
jobs.completion.open_missing|결과 파일이 없는 상태 보기|S03,S08
jobs.parse_failed.title|AI가 답했지만 {section}번 부분 값을 읽지 못했습니다.|S03,S08
jobs.parse_failed.state|값 해석 실패|S03,S08
jobs.parse_failed.fact|작업은 끝났지만 AI의 답을 값으로 읽지 못했습니다.|S03,S08
jobs.parse_failed.todo|실제 시험 성공은 기록하지 않았습니다. 할 일: {stage}단계의 오류를 보고 다시 시험하세요.|S03,S08
jobs.parse_failed.retry|같은 조건으로 다시 시험하기|S03,S08
jobs.parse_failed.columns|해석 실패. 표의 열 수가 맞지 않습니다.|S03,S08
jobs.parse_failed.column_count|오류: 필요한 {expected}개 칸 중 {received}개만 받았습니다.|S03,S08
jobs.parse_failed.no_fields|해석에 실패해 최종 값을 만들지 못했습니다.|S03,S08
jobs.parse_failed.no_score|이 부분을 해석하지 못해 점수 비교를 완료하지 못했습니다.|S03,S08
jobs.parse_failed.no_record|기록하지 않음|S03,S08
jobs.practice_done.title|입력과 설명만 확인했습니다.|S03,S08
jobs.practice_done.state|연습 완료|S03,S05
jobs.practice_done.no_success|실제 시험 성공은 아직 없습니다.|S03,S08
jobs.practice_done.connect|모델 연결하기|S03,S08
jobs.practice_done.omitted_stages|연습에서는 {first_stage}~{last_stage}단계의 모델 응답과 점수를 만들지 않습니다.|S03,S08
jobs.practice_done.shape|plan만 있음|S03,S08
jobs.practice_done.record|연습에만 기록|S03,S08
jobs.score_skipped.fact|시험 전후 점수는 계산하지 않았습니다.|S03
jobs.score_skipped.no_key|이 문서에 대응하는 정답이 없습니다.|S03
jobs.score_skipped.reason|정답이 없어 점수 계산을 생략했습니다.|S03
jobs.multiple.title|{section}번과 {other_section}번 부분을 함께 시험합니다.|S03
jobs.multiple.prompt|AI에게 시킬 일|S03
jobs.multiple.no_edit|설명을 고쳐 쓰려면 한 부분만 고르세요.|S03
jobs.multiple.send|선택한 부분 다시 시험하기|S03
jobs.multiple.change_scope|범위 바꾸기|S03
jobs.multiple.single|한 부분으로 돌아가기|S03
jobs.multiple.whole|문서 전체 고르기|S03
jobs.whole.title|{doc}의 전체를 시험합니다.|S03
jobs.whole.prompts|16개 부분의 기본 설명을 사용합니다.|S03
jobs.whole.journey_scope|첫 시험 안내는 한 부분 실제 시험으로 완료합니다.|S03
jobs.whole.send|문서 전체 다시 시험하기|S03
jobs.whole_running.title|문서의 16개 부분을 시험하고 있습니다.|S03
jobs.whole_running.state|진행 중|S03
jobs.whole_running.elapsed|{doc}. 시작 후 {minutes}분이 지났습니다.|S03
jobs.whole_running.open_result|문서 전체 결과 보기|S03
jobs.whole_done.title|16개 부분 중 {failed}개를 해석하지 못했습니다.|S03
jobs.whole_done.success|성공한 부분|S03
jobs.whole_done.failure|실패한 부분|S03
jobs.whole_done.failed_count|{section}번 부분 {count}개|S03
jobs.whole_done.duration|걸린 시간|S03
jobs.whole_done.raw_path|원래 답 폴더|S03
jobs.whole_done.kind|이 결과는 문서 전체 시험 기록입니다.|S03
jobs.whole_done.no_journey_success|한 부분 안내의 실제 성공으로 대신 세지 않습니다.|S03
jobs.whole_done.return_single|한 부분 시험으로 돌아가기|S03
jobs.whole_done.shape|전체 결과의 기록 구조|S03
jobs.whole_done.fields|plan, run, summary, score, base_run, saved|S03
jobs.whole_done.summary|각 부분의 결과는 summary에서 읽습니다. 항 시험의 results를 가정하지 않습니다.|S03
jobs.result_missing.target_kept|대상을 유지했습니다.|S03
jobs.result_missing.todo|결과 조회에 내용이 없습니다({status_code}). 할 일: 작업 기록을 확인하세요.|S03
jobs.result_missing.open_log|작업 로그 보기|S03
jobs.target_mismatch.todo|성공을 기록하지 않았습니다. 할 일: 작업 기록에서 보낸 문서와 결과 문서를 맞춰 보세요.|S03
jobs.send_unknown.todo|자동으로 다시 보내지 않습니다. 할 일: 작업 기록에서 같은 시험이 있는지 보세요.|S03
jobs.stopped.late_reply|이후 늦게 온 응답도 성공으로 기록하지 않습니다.|S03
jobs.stopped.return_target|시험 대상으로 돌아가기|S03
jobs.no_runnable.todo|할 일: 문서 목록에서 시험할 수 없는 이유를 확인하세요.|S03
jobs.set_mismatch.title|원문과 다음 시험의 문서 묶음이 다릅니다.|S03
jobs.set_mismatch.source|읽은 원문|S03
jobs.set_mismatch.recorded|실행 당시 · 이전 개발 자료 {version}판|S03
jobs.set_mismatch.next|다음 시험|S03
jobs.set_mismatch.current|현재 선택 · 이전 개발 자료 {version}판|S03
jobs.set_mismatch.select|시험에 쓸 묶음|S03
jobs.set_mismatch.source_option|원문을 본 {version}판|S03
jobs.set_mismatch.current_option|현재 선택한 {version}판|S03
jobs.set_mismatch.prepare|고른 묶음으로 시험 준비하기|S03
jobs.set_mismatch.keep_context|문서와 {section}번 부분과 편집한 설명은 유지합니다.|S03
jobs.prompt_review.title|이 설명은 다른 부분에서 가져왔습니다.|S03
jobs.prompt_review.target|현재 대상은 {doc}의 {section}번 부분입니다.|S03
jobs.prompt_review.origin|설명 출처는 {model}의 {section}번 부분입니다.|S03
jobs.prompt_review.todo|{section}번 부분에 맞는 설명으로 고쳐 주세요.|S03
jobs.prompt_review.restore|{section}번 부분 기본 설명으로 돌아가기|S03
jobs.list.title|진행 중인 작업과 결과를 여기에서 이어 봅니다.|S05
jobs.list.single_trial|한 부분 시험|S05,S09
jobs.list.target|{doc} · {section}번 부분|S05
jobs.list.elapsed|진행 중 · {minutes}분 {seconds}초|S05
jobs.list.batch_target|개발용 {count}건 · {repeats}회|S05
jobs.list.rounds_done|완료 · {completed}/{total}회|S05
jobs.list.selected_runs|선택 결과 {count}개|S05
jobs.list.external|다른 터미널 작업|S05
jobs.list.target_unknown|대상 확인 안 됨|S05
jobs.list.unstoppable|진행 중 · 중단 불가|S05
jobs.list.open_trial|선택한 시험 상태 보기|S05
jobs.selected.title|선택한 작업의 상세|S05
jobs.selected.target|선택: {doc}의 {section}번 부분 시험.|S05
jobs.selected.context|시작 당시 조건|S05
jobs.selected.key|AI가 만든 정답 ·|S05
jobs.selected.prompt|수정 설명|S05
jobs.selected.no_warning|설정 경고는 없습니다.|E09,S05
jobs.selected.path|기록 위치:|S05,S06
jobs.selected.restore|상세를 닫아도 선택 행과 읽던 위치는 유지합니다.|S05
jobs.selected.legacy|오래된 작업과 알 수 없는 상태|S05
jobs.selected.open_missing_target|기록 당시 대상이 없는 작업 보기|S05
jobs.selected.open_unknown|끝을 알 수 없는 작업 보기|S05
jobs.external.title|이 작업은 다른 터미널에서 시작했습니다.|S05
jobs.external.record|현재 기록|S05
jobs.external.process|문서를 처리하는 프로그램|S05
jobs.external.running|실행 중|S05
jobs.external.unknown|확인 안 됨|P01,S05
jobs.external.unstoppable|이 화면에서는 중단할 수 없음|S05
jobs.external.no_docs|이 작업에는 처리한 문서가 기록되지 않았습니다.|S05
jobs.external.no_journey_success|이 작업은 첫 시험 성공 기록에 넣지 않습니다.|S05
jobs.external.back|작업 목록으로 돌아가기|S05
jobs.legacy.title|이 작업의 시작 당시 기준을 확인할 수 없습니다.|S05
jobs.legacy.no_target|기존 작업에는 대상 기록이 없습니다.|S05
jobs.legacy.available|보관된 로그와 종료 코드는 볼 수 있습니다.|S05
jobs.legacy.log|기록 원문|S05
jobs.legacy.exit_code|종료 코드: {count}.|E09,S05
jobs.batch.title|여러 문서를 같은 조건으로 실행하세요.|S09
jobs.batch.ready|{model}가 준비되어 있습니다.|S09
jobs.batch.select_docs|문서 고르기|S09
jobs.batch.select_all|개발용 문서 {count}건 모두 고르기|S09
jobs.batch.eval_locked|평가용 {count}건 · 최종 성능 평가를 위해 잠김|S09
jobs.batch.outside_locked|목록 밖 예시 문서 · 현재 실행기가 본 실행을 지원하지 않음|S09
jobs.batch.repeats|같은 문서를 처리할 횟수|S09
jobs.batch.summary|선택 {count}건. 반복 {repeats}회. 이전 개발 자료를 사용합니다.|S09
jobs.batch.key|비교할 정답은 AI가 먼저 만든 정답입니다.|S09
jobs.batch.start|선택한 문서 시험 시작하기|S09
jobs.batch.details|실행 전 조건과 이름 규칙|S09
jobs.batch.kind|실행 종류는 서버가 분류한 값을 사용합니다.|S09
jobs.batch.exclude_eval|개발용 전체 선택에는 평가용 문서를 포함하지 않습니다.|S09
jobs.batch.repeat_range|반복은 1~10회입니다.|S09
jobs.batch.suffix_intro|두 번째 결과 이름 끝에는|S09
jobs.batch.suffix|_r2|S09
jobs.batch.suffix_end|가 붙습니다.|S09
jobs.batch.base_auto|비교할 이전 결과은 선택한 범위에 맞춰 자동으로 찾습니다.|S09
jobs.batch.keep_awake|실행 중에는 컴퓨터가 잠들지 않도록 유지합니다.|S09
jobs.batch.confirm|서버가 추가 확인을 요구하면 확인 후 시작합니다.|S09
jobs.batch.open_confirm|서버 확인이 필요한 경우 보기|S09
jobs.batch.runnable|문서별 실행 가능 여부|S09
jobs.batch.outside_policy|목록 밖 문서는 서버가 허용한 경우에만 실행합니다.|S09
jobs.batch.no_name_inference|문서 이름으로 허용 여부를 판단하지 않습니다.|S09
jobs.batch.open_outside|목록 밖 문서 실행 가능 상태 보기|S09
jobs.outside.title|이 문서는 여러 문서 시험에 넣을 수 있습니다.|S09
jobs.outside.server_state|서버가 알려 준 상태|S09
jobs.outside.single_forbidden|불가. 문서 목록에 등록되지 않음.|S09
jobs.outside.batch_allowed|가능. 실행기가 문서 정보를 읽을 수 있음.|S09
jobs.outside.no_score|정답이 없어 점수는 계산하지 않습니다.|S09
jobs.outside.back|여러 문서 선택으로 돌아가기|S09
jobs.batch_running.title|개발용 문서 {count}건을 실행하고 있습니다.|S09
jobs.batch_running.round|{total}회 중 {round}회 진행 중|S09
jobs.batch_running.run_name|실행 이름은 {run}입니다.|S09
jobs.batch_running.context|시작 당시 문서 묶음과 모델을 계속 사용합니다.|S09
jobs.trial.rented_ready|{model}가 응답했습니다. 빌린 서버를 사용합니다.|S03
jobs.trial.rented_cost|시간당 약 ${cost_per_hour}의 실제 요금이 나갑니다(예시).|S03
jobs.batch_running.rented|빌린 서버에서 개발용 문서 {count}건을 실행하고 있습니다.|S09
jobs.multiple_running.title|{section}번과 {other_section}번 부분을 시험하고 있습니다.|S03
jobs.multiple_running.sent|선택한 두 부분을 보냈습니다.|S03
jobs.multiple_running.progress|{doc}의 한 부분씩 결과를 확인합니다.|S03
jobs.multiple.default_prompt|여러 부분은 각 부분의 기본 설명을 사용합니다.|S03
jobs.form.focus_line|원문 줄: {page}쪽 {line_no}번째 줄|S03 고른 값
jobs.form.focus_estimated|원문 줄(추정): {page}쪽 {line_no}번째 줄|S03 고른 값

### journey — S08 두 갈래 안내

키|글|쓰는 곳
---|---|---
journey.record.errors.unavailable.message|첫 사용 기록의 저장 위치가 설정되지 않았습니다.|S08
journey.record.errors.unavailable.fix|할 일: 앱을 켠 터미널에서 python scripts/b_app.py로 다시 시작하세요.|S08
journey.record.errors.read_failed.message|기록 파일을 열지 못했습니다.|S08
journey.record.errors.read_failed.fix|할 일: runs/manual/journey.json 파일을 읽을 수 있는지 확인하세요.|S08
journey.record.errors.save_failed.message|기록을 저장하지 못했습니다.|S08
journey.record.errors.save_failed.fix|할 일: runs/manual 폴더에 파일을 쓸 수 있는지 확인하세요.|S08
journey.record.errors.too_big.message|보낸 기록이 16KB를 넘습니다.|S08
journey.record.errors.too_big.fix|할 일: 기록에는 진행 단계와 횟수와 시각과 작업 번호만 보내세요.|S08
journey.record.errors.bad_body.fix|할 일: 화면을 새로 고친 뒤 안내를 다시 여세요.|S08
journey.record.invalid.body|안내 기록의 형식이 맞지 않습니다. journey 칸 하나가 필요합니다.|S08
journey.record.invalid.unknown_key|사용할 수 없는 기록 칸입니다: {where}.|S08
journey.record.invalid.missing_key|기록에 필요한 칸이 빠졌습니다: {where}.|S08
journey.record.invalid.version|안내 기록의 형식 번호가 2가 아닙니다.|S08
journey.record.invalid.bad_value|{where} 칸의 값이 맞지 않습니다. 필요한 값: {expect}.|S08
journey.record.expect.object|이름과 값을 묶은 기록(JSON 객체)|S08
journey.record.expect.object_or_null|이름과 값을 묶은 기록 또는 비어 있음(null)|S08
journey.record.expect.time|화면에서 기록한 시각(예: 2026-10-31T00:58:00.000Z)|S08
journey.record.expect.time_or_null|화면에서 기록한 시각 또는 비어 있음(null)|S08
journey.record.expect.count|1 이상의 정수|S08
journey.record.expect.step|0부터 {top}까지의 정수|S08
journey.record.expect.state|시작 전(not_started), 진행 중(in_progress), 건너뜀(skipped), 완료(completed) 중 하나|S08
journey.record.expect.active|갈래 1(t1), 갈래 2(t2), 선택 없음(null) 중 하나|S08
journey.record.expect.mode|실제 시험(real) 또는 연습(practice)|S08
journey.record.expect.id|영문과 숫자 및 _와 -만 사용한 64자 이하 이름|S08
journey.record.expect.id_or_null|영문과 숫자 및 _와 -만 사용한 64자 이하 이름 또는 비어 있음(null)|S08
journey.record.expect.migrated_from|1 또는 비어 있음(null)|S08
journey.record.parts.file_json|안내 기록 파일을 읽을 수 있는 형식이 아닙니다.|S08
journey.record.parts.file_version|안내 기록 파일의 형식 번호가 2가 아닙니다.|S08
journey.record.parts.progress|안내 진행 기록을 읽지 못했습니다.|S08
journey.record.parts.outcomes|실제 성공과 연습 기록을 읽지 못했습니다.|S08
journey.record.parts.pending|결과 확인을 기다리는 시험 기록을 읽지 못했습니다.|S08
journey.record.parts.migrated_from|옛 기록을 옮겼는지 확인하지 못했습니다.|S08
journey.start.intro|저장된 점수에서 문제 값을 찾고 원문과 맞춰 봅니다.|S08
journey.start.first|먼저 저장된 결과로 시작하세요. AI를 켜지 않아도 됩니다.|S08
journey.start.step_one|최근 점수와 목표를 읽으세요.|S08
journey.start.step_two|가장 큰 문제의 원문을 여세요.|S08
journey.start.step_three|문제 값과 선택된 원문 줄을 맞춰 보세요.|S08
journey.start.empty|저장된 결과가 없어 결과 읽기 안내를 시작할 수 없습니다. 할 일: 한 부분 시험을 준비하세요.|S08
journey.start.unscored|점수가 있는 결과가 없습니다. 할 일: 결과 목록에서 상태를 확인하세요.|S08
journey.start.no_problem|열어 볼 문제 값이 없어 안내를 마칠 수 없습니다. 할 일: 기준별 점수를 보거나 안내를 건너뛰세요.|S08
journey.start.no_line|이 값의 원문 줄을 찾지 못했습니다. 할 일: 해당 부분의 원문을 직접 읽으세요.|S08
journey.start.resume|안내를 이어가려면 최근 결과에서 문제를 다시 고르세요.|S08
journey.start.success|문제 값과 실제 원문 줄을 함께 확인했습니다.|S08
journey.start.later|다음에 할 수 있는 일|S08
journey.start.done|안내 완료|S08
journey.start.current|현재 단계|S08
journey.start.skipped|건너뜀|S08
journey.start.dismiss|안내 닫기|S08
journey.start.replay|처음부터 다시 보기|S08
journey.start.loading|저장된 결과 목록을 읽고 있습니다.|S08
journey.choice.title|먼저 끝내고 싶은 일을 고르세요.|S08
journey.choice.read_title|1. 저장된 점수와 원문 읽기 · 추천|S08
journey.choice.read_action|저장된 점수에서 가장 큰 문제를 엽니다.|S08
journey.choice.read_success|문제 값과 실제 원문 줄을 함께 확인하면 끝납니다.|S08
journey.choice.read_ready|저장된 결과가 있어 바로 시작할 수 있습니다.|S08
journey.choice.start_read|저장된 결과로 시작하기|S08
journey.choice.trial_title|2. 한 부분을 실제로 시험하기|S08
journey.choice.trial_action|개발용 문서의 한 부분을 모델에 보냅니다.|S08
journey.choice.trial_success|AI가 뽑은 값을 읽는 데 성공한 결과를 열면 끝납니다.|S08
journey.choice.trial_requires_model|실제 시험에는 AI를 먼저 켜야 합니다.|S08
journey.choice.start_trial|한 부분 시험 준비하기|S08
journey.choice.practice|AI 없이 보낼 내용만 확인하는 연습도 할 수 있습니다.|S08
journey.history.title|안내 기록 · 실제 성공과 연습은 별도|S08
journey.history.real_success|실제로 해냄|S08
journey.history.read_track|1. 점수와 원문|S08
journey.history.none|아직 없음|S08
journey.history.trial_track|2. 한 부분 시험|S08
journey.history.first_count|{time} 처음. 모두 {count}회.|S08
journey.history.replay_progress|다시 보기는 진행 단계만 처음으로 돌립니다.|S08
journey.history.keep_outcomes|실제 성공 시각과 연습 횟수는 지우지 않습니다.|S08
journey.choice.skip|안내 건너뛰고 최근 결과 보기|S08
journey.history.details|기록과 중단 상태 보기|S08
journey.history.resume|중간부터 이어하기|S08
journey.history.open_save_failure|기록 저장 실패 보기|S08
journey.history.open_pending|지난 시험 이어 보기|S08
journey.replay.start|안내 다시 시작하기|S08
journey.replay.keep_job|진행 중인 시험은 멈추지 않습니다. 결과는 작업 기록에서 봅니다.|S08
journey.read.track|갈래 {track} 안내|S08
journey.read.instruction|최근 점수와 목표 점수을 읽으세요.|S08
journey.read.two_targets|전체 점수의 목표와 필수 기준의 목표는 따로 봅니다.|S08
journey.read.next_problem|다음: 가장 큰 문제 보기|S08
journey.problem.loss|{section}번 부분에서 전체 점수 {loss}점이 깎였습니다.|S08
journey.problem.evidence|틀린 값은 AI가 적은 근거 줄이 있어 바로 맞춰 볼 수 있습니다.|S08
journey.problem.unavailable|열어 볼 수 없는 경우|S08
journey.problem.none|문제 없음|S08
journey.problem.unlinked|문서나 부분 연결 없음|S08
journey.read.completed|갈래 1을 마쳤습니다. 성공 기록은 안내를 다시 봐도 남습니다.|S08
journey.unlinked.title|이 문제의 원문 줄로 바로 이어 드릴 수 없습니다.|S08
journey.unlinked.stay|안내는 이 단계에 머뭅니다.|S08
journey.unlinked.reason|문서나 부분을 확인할 연결 정보가 없습니다.|S08
journey.unlinked.open_items|항목별 문제 보기|S08
journey.unlinked.manual|직접 확인하기|S08
journey.unlinked.open_doc|문서 원문 읽기|S08
journey.unlinked.skip|갈래 건너뛰기|S08
journey.trial.select_instruction|시험할 문서와 부분을 고르세요.|S08
journey.trial.select_title|한 문서의 한 부분을 시험합니다.|S08
journey.trial.eval_locked|평가용 {count}건 · 개발 중 사용 금지|S08
journey.trial.section_label|시험할 부분|S08
journey.trial.section|{section}번 부분 · 노출기준|S08
journey.trial.prefilled|갈래 1에서 본 문서와 부분을 채웠습니다.|S08
journey.trial.single_only|이 안내에서는 부분을 하나만 고릅니다.|S08
journey.trial.next_model|다음: AI 준비 확인하기|S08
journey.trial.model_instruction|실제 시험에 쓸 모델을 준비하세요.|S08
journey.trial.model_title|실제 시험에는 켜진 AI 모델이 필요합니다.|S08
journey.trial.saved_target|{doc}의 {section}번 부분을 보관했습니다.|S08
journey.trial.already_ready|이미 모델이 켜져 있을 때|S08
journey.trial.fresh_reply|단계에 들어온 뒤 받은 모델 응답으로 확인합니다.|S08
journey.trial.continue_ready|준비된 모델로 계속하기|S08
journey.trial.send_instruction|대상과 설명을 읽고 실제 시험을 보내세요.|S08
journey.trial.waiting|보낸 시험의 결과를 기다리고 있습니다.|S08
journey.trial.opened_result|실제 시험의 결과를 열었습니다.|S08
journey.trial.completed|갈래 2를 마쳤습니다. 실제 성공 기록이 남습니다.|S08
journey.trial.parse_failed|작업은 끝났지만 값을 읽지 못했습니다.|S08
journey.trial.practice_stay|갈래 2는 모델 준비 확인 단계에 머뭅니다.|S08
journey.skipped.title|첫 사용 안내를 건너뛰었습니다.|S08
journey.skipped.restart|처음 사용 안내에서 언제든 다시 시작할 수 있습니다.|S08
journey.skipped.keep_job|이미 보낸 시험은 멈추지 않습니다.|S08
journey.skipped.keep_outcomes|실제 성공 기록과 연습 기록은 그대로입니다.|S08
journey.skipped.open_recent|최근 결과 보기|S08
journey.resume.title|갈래 2의 모델 준비 확인을 이어갑니다.|S08
journey.resume.practice_only|AI 없이 입력 확인 연습은 {count}회 마쳤습니다. 실제 성공은 아직 없습니다.|S08
journey.resume.target_missing|새로 열어 대상이 없을 때|S08
journey.resume.memory_target|고른 문서와 부분은 이 화면 메모리에 보관합니다.|S08
journey.resume.reselect|새로 열어 대상이 사라졌다면 다시 고릅니다.|S08
journey.resume.select_target|시험 대상 다시 고르기|S08
journey.pending.title|지난번에 보낸 시험이 끝났습니다.|S08
journey.pending.checked|보관한 작업 번호로 작업 기록을 확인했습니다.|S08
journey.pending.open_result|결과 보기|S08
journey.pending.missing|기록을 찾지 못한 경우|S08
journey.pending.not_found|지난번 시험 기록을 찾지 못했습니다.|S08
journey.pending.todo|할 일: 작업 기록을 확인하세요. 자동으로 다시 보내지 않습니다.|S08
journey.save_failed.title|첫 사용 기록을 저장하지 못했습니다.|S08
journey.save_failed.continue|안내와 시험은 계속할 수 있습니다.|S08
journey.save_failed.todo|할 일: 앱을 켠 터미널이 열려 있는지 보세요. 다음 단계에서 다시 저장합니다.|S08
journey.save_failed.action|안내 계속하기|S08
journey.save_failed.notify_once|저장 실패 알림은 한 번만 보입니다.|S08
journey.save_failed.memory|이 탭의 메모리에서 진행을 이어갑니다.|S08
journey.partial_record.title|안내 기록 일부를 읽지 못했습니다.|S08
journey.partial_record.reset_progress|진행 상태만 처음으로 돌렸습니다.|S08
journey.partial_record.keep_outcomes|실제 성공 기록과 연습 기록은 남아 있습니다.|S08
journey.target_missing.title|안내할 자리를 찾지 못했습니다.|S08
journey.target_missing.stopped|이 단계에서 멈췄습니다.|S08
journey.target_missing.todo|메뉴는 사용할 수 있습니다. 할 일: 안내로 돌아가 다시 시작하세요.|S08
journey.target_missing.back|안내로 돌아가기|S08
journey.detached.title|보낸 시험을 안내에서 분리했습니다.|S08
journey.detached.keep_job|시험 대상이 바뀌었습니다. 진행 중인 작업은 멈추지 않습니다.|S08
journey.detached.no_progress|분리된 결과는 현재 안내 단계를 올리지 않습니다.|S08
journey.detached.real_success|실제 시험이 성공한 뒤 결과를 열면 실제 사용 기록에는 남습니다.|S08
journey.detached.open_job|보낸 작업 보기|S08
journey.track|해 볼 일|S08
journey.practice|연습|S08
journey.resume.action|이어하기|S08
journey.skip|건너뛰기|S08
journey.trial.parse_todo|할 일: 자세히 보기의 ‘읽어 낸 값’에서 오류를 확인하고 같은 조건으로 다시 시험하세요.|안내 띠
journey.tracks.t1.steps.1|최근 점수와 목표를 읽으세요.|안내 띠
journey.tracks.t1.steps.2|가장 큰 문제의 원문을 여세요.|안내 띠
journey.tracks.t1.steps.3|문제 값과 선택된 원문 줄을 맞춰 보세요.|안내 띠
journey.tracks.t2.steps.1|① 무엇을: 시험할 문서와 부분을 고르세요.|안내 띠
journey.tracks.t2.steps.2|② 어느 AI로: 실제 시험에 쓸 모델을 준비하세요.|안내 띠
journey.tracks.t2.steps.3|③ 무엇을 시킬지: 대상과 설명을 읽고 실제 시험을 보내세요.|안내 띠
journey.tracks.t2.steps.4|⑤ 결과: 실제 시험의 결과를 열었습니다.|안내 띠

### help — S07 도움말

키|글|쓰는 곳
---|---|---
help.settings.runpod_url_pattern|빌린 서버의 중계 주소 형식: https://{pod_id}-8000.proxy.runpod.net/v1|S07
help.settings.runpod_url_fact|RUNPOD_VLLM_BASE_URL은 빌린 서버의 중계 주소입니다. SSH 연결 주소가 아닙니다.|S07
help.settings.company_url_pattern|회사 서버 연결 주소 형식: http://127.0.0.1:{port}/v1|S07
help.settings.certificates|인증서 설치 파일: /Applications/Python 3.11/Install Certificates.command|S07
help.title|하려는 일에 맞는 설명을 펼치세요.|S07
help.replay_read|결과 읽기 안내 다시 보기|S07
help.return_trial|다시 시험으로 돌아가기|S07
help.flow.title|앱과 처리 순서|S07
help.flow.purpose|AI는 안전 문서의 내용을 정해진 칸으로 옮깁니다.|S07
help.flow.pdf|PDF에서 쪽별 글자를 읽습니다.|S07
help.flow.sections|문서를 16개 부분으로 나눕니다.|S07
help.flow.extract|AI가 필요한 값을 뽑습니다.|S07
help.flow.save|정해진 결과 형식(JSON)으로 저장합니다.|S07
help.flow.score|답안과 비교해 점수를 매깁니다.|S07
help.flow.audience|이 화면은 그 결과를 검토하는 사람을 위한 도구입니다.|S07
help.score.title|점수와 비교 읽기|S07
help.score.weight|중요한 항목에는 더 큰 비중을 줍니다.|S07
help.score.target|전체 목표 점수은 90점입니다.|S07
help.score.must|필수 17개 항목의 목표 달성 수는 따로 확인합니다.|S07
help.score.draft|정답도 틀릴 수 있습니다.|S07
help.score.cause|2점 이상 하락한 항목의 원인 후보는 추정입니다.|S07
help.score.open_methods|23개 기준의 측정 방법 보기|S07
help.source.title|원문으로 확인하기|S07
help.source.compare|AI가 채운 값과 같은 위치의 원문 줄을 비교합니다.|S07
help.source.example|예: 2쪽 23번째 줄에는 5 mg/m³가 적혀 있습니다.|S07
help.source.no_fallback|근거가 없으면 임의의 줄을 대신 선택하지 않습니다.|S07
help.source.open|선택한 값과 원문 보기|S07
help.setup.title|처음 준비하기|S07
help.setup.read_offline|저장 결과를 읽는 데는 서버 설정이 필요 없습니다.|S07
help.setup.file_intro|실제 시험에 쓸 설정은 프로젝트의|S07
help.setup.filename|.env|S07
help.setup.file_end|파일에서 준비합니다.|S07
help.setup.names_only|아래는 설정 이름뿐입니다.|S07
help.setup.name_column|설정 이름|S07
help.setup.meaning_column|뜻|S07
help.settings.runpod_url_name|RUNPOD_VLLM_BASE_URL|S07
help.settings.runpod_url_meaning|빌린 서버의 중계 주소(RunPod 프록시). SSH 연결 주소가 아닙니다.|S07
help.settings.runpod_key_meaning|빌린 서버의 모델 접속 키|S07
help.settings.company_url_meaning|회사 모델에 요청을 보내는 내 컴퓨터 쪽 주소|S07
help.settings.company_key_name|RNGD_API_KEY|S07
help.settings.company_key_meaning|회사 모델의 접속 키|S07
help.settings.management_key_name|RUNPOD_API_KEY|S07
help.settings.management_key_meaning|빌린 서버를 만들고 삭제할 때 쓰는 관리 키|S07
help.settings.ssh_name|RNGD_SSH|S07
help.settings.ssh_meaning|회사 서버에 접속하는 보안 연결(SSH) 설정|S07
help.setup.template_intro|양식 파일은|S07
help.setup.template_name|.env.example|S07
help.setup.template_end|입니다.|S07
help.setup.no_secrets|비밀값은 화면이나 기록에 넣지 않습니다.|S07
help.setup.command_label|앱 시작 명령:|S07
help.trial.title|한 부분 시험하기|S07
help.trial.meaning|문서의 같은 부분을 다시 보내 수정 효과를 확인합니다.|S07
help.trial.open_stages|입력부터 결과까지 6단계 보기|S07
help.cli.title|터미널 명령과 옵션|S07
help.cli.help_label|명령 도움말:|S07
help.cli.help_command|try_section.py --help|S07
help.cli.option_column|옵션|S07
help.cli.section_flag|--section|S07
help.cli.section_meaning|시험할 문서 부분|S07
help.cli.all_flag|--all|S07
help.cli.all_meaning|문서 전체 16개 부분|S07
help.cli.dry_run_flag|--dry-run|S07
help.cli.dry_run_meaning|AI 호출 없이 입력 확인|S07
help.cli.system_file_flag|--system-file|S07
help.cli.system_file_meaning|기본 설명 대신 보낼 파일|S07
help.cli.base_run_flag|--base-run|S07
help.cli.base_run_meaning|전후 비교의 기준 결과|S07
help.cli.show_prompt_flag|--show-prompt|S07
help.cli.show_prompt_meaning|설명 전문을 화면에 표시|S07
help.cli.json_flag|--json|S07
help.cli.json_meaning|결과를 구조화된 형식으로 출력|S07
help.prompt.title|AI에게 시킬 일 바꾸기|S07
help.prompt.code_default|기본 설명은 코드의 기본값에서 가져옵니다.|S07
help.prompt.model_default|모델별 설정에 있는 설명이 기본값을 덮을 수 있습니다.|S07
help.prompt.trial_override|시험 화면에서 고친 설명을 그 시험에만 사용할 수 있습니다.|S07
help.prompt.persist|영구 반영은 해당 모델의 설명 파일을 수정하고 버전을 올립니다.|S07
help.prompt.memory|임시 전문은 화면 메모리에만 남깁니다.|S07
help.prompt.hash|기록에는 확인값만 남겨 다음 반복과 비교합니다.|S07
help.servers.title|AI 연결과 비용 관리|S07
help.servers.cost|빌린 서버는 켜진 시간에 따라 비용이 듭니다.|S07
help.servers.company|회사 서버는 연결 통로와 AI 준비를 따로 확인합니다.|S07
help.servers.manual_record|서버 기록은 운영용 수동 기록에도 옮겨 둡니다.|S07
help.servers.open_rented|빌린 서버 관리하기|S07
help.servers.open_company|회사 서버 관리하기|S07
help.recovery.title|막혔을 때 복구하기|S07
help.recovery.length|답이 너무 길면 출력 길이 제한에 도달할 수 있습니다.|S07
help.recovery.whitespace|공백을 계속 생성해도 출력 길이 제한에 도달할 수 있습니다.|S07
help.recovery.repetition|같은 내용을 반복해도 출력 길이 제한에 도달할 수 있습니다.|S07
help.recovery.columns|표의 열 수가 맞지 않으면 AI에게 시킬 일의 답변 형식을 검토합니다.|S07
help.recovery.slow|처리가 300초를 넘으면 느린 항목의 요청 기록을 봅니다.|S07
help.recovery.connection|연결 오류는 장비의 응답 상태부터 확인합니다.|S07
help.recovery.open_states|상태별 복구 방법 보기|S07
help.protection.title|자료 보호와 용어|S07
help.protection.eval_locked|평가용 10건은 개발 과정에서 열거나 시험하지 않습니다.|S07
help.protection.private_data|문서 원문과 회사 자료는 밖으로 공유하지 않습니다.|S07
help.protection.keys|접속 키는 설정 파일에만 둡니다.|S07
help.protection.delete_rented|빌린 서버는 사용 뒤 삭제합니다.|S07
help.protection.no_eval|개발 중에는 평가용 문서를 사용하지 않습니다.|S07
help.protection.tests|자동 검사에서는 원문 자료를 덮어쓰는 전처리 시험을 제외합니다.|S07
help.protection.command_label|검사 명령:|S07
help.protection.harness_intro|자동 실행기(하네스)가 동작 중일 때는 보호된|S07
help.protection.docs_path|docs/|S07
help.protection.harness_end|파일을 고치지 않습니다.|S07
help.terms.distinction|문서 부분(항)과 점수 기준은 서로 다릅니다.|S07
help.terms.section_count|문서 부분은 16개입니다.|S07
help.terms.criterion_count|점수 기준은 23개입니다.|S07
help.terms.load_failed|용어를 불러오지 못하면 ‘설명을 읽지 못했습니다’와 다시 읽기를 제공합니다.|S07
help.terms.open_score|전체 점수 용어 보기|S07
help.terms.title|화면에서 쓰는 말 47개|S07
help.terms.columns|쉬운 설명과 원래 용어|S07
help.journey.title|첫 사용 기록과 재시작|S07
help.journey.storage|안내 기록은 프로젝트 파일에 보관합니다.|S07
help.journey.replay|다시 보기는 진행만 처음으로 돌립니다.|S07
help.journey.open|처음 사용 안내 다시 보기|S07
help.terms.failure|설명을 읽지 못한 상태|S07
help.terms.open_failure|용어를 읽지 못한 상태 보기|S07
help.failed.title|용어 설명을 읽지 못했습니다.|S07
help.failed.scope|설명만 확인할 수 없습니다.|S07
help.failed.todo|다른 기능은 사용할 수 있습니다. 할 일: 용어 설명만 다시 읽으세요.|S07
help.failed.reload|설명 다시 읽기|S07
help.data.source_meaning|원문 자료(문서 묶음)는 PDF를 쪽마다 글자와 그림으로 바꿔 둔 파일입니다. AI는 이 글자를 읽고, 근거도 이 글자의 줄 번호로 댑니다.|S07
help.data.source_example|예: p5:L22는 5쪽 22번째 줄입니다.|S07
help.data.source_change|바꾸기: 위쪽 막대의 ‘문서 묶음’을 눌러 다른 묶음을 고릅니다. 그 묶음으로 돌린 저장 결과만 보입니다.|S07
help.data.source_receive|받은 폴더는 화면 위쪽의 새 자료 받기에서 가져옵니다. 앱이 줄 번호와 열지 않을 문서를 검사하고 복사까지 합니다. 점수가 나오는 폴더인지도 알려 줍니다.|S07
help.data.source_add_title|직접 폴더를 만들어 더하는 순서입니다.|S07
help.data.source_add1|data/pages/<묶음 이름>/<문서 번호>/ 폴더를 만듭니다.|S07
help.data.source_add2|쪽마다 p001.txt(글자)와 p001.png(그림)를 넣습니다. 글자 줄 앞에 L001 같은 줄 번호가 있어야 새 시험에 쓸 수 있습니다.|S07
help.data.source_add3|data/manifest.csv에 없는 문서 번호라면 meta.json도 넣습니다. 안의 doc_id가 폴더 이름과 같아야 열립니다.|S07
help.data.source_add4|화면을 새로고침하면 목록에 나타납니다. 앱을 다시 켤 필요는 없습니다.|S07
help.data.source_caution|평가용 문서는 점수가 부풀려지지 않도록 개발 중에는 열지 않습니다. 목록에 잠김으로 보입니다. data/pages는 git에 올리지 않습니다.|S07
help.data.answer_meaning|정답은 AI 값과 견주는 기준입니다. 점수는 AI가 뽑은 값이 정답과 얼마나 같은지로 계산합니다. 정답을 바꾸면 같은 결과의 점수도 달라집니다.|S07
help.data.answer_gold|사람이 확인한 정답(골드)은 사람이 검토해 확정한 답입니다. data/gold에 있습니다.|S07
help.data.answer_silver|AI 정답 초안(실버)은 AI가 먼저 만든 비교용 답입니다. data/silver 아래 폴더에 있고, 틀릴 수 있습니다.|S07
help.data.answer_change|바꾸기: 위쪽 막대의 ‘정답’을 눌러 고릅니다. 저장된 결과를 AI 없이 다시 채점합니다.|S07
help.data.answer_receive|담당이 올린 새 정답은 화면 위쪽의 새 자료 받기에서 확인합니다. 받는 명령을 알려 주고, 받은 뒤에는 바뀐 문서 수를 보여 줍니다.|S07
help.data.answer_add_title|정답 폴더를 직접 더하는 순서입니다.|S07
help.data.answer_add1|data/silver/<이름>/ 또는 data/gold/<이름>/ 폴더를 만듭니다.|S07
help.data.answer_add2|문서마다 <문서 번호>.json을 넣습니다. 예: T21-S001.json. 정해진 결과 형식(TO21 JSON)이어야 합니다.|S07
help.data.answer_add3|화면을 새로고침하면 목록에 나타납니다. 앱을 다시 켤 필요는 없습니다.|S07
help.data.answer_caution|골드는 A 담당이 검수해 올립니다. 고칠 곳을 찾으면 파일을 직접 바꾸지 말고 A 담당에게 알립니다. 평가용 문서의 정답은 열지 않고 개수만 셉니다.|S07
help.guide.data.title|원문 자료와 정답은 무엇이고 어떻게 바꾸나요?|S07
help.guide.data.summary|AI가 읽는 글과 점수 기준의 뜻, 바꾸고 새로 더하는 순서를 설명합니다.|S07
help.guide.flow.title|앱은 어떤 일을 하나요?|S07
help.guide.flow.summary|문서에서 값을 뽑아 저장하고 정답과 비교하는 순서를 설명합니다.|S07
help.guide.score.title|점수와 문제 건수는 어떻게 읽나요?|S07
help.guide.score.summary|두 목표와 정답의 신뢰 범위를 구분합니다.|S07
help.guide.source.title|문제 값을 원문에서 어떻게 확인하나요?|S07
help.guide.source.summary|실제 근거 줄과 추정 줄을 구분해 읽습니다.|S07
help.guide.setup.title|실제 시험 전에 무엇을 준비하나요?|S07
help.guide.setup.summary|저장 결과 읽기와 모델 접속 설정을 구분합니다.|S07
help.guide.retest.title|한 부분을 어떻게 다시 시험하나요?|S07
help.guide.retest.summary|AI 없이 확인하는 연습과 실제 시험을 구분합니다.|S07
help.guide.prompt.title|AI에게 시킬 일은 어떻게 고치나요?|S07
help.guide.prompt.summary|원문에서 확인한 오류를 한 가지 규칙으로 바꿉니다.|S07
help.guide.servers.title|어느 서버를 고르고 언제 끄나요?|S07
help.guide.servers.summary|추가 임대료와 준비 시간과 삭제 시점을 확인합니다.|S07
help.guide.recovery.title|오류가 나면 어디서 다시 시작하나요?|S07
help.guide.recovery.summary|화면의 사실과 할 일을 읽고 같은 대상에서 이어갑니다.|S07
help.guide.protection.title|어떤 문서와 정보를 보호하나요?|S07
help.guide.protection.summary|평가용 문서 잠금과 접속 키 보관 원칙을 확인합니다.|S07
help.setup.command|(cd backend && .venv/bin/python scripts/b_app.py)|S07
help.protection.command|(cd backend && .venv/bin/python -m pytest -q --ignore=tests/test_preprocess.py)|S07
help.source.step_choose|① 문제 고르기: 점수를 많이 깎은 항목부터 고릅니다.|S07 원문 장
help.source.step_compare|② 원문과 맞춰 보기: 왼쪽에서 행을 고르고, 그 행의 칸을 근거 줄과 함께 봅니다.|S07 원문 장
help.source.step_send|③ 다시 시험으로 보내기: 문서와 부분을 다시 시험으로 넘깁니다. 시험은 여기서 시작하지 않습니다.|S07 원문 장
help.source.image_text|원문 그림은 쪽 안의 위치를 확인하는 곳입니다. 글자는 원문 글자 칸에서 읽습니다.|S07 원문 장
help.source.kinds|틀림은 같은 칸의 값이 정답과 다른 경우입니다. 만듦은 AI 결과에는 있는데 정답에는 없는 값입니다. 못 뽑음은 정답에는 있는데 AI 결과에는 없는 값입니다.|S07 원문 장
help.source.details|원래 값과 위치, 비교 범위, 문서 전체 표, 추정 방법은 자세히 보기에 있습니다.|S07 원문 장
help.servers.step_choose|① 서버 고르기: 고른 AI를 켤 수 있는 서버에 표시가 붙습니다.|S07 서버 장
help.servers.step_start|② 켜기: 요금과 자동 삭제를 확인 창에서 본 뒤 정합니다. 확인 창에서 실행해야 요청이 나갑니다.|S07 서버 장
help.servers.step_wait|③ 준비 기다리기: 앱이 확인한 상태까지만 보입니다. 화면을 떠나도 준비는 계속됩니다.|S07 서버 장
help.servers.step_stop|④ 쓰고 나서 끄기: 요금과 켜진 시간을 본 뒤 시험으로 돌아가거나 서버를 끕니다.|S07 서버 장
help.servers.order|시험으로 돌아가기는 서버를 끄지 않습니다. 순서는 시험으로 돌아가기, 결과 확인, 이 화면으로 다시 와서 끄기입니다. 끄지 않으면 요금이 계속 나갑니다.|S07 서버 장
help.facts.source_colors|같음과 틀림과 만듦과 못 뽑음은 글로 구분합니다. 지금 고른 값과 줄은 노란 바탕으로 표시합니다.|S07
help.facts.setup_reload|설정을 고친 뒤 AI 켜기와 비용의 자세히 보기에서 설정 다시 읽기를 누르세요.|S07
help.facts.trial_scope|① 무엇을: 한 부분, 문서 전체, 여러 문서 중에서 고르고 개발용 문서와 부분을 정합니다.|S07 다시 시험 장
help.facts.trial_ready|② 어느 AI로: 모델을 고르고 응답을 확인합니다. 꺼져 있으면 AI 켜기와 비용에서 켠 뒤 돌아옵니다.|S07 다시 시험 장
help.facts.trial_send|③ 무엇을 시킬지: 기본 지시문을 그대로 쓰거나 고친 뒤 실제 시험을 시작합니다.|S07 다시 시험 장
help.facts.trial_running|④ 시험: AI의 답을 기다립니다. 다른 화면으로 가도 시험은 계속되고, 끝나면 결과로 넘어갑니다.|S07 다시 시험 장
help.facts.trial_result|⑤ 결과: 전후 점수와 고른 값의 변화를 봅니다. 서버가 켜져 있으면 요금도 함께 보입니다.|S07 다시 시험 장
help.facts.trial_records|아래 기록 중 시험 전후 점수는 ⑤ 결과에 있고, 나머지 다섯 가지는 자세히 보기에 있습니다.|S07 다시 시험 장
help.facts.trial_many|여러 문서는 ① 무엇을에서 ‘여러 문서’를 고릅니다. 개발용 문서와 반복 횟수를 정합니다. 두 결과 비교에서는 여러 결과의 비교표도 만들 수 있습니다.|S07 다시 시험 장
help.facts.columns|시험 결과의 자세히 보기에서 ‘읽어 낸 값’의 버린 줄 수를 봅니다. 모델의 원래 답과 정해진 열 수를 비교하세요.|S07

### steps — 단계 진행의 공통 틀

위쪽 막대 한 줄, 화면 위 단계 표시, 맨 아래 행동 줄, 자세히 서랍의 글입니다. 최종 문구는 G6에서 검토합니다.

키|글|쓰는 곳
---|---|---
steps.a11y|이 화면의 단계|단계 표시
steps.actions_a11y|이 단계의 행동|행동 줄
steps.current|지금 단계|단계 표시
steps.details.close|자세히 닫기|서랍
common.raw_error_title|오류 기록|서랍
common.code_record_title|원래 기록 값|서랍
steps.server.cost_basis|표시한 비용은 현재 서버의 추정값입니다.|위쪽 막대, S06
steps.details.open|자세히 보기|S06 서랍 입구
steps.server.choose|서버 고르기|S06
steps.server.start|켜기|S06
steps.server.wait|준비 기다리기|S06
steps.server.stop|쓰고 나서 끄기|S06
steps.server.choose_title|어느 서버에서 AI를 켤까요?|S06
steps.server.choose_target|다시 시험에서 {model}를 골랐습니다.|S06
steps.server.only_on|이 AI는 {server}에서 켤 수 있습니다.|S06
steps.server.no_server|이 앱에서는 이 AI를 켤 수 없습니다. 할 일: 다시 시험에서 다른 AI를 고르세요.|S06
steps.server.rented_name|빌린 서버 (RunPod)|S06
steps.server.company_name|회사 서버 (RNGD)|S06
steps.server.matches|고른 AI를 켤 수 있습니다.|S06
steps.server.mismatch|고른 AI는 이 서버에서 켤 수 없습니다.|S06
steps.server.fact_models|켤 수 있는 AI|S06
steps.server.fact_cost|요금|S06
steps.server.company_cost|추가 임대료 없음|S06
steps.server.use_rented|빌린 서버로 켜기|S06
steps.server.use_company|회사 서버로 켜기|S06
steps.server.use_other_ai|이 서버에서 다른 AI 켜기|S06
steps.server.stop_company_note|다 쓰면 모델을 끄세요. 회사 서버에는 한 번에 모델 하나만 올라갑니다. 연결을 닫아도 모델은 회사 서버에 켜진 채로 남습니다.|S06
steps.server.start_company_other_title|먼저 켜져 있는 AI를 끄세요.|S06
steps.server.wait_auto|이대로 두면 {minutes}분 뒤 자동으로 지워집니다.|S06
servers.failed.fact|앱이 서버 상태를 읽지 못했습니다. 지금 요금이 나가는지도 알 수 없습니다.|S06
steps.server.other_on|다른 서버에서 {model}가 켜져 있거나 준비 중입니다.|S06
steps.server.other_on_open|그 서버 보기|S06
steps.server.back_choose|서버 다시 고르기|S06
steps.server.start_rented_title|요금을 확인하고 서버를 만드세요.|S06
steps.server.start_rented_say|다음 단추는 확인 창을 엽니다. 요금은 확인 창에서 만들기를 누른 순간부터 나갑니다.|S06
steps.server.stat_hourly|시간당 요금|S06
steps.server.stat_forgot|잊었을 때 ({hours}시간)|S06
steps.server.forgot_note|서버 안 타이머가 {hours}시간에 지운다고 보고 계산한 추정입니다. 저장 공간 비용은 별도입니다.|S06
steps.server.quote_basis|지난 기록으로 잡은 추정입니다. 실제 요금과 다를 수 있습니다.|S06
steps.server.fact_target_model|켜는 AI|S06
steps.server.fact_auto_delete|자동 삭제|S06
steps.server.fact_storage|저장 공간|S06
steps.server.fact_basis|요금 근거|S06
steps.server.fact_return|돌아갈 곳|S06
steps.server.return_value|다시 시험 · {doc} · {section}번 부분|S06
steps.server.confirm_create|켜진 동안 시간당 약 ${cost_per_hour}가 듭니다. 아래 단추를 누르는 순간부터 요금이 나갑니다. 준비 완료 시각은 모릅니다. 요청이 20분 없으면 앱이 지우고, 앱이 꺼져 있어도 서버 안 타이머가 4시간에 지웁니다.|S06
steps.server.start_company_tunnel_title|내 컴퓨터와 회사 서버를 연결하세요.|S06
steps.server.start_company_pick_title|내 컴퓨터와 회사 서버를 연결했습니다. 이제 AI를 고르세요.|S06
steps.server.start_company_say|회사 서버에는 한 번에 AI 하나만 올라갑니다.|S06
steps.server.start_company_note|추가 임대료는 없습니다. 켜는 동안 다른 작업을 해도 됩니다.|S06
steps.server.tunnel_line|회사 서버 연결 통로를 엽니다.|S06
steps.server.pick_line|켤 AI를 고릅니다.|S06
steps.server.start_done_rented|서버 만듦|S06
steps.server.start_done_company|AI 켜기 시작|S06
steps.server.wait_title|{model}를 준비하고 있습니다.|S06
steps.server.wait_say|이 화면을 떠나도 준비는 계속됩니다. 준비되면 위쪽 막대가 바뀝니다.|S06
steps.server.wait_server|빌린 서버가 켜져 있습니다. 이때부터 요금이 나갑니다.|S06
steps.server.wait_server_unseen|서버 목록에서 새 서버를 찾고 있습니다.|S06
steps.server.wait_process|회사 서버에서 모델 실행 프로그램을 확인했습니다.|S06
steps.server.wait_process_unseen|회사 서버에서 모델 실행 프로그램을 찾고 있습니다.|S06
steps.server.wait_reply|AI의 응답을 기다립니다.|S06
steps.server.wait_match|고른 AI가 응답하면 다음 단계로 넘어갑니다.|S06
steps.server.wait_on_for|서버가 켜진 지 {elapsed}입니다.|S06
steps.server.cancel_rented|취소하고 서버 지우기 (요금 멈춤)|S06
steps.server.cancel_company|취소하고 AI 끄기|S06
steps.server.stop_say_rented|다 쓰면 서버를 지워야 요금이 멈춥니다.|S06
steps.server.stat_uptime|켜진 시간|S06
steps.server.stat_total|지금까지 (추정)|S06
steps.server.stat_auto|자동 삭제까지|S06
steps.server.auto_unknown|확인 안 됨|S06
steps.server.delete_note|시험을 더 하려면 그대로 두세요. 오늘 더 쓰지 않으면 서버를 지우세요. 지우는 순간 요금이 멈추고, 다음에 다시 만들 수 있습니다.|S06
steps.server.delete_action|서버 지우고 요금 멈추기|S06
steps.server.others_running|이 앱이 만든 다른 서버 {count}개도 켜져 있습니다. 할 일: 자세히 보기에서 지우세요.|S06
steps.server.preparation_unknown|준비에 걸린 시간 기록이 없습니다.|S06
steps.server.prepared_time|준비에 약 {elapsed} 걸렸습니다.|S06
steps.server.prepared_short|약 {elapsed} 걸림|S06
steps.server.details_title|자세히 · 서버와 설정|S06
steps.server.details_hint|서버 목록과 설정 이름, 서버 기록을 봅니다.|S06
steps.server.settings|설정 확인 기록|S06
steps.server.connection|회사 서버 연결 기록|S06
steps.back|이전 단계로 가기|S03
steps.next|다음: {name}|S03
steps.jobs.loading|작업 기록을 읽고 있습니다.|S05
steps.trial.target|무엇을|S03
steps.trial.model|어느 AI로|S03
steps.trial.prompt|무엇을 시킬지|S03
steps.trial.running|시험|S03
steps.trial.result|결과|S03
steps.trial.scope.a11y|시험 범위|S03
steps.trial.scope.part|한 부분|S03
steps.trial.scope.document|문서 전체|S03
steps.trial.scope.batch|여러 문서|S03
steps.trial.target_title|무엇을 다시 시험할까요?|S03
steps.trial.target_filled|원문 화면에서 고른 부분이 채워져 있습니다. 그대로 두면 됩니다.|S03
steps.trial.target_say|문서와 부분을 고르세요.|S03
steps.trial.batch_hint|‘여러 문서’를 고르면 이 자리에 문서 목록과 반복 횟수가 나옵니다.|S03
steps.trial.model_on_title|{model}가 켜져 있습니다. 이대로 시험하면 됩니다.|S03
steps.trial.model_on_say|이번 결과를 만든 AI라 전후를 바로 비교할 수 있습니다.|S03
steps.trial.model_off_title|고른 AI가 꺼져 있습니다. 먼저 켜야 합니다.|S03
steps.trial.model_off_say|AI를 켠 뒤 ‘시험으로 돌아가기’를 누르면 이 화면으로 옵니다. 고른 문서와 부분은 그대로 남습니다.|S03
steps.trial.state_on|지금 켜짐|S03
steps.trial.state_off|지금 꺼짐|S03
steps.trial.made_base|이번 결과를 만든 AI입니다.|S03
steps.trial.on_note|응답을 확인했습니다.|S03
steps.trial.on_rented|응답을 확인했습니다. 서버 요금은 시간당 ${hourly}입니다.|S03
steps.trial.on_company|응답을 확인했습니다. 추가 임대료가 없습니다.|S03
steps.trial.off_rented|켜면 시간당 ${hourly}가 나갑니다.|S03
steps.trial.off_company|추가 임대료가 없습니다. 준비에 보통 15~25분 걸립니다.|S03
steps.trial.off_note|켜러 가도 요금은 아직 나가지 않습니다. 서버를 만들 때 다시 확인합니다.|S03
steps.trial.prepare|고른 AI 켜러 가기|S03
steps.trial.practice|연습: AI 없이 보낼 내용 보기|S03
steps.trial.prompt_title|AI에게 시킬 일을 정하세요.|S03
steps.trial.prompt_say|이 글이 지시문입니다. 고치면 전후 점수로 효과를 볼 수 있습니다.|S03
steps.trial.prompt_default|기본 지시문 그대로|S03
steps.trial.prompt_default_note|같은 조건으로 결과만 다시 봅니다.|S03
steps.trial.prompt_edit|고쳐서 시험|S03
steps.trial.prompt_edit_note|고른 뒤 아래 글을 바로 고칩니다. 새로고침하면 고친 글은 사라집니다.|S03
steps.trial.prompt_used_default|기본 지시문|S03
steps.trial.prompt_used_edited|고친 지시문|S03
steps.trial.send_note|{target}을 {model}에게 보냅니다.|S03
steps.trial.previous_time|같은 조건의 지난 시험은 {seconds}초 걸렸습니다.|S03
steps.trial.batch_prompt_title|조건을 확인하고 시작하세요.|S03
steps.trial.running_title|AI가 {target}을 읽고 있습니다.|S03
steps.trial.batch_running_title|여러 문서 시험이 진행 중입니다.|S03
steps.trial.sent|AI에게 보냈습니다.|S03
steps.trial.pending|AI의 응답과 결과를 기다립니다.|S03
steps.trial.elapsed|시험을 시작한 지 {seconds}초입니다.|S03
steps.trial.see_result|결과 보기|S03
steps.trial.result_later|끝나면 결과로 저절로 넘어갑니다.|S03
steps.trial.failed_title|시험이 실패했습니다.|S03
steps.trial.took|{seconds}초 걸림|S03
steps.trial.practice_button_note|연습 단추는 AI 없이 보낼 내용만 확인합니다. 연습으로는 시험 기록과 점수가 생기지 않습니다.|S03
steps.trial.details_hint_practice|보낸 입력과 오류 기록을 봅니다.|S03
steps.trial.partial_score_up|이 부분을 바꾸니 문서 전체 점수가 {before}점에서 {after}점으로 올랐습니다.|S03
steps.trial.partial_score_down|이 부분을 바꾸니 문서 전체 점수가 {before}점에서 {after}점으로 내려갔습니다.|S03
steps.trial.partial_score_same|이 부분을 바꿔도 문서 전체 점수는 {before}점 그대로입니다.|S03
steps.trial.score_up|문서 전체 점수가 {before}점에서 {after}점으로 올랐습니다.|S03
steps.trial.score_down|문서 전체 점수가 {before}점에서 {after}점으로 내려갔습니다.|S03
steps.trial.score_same|문서 전체 점수가 {before}점으로 그대로입니다.|S03
steps.trial.result_say|같은 조건을 반복해도 점수는 조금 달라질 수 있습니다. 한 번의 변화로 단정하지 마세요.|S03
steps.trial.parse_title|AI가 답했지만 값을 읽지 못했습니다.|S03
steps.trial.parse_todo|실제 시험 성공은 기록하지 않았습니다. 할 일: 자세히 보기의 ‘읽어 낸 값’을 보고 다시 시험하세요.|S03
steps.trial.practice_title|연습이 끝났습니다. 보낼 내용만 확인했습니다.|S03
steps.trial.practice_omitted|연습에서는 AI의 답과 점수를 만들지 않습니다. 보낸 입력은 자세히 보기에 있습니다.|S03
steps.trial.after_practice|실제 시험 준비하기|S03
steps.trial.change_unavailable|이 값의 전후 변화를 확인할 결과가 없습니다.|S03
steps.source.choose|문제 고르기|S02
steps.source.compare|원문과 맞춰 보기|S02
steps.source.send|다시 시험으로 보내기|S02
steps.source.choose_title|어떤 항목의 문제부터 볼까요?|S02
steps.source.choose_say|점수를 많이 깎은 순서입니다. 맨 위부터 보면 됩니다.|S02
steps.source.row_meaning|행은 표의 한 줄입니다. 칸은 그 줄 안의 값 하나입니다.|S02
steps.source.choose_summary|{what} · 문제 있는 행 {count}개 · 바꾸기|S02
steps.source.choose_summary_plain|{what} · 바꾸기|S02
steps.source.compare_hint|한 행씩 확인|S02
steps.source.send_hint|고른 부분을 넘김|S02
steps.source.send_summary|{doc} · {section}번 부분|S02
steps.source.all_docs|전체 {count}건|S02
steps.source.col_item|문제가 있는 항목|S02
steps.source.col_loss|깎인 점수|S02
steps.source.col_rows|문제 행|S02
steps.source.col_cells|문제 칸|S02
steps.source.col_open|볼 문제|S02
steps.source.loss|{points}점|S02
steps.source.open|이 문제 보기|S02
steps.source.all_criteria|기준 {count}개 모두 보기|S02
steps.source.top_criteria|큰 문제만 보기|S02
steps.source.run_failed|이 결과의 점수를 읽지 못해 항목 표를 보이지 않습니다. 할 일: 다시 불러오세요.|S02
steps.source.list_title|문서 {count}건의 문제 행|S02
steps.source.list_title_one|{doc}의 문제 행|S02
steps.source.earlier_rows|앞쪽 {count}행 보기|S02
steps.source.evidence_title|AI가 근거로 댄 줄|S02
steps.source.choose_section|부분 고르기|S02
source.labels.code_value|{name} ({code})|S02
source.field_names.standard|기준 출처|S02
source.field_names.form|물질 형태|S02
source.field_names.kr_basis|국내 기준 근거|S02
source.field_names.bio_medium|생물 시료|S02
source.field_names.bio_timing|채취 시기|S02
source.field_names.bio_determinant|측정 대상|S02
source.field_names.notations|표기|S02
source.field_names.prop_code|물성 항목|S02
source.field_names.text_value|글로 적힌 값|S02
source.field_names.data_source|자료 출처|S02
source.field_names.endpoint|독성 항목|S02
source.field_names.descriptor|독성 지표|S02
source.field_names.species|시험 생물|S02
source.field_names.sex|성별|S02
source.field_names.duration_value|노출 시간|S02
source.field_names.duration_unit|시간 단위|S02
source.field_names.physical_form|물질 상태|S02
source.field_names.exposure_type|노출 방식|S02
source.field_names.converted|환산 여부|S02
source.field_names.read_across_cas|유추 근거 물질 번호|S02
source.field_names.guideline|시험 지침|S02
source.field_names.classification|분류 판정|S02
source.field_names.statements|설명 문장|S02
source.field_names.hazard|유해성 종류|S02
source.field_names.agency|평가 기관|S02
source.field_names.class|등급|S02
source.field_names.law|법률|S02
source.field_names.item_code|규제 항목|S02
source.field_names.item_raw|규제 항목(원래 표기)|S02
source.field_names.applicable|해당 여부|S02
source.field_names.threshold|기준량|S02
source.field_names.qty|수량|S02
source.field_names.qty_alt|다른 단위 수량|S02
source.field_names.sub_class|세부 분류|S02
source.field_names.cycle|주기|S02
source.field_names.country|국가|S02
source.field_names.value_raw|규제 값(원래 표기)|S02
source.field_names.remark|참고|S02
source.field_names.name_en|영어 이름|S02
source.field_names.synonyms|다른 이름|S02
source.field_names.ec_no|EC 번호|S02
source.field_names.other_id|다른 식별 번호|S02
source.field_names.other_id_type|다른 식별 번호의 종류|S02
source.field_names.parent_seq|상위 성분 순번|S02
source.field_names.content|함유량|S02
source.field_names.content_note|함유량 메모|S02
source.field_names.content_basis|함유량 기준|S02
source.field_names.trade_secret|영업비밀 여부|S02
source.field_names.approval_no|승인 번호|S02
source.field_names.approval_expiry|승인 만료일|S02
source.field_names.role|회사 역할|S02
source.field_names.site|사업장|S02
source.field_names.address|주소|S02
source.field_names.postcode|우편번호|S02
source.field_names.department|부서|S02
source.field_names.contacts.type|연락처 종류|S02
source.field_names.contacts.value|연락처|S02
source.field_names.mode|운송 수단|S02
source.field_names.basis_raw|근거 표기|S02
source.field_names.regulated|규제 여부|S02
source.field_names.un_no|UN 번호|S02
source.field_names.shipping_name|운송 품명|S02
source.field_names.hazard_class|위험 등급|S02
source.field_names.sub_risk|부차 위험|S02
source.field_names.packing_group|포장 등급|S02
source.field_names.marine_pollutant|해양 오염 물질|S02
source.field_names.ems_fire|비상 조치(화재)|S02
source.field_names.ems_spill|비상 조치(누출)|S02
source.field_names.item|품명|S02
source.field_names.water_soluble|수용성 여부|S02
source.field_names.grade|등급 표기|S02
source.field_names.designated_qty|지정 수량|S02
source.field_names.designated|지정폐기물 여부|S02
source.field_names.waste_type|폐기물 종류|S02
source.field_names.system|분류 체계|S02
source.field_names.class_raw|분류(원래 표기)|S02
source.field_names.h_code|H 코드|S02
source.field_names.section_no|넣을 부분 번호|S02
source.field_names.after_item|앞 항목|S02
source.field_names.title_raw|원문 제목|S02
source.field_names.reason|표 밖에 둔 이유|S02
source.field_names.suggested_code|제안 코드|S02
steps.source.filter_a11y|문제 종류|S02
steps.source.doc_rows|{doc} · {count}행|S02
steps.source.row_kind|{kind} {count}칸|S02
steps.source.more_rows|{count}행 더 보기|S02
steps.source.partial|일부 문서만 읽었습니다. 할 일: 읽지 못한 문서를 다시 불러오세요.|S02
steps.source.previous_row|이전 행 보기|S02
steps.source.next_row|다음 행 보기|S02
steps.source.row_summary|{doc} · {section}번 부분 · 칸 {total}개 중 문제 {problems}개|S02
steps.source.row_position|{total}행 중 {index}번째 행|S02
steps.source.col_result|결과|S02
steps.source.compare_note|노란색은 지금 보는 값과 그 근거입니다. AI가 틀렸다면 이 부분을 다시 시험하세요.|S02
steps.source.image_title|원문 그림 · {page}쪽|S02
steps.source.lines_title|원문 글자 · {page}쪽|S02
steps.source.lines_near|원문 글자 · {page}쪽 {line}번째 줄 근처|S02
steps.source.all_lines|쪽 전체 줄 보기|S02
steps.source.near_lines|고른 값 근처 줄 보기|S02
steps.source.no_linked_lines|이 쪽에는 값과 연결된 줄이 없습니다. 할 일: 쪽 전체 줄을 보세요.|S02
steps.source.send_title|이 내용을 다시 시험으로 넘깁니다.|S02
steps.source.send_say|이 단추는 시험을 시작하지 않습니다. 다음 화면에서 AI와 지시문을 확인합니다.|S02
steps.source.send_no_value|고른 값이 없습니다. 문서와 부분만 넘깁니다.|S02
steps.source.details_title|자세히 · 원문과 값|S02
steps.source.details_hint|문서 전체 표와 추정 방법, 잠긴 문서를 봅니다.|S02
steps.source.raw_value_title|원래 값과 위치|S02
steps.source.scope_title|비교 범위|S02
steps.source.scope_items|이 값은 ‘{items}’ 점수에 들어갑니다.|S02
steps.source.scope_none|이 값은 점수 기준에 들어가지 않습니다.|S02
steps.source.scope_note|같은 표의 다른 칸은 다른 기준에도 쓰일 수 있습니다.|S02
steps.source.doc_table_open|문서 전체 표 열기|S02
steps.source.howto_title|값과 줄을 고르는 법|S02
steps.source.target_title|보고 있는 기록|S02
steps.trial.change_title|고른 값의 변화|S03
steps.trial.change_value|AI 값: {before} → {after}|S03
steps.trial.change_kind|판정: {before} → {after}|S03
steps.trial.change_same|이 값은 달라지지 않았습니다.|S03
steps.trial.change_gone|새 결과에서 이 행을 찾지 못했습니다.|S03
steps.trial.change_loading|고른 값의 변화를 읽고 있습니다.|S03
steps.trial.change_open|새 결과에서 이 값 원문 보기|S03
steps.trial.change_none|값 없음|S03
steps.trial.server_on|빌린 서버가 아직 켜져 있습니다.|S03
steps.trial.company_on|회사 서버가 아직 켜져 있습니다. 추가 임대료는 없습니다.|S03
steps.trial.close_server|AI 켜기와 비용에서 끄기|S03
steps.trial.edit_again|지시문 고쳐 다시 시험|S03
steps.trial.batch_done_title|여러 문서 시험이 끝났습니다.|S03
steps.trial.open_recent|최근 결과에서 보기|S03
steps.trial.details_title|자세히 · 시험 기록|S03
steps.trial.details_hint|보낸 입력과 AI의 원래 답, 오류 기록을 봅니다.|S03
steps.trial.prompt_origin_title|지시문의 출처와 보관 방식|S03
steps.trial.conditions_title|대상과 조건|S03
context.model.chip_on|AI 켜짐|위쪽 막대
context.model.chip_no_cost|요금 없음|위쪽 막대
context.model.chip_cost_unknown|요금 확인 안 됨|위쪽 막대
context.model.rented_so_far|지금까지 약 ${cost}|위쪽 막대
steps.server.stop_order|끄는 순서|S06 ④ 말풍선
steps.source.kind_notes.wrong|값이 다름|S02 ② 문제 종류 안내
steps.source.kind_notes.made|정답에 없는 값|S02 ② 문제 종류 안내
steps.source.kind_notes.missing|AI가 놓친 값|S02 ② 문제 종류 안내

### swap — S11 자료 바꾸기

시안 6화면을 11/2 승인 대기로 옮겼습니다. 윗줄 지금 닫기 단추는 11/2 사용자 결정으로 넣지 않았습니다.

|키|글|쓰는 곳|
|---|---|---|
nav.swap|새 자료 받기|전역, S11
context.model.off_no_cost|요금이 나가지 않습니다.|전역
context.model.rented_hourly|시간당 약 ${cost}|전역
context.model.rented_auto_close|요청이 {idle}분 없으면 자동으로 닫힙니다.|전역
context.model.rented_auto_left|{minutes}분 남았습니다.|전역
context.model.rented_close_where|지금 닫으려면 AI 켜기와 비용 화면으로 가세요.|전역
context.model.auto_closed_idle|요청 없이 {limit}분이 지나 서버를 닫았습니다.|전역
context.model.auto_closed_no_reply|모델이 {limit}분 동안 응답하지 않아 서버를 닫았습니다.|전역
context.model.auto_closed_cost|켠 시간 {minutes}분, 추정 ${cost}.|전역
swap.context.score_docs|점수를 매길 수 있는 문서 {count}건|S11
swap.context.no_score|점수 없음 · 양식만 확인|S11
swap.context.score_docs_short|채점 문서 {count}건|위쪽 막대
swap.context.no_score_short|점수 없음|위쪽 막대
swap.context.gold_note|최근 올린 날 {date} · 정답 {count}건 사용|S11
swap.context.gold_changed|새 정답이 들어왔습니다. 문서 {count}건이 바뀌어 점수를 다시 계산합니다.|S11
swap.context.gold_changed_open|무엇이 바뀌었나요|S11
swap.steps.a11y|폴더 바꾸기 단계|S11
swap.steps.pick|1 폴더 고르기|S11
swap.steps.check|2 검사|S11
swap.steps.apply|3 적용|S11
swap.back|처음으로|S11
swap.start.title|어떤 자료를 새로 받았나요?|S11
swap.start.lead|받은 자료에 따라 하는 일이 다릅니다. 검사와 복사에는 AI를 쓰지 않아 요금이 들지 않습니다.|S11
swap.start.docs_title|새 문서 폴더|S11
swap.start.docs_note|PDF를 글자로 바꾸는 담당이 보내 준 폴더입니다. 문서마다 쪽별 글자가 들어 있고, AI가 이 글을 읽습니다. 예: Downloads/version17_신규40|S11
swap.start.docs_action|폴더 고르기|S11
swap.start.gold_title|새 정답 파일|S11
swap.start.gold_note|정답 담당이 GitHub에 올린 파일입니다. AI 결과와 견줘 점수를 매기는 기준입니다.|S11
swap.start.gold_action|새 정답 받기|S11
swap.start.have_title|새로 받은 자료가 없을 때|S11
swap.start.have_note|앱에 이미 있는 폴더나 정답으로 바꾸기만 합니다. 파일은 복사하지 않습니다.|S11
swap.start.have_action|앱에 있는 것으로 바꾸기|S11
swap.pick.title|어느 문서 폴더를 쓸까요?|S11
swap.pick.lead|Downloads에서 문서 폴더처럼 보이는 것을 찾았습니다. 앱에 없는 폴더는 검사한 뒤 앱으로 복사합니다. 검사만으로는 파일이 옮겨지지 않습니다.|S11
swap.pick.in_app|앱에 있음|S11
swap.pick.not_in_app|앱에 없음|S11
swap.pick.meta|문서 {count}건 · {time}에 받음|S11
swap.pick.check|검사하기|S11
swap.pick.empty|Downloads에서 문서 폴더를 찾지 못했습니다. 아래에 경로를 직접 적어 주세요.|S11
swap.pick.unreadable|Downloads 폴더를 읽지 못했습니다. 아래에 경로를 직접 적어 주세요.|S11
swap.pick.other_label|다른 곳에 있는 폴더의 전체 경로|S11
swap.pick.other_placeholder|/Users/내이름/Downloads/version18|S11
swap.pick.other_hint|압축 파일은 먼저 풀어 주세요.|S11
swap.check.checking|폴더를 검사하고 있습니다. 파일은 옮기지 않습니다.|S11
swap.check.title.score|이 폴더로 시험하고 점수도 볼 수 있습니다.|S11
swap.check.title.format_only|이 폴더는 쓸 수 있지만 점수는 나오지 않습니다.|S11
swap.check.title.unusable|이 폴더로는 시험할 수 없습니다.|S11
swap.check.no_overlap_title|이 폴더의 문서와 겹치는 정답이 없습니다.|S11
swap.check.no_overlap_body|정답이 있는 문서와 문서 번호가 다릅니다. 이 폴더는 처음 보는 문서에서 AI 결과가 양식에 맞는지 볼 때 고릅니다.|S11
swap.check.alternative|점수를 보려면 정답이 있는 문서 {count}건이 든 {set} 폴더를 고르세요.|S11
swap.check.unusable_body|시험할 수 있는 문서가 없습니다. 줄 번호가 없거나 열지 않는 문서뿐입니다. 폴더를 보낸 담당에게 줄 번호가 있는 판을 요청하세요.|S11
swap.check.can_title|이 폴더로 할 수 있는 일|S11
swap.check.yes|가능|S11
swap.check.no|안 됨|S11
swap.check.batch_yes|{count}건을 한꺼번에 시험하기. AI 결과가 정해진 양식에 맞는지 봅니다.|S11
swap.check.score_yes|점수 매기기. 정답이 있는 문서 {count}건에 점수가 나옵니다.|S11
swap.check.score_no|점수 매기기. 비교할 정답이 없습니다.|S11
swap.check.try_yes|문서 하나의 한 부분만 다시 시험하기. 고를 수 있는 문서 {count}건.|S11
swap.check.try_no|문서 하나의 한 부분만 다시 시험하기. 지금은 개발용 문서 목록에 있는 문서만 됩니다.|S11
swap.check.facts_title|검사 결과|S11
swap.check.docs_label|문서|S11
swap.check.docs_value|{count}건|S11
swap.check.lines_label|줄 번호|S11
swap.check.lines_all|열 수 있는 {count}건 모두 있음. AI가 근거로 적는 번호라 있어야 시험할 수 있습니다. 예: L001|S11
swap.check.lines_some|열 수 있는 문서 중 {count}건에 없음. 이 문서들은 시험에서 빠집니다. AI가 근거로 적는 번호입니다. 예: L001|S11
swap.check.locked_label|열지 않는 문서|S11
swap.check.locked_none|없음|S11
swap.check.locked_eval|최종 평가 문서 {count}건. 점수가 부풀지 않도록 복사만 하고 열지 않습니다.|S11
swap.check.locked_same|{doc}는 최종 평가 문서 {eval_doc}와 원본이 같습니다.|S11
swap.check.locked_unknown|용도를 확인할 수 없는 문서 {count}건. 문서 폴더의 meta.json에 문서 번호가 있어야 열립니다.|S11
swap.check.target_label|앱에 넣을 곳|S11
swap.check.target_new|이 앱을 켠 작업 폴더에만 들어갑니다. 받은 폴더는 그대로 둡니다.|S11
swap.check.target_same|이미 앱에 있습니다. 복사하지 않습니다.|S11
swap.check.target_conflict_title|앱에 같은 이름의 다른 폴더가 있습니다.|S11
swap.check.target_conflict|덮어쓰지 않습니다. 받은 폴더의 이름을 바꾼 뒤 다시 검사하세요. 예: version18_2|S11
swap.check.past_label|지난 결과|S11
swap.check.past_value|지우지 않습니다. 이전 문서 묶음으로 돌아가면 다시 보입니다.|S11
swap.check.apply_note_new|누르면 이 폴더를 앱으로 복사하고 화면 위쪽의 시험할 문서 묶음을 이 폴더로 바꿉니다. 다음 화면의 되돌리기 단추로 이전 묶음으로 돌아갈 수 있습니다.|S11
swap.check.apply_note_same|누르면 복사 없이 화면 위쪽의 시험할 문서 묶음만 이 폴더로 바꿉니다. 다음 화면의 되돌리기 단추로 이전 묶음으로 돌아갈 수 있습니다.|S11
swap.check.apply|이 폴더로 바꾸기|S11
swap.check.applying|폴더를 복사하고 있습니다.|S11
swap.check.switching|문서 묶음을 바꾸고 있습니다.|S11
swap.check.other|다른 폴더 고르기|S11
swap.done.title|이제 이 폴더로 시험합니다.|S11
swap.done.changed|화면 위쪽의 시험할 문서 묶음이 바뀌었습니다.|S11
swap.done.results_none|이 폴더로 만든 결과가 아직 없어 최근 결과 화면은 비어 있습니다.|S11
swap.done.results_found|이 폴더로 만든 결과 {count}개를 최근 결과에서 볼 수 있습니다.|S11
swap.done.off_title|다음 할 일: AI 켜기|S11
swap.done.off_note|시험하려면 AI가 켜져 있어야 합니다. 이 단추는 서버 고르는 화면만 엽니다. 요금은 그 화면에서 서버를 만든 때부터 나갑니다.|S11
swap.done.off_action|서버 고르는 화면 열기|S11
swap.done.on_title|다음 할 일: 여러 문서 시험하기|S11
swap.done.on_note|AI가 연결되어 있습니다. 이 단추는 시험할 문서를 고르는 화면만 엽니다. 시험은 그 화면에서 시작합니다.|S11
swap.done.on_action|시험 화면 열기|S11
swap.done.undo_title|되돌리기|S11
swap.done.undo_note|이전 문서 묶음({set})으로 돌아갑니다. 복사한 파일은 지우지 않습니다.|S11
swap.done.undo|되돌리기|S11
swap.done.undone|이전 문서 묶음으로 돌아갔습니다.|S11
swap.gold.title|새 정답은 GitHub에서 받습니다.|S11
swap.gold.lead|정답 담당이 검수해 올립니다. 앱에서 정답 파일을 고치지 않습니다. 고칠 곳을 찾으면 담당에게 알려 주세요.|S11
swap.gold.now_title|내 컴퓨터에 받아 둔 정답|S11
swap.gold.name_label|이름|S11
swap.gold.name_value|사람이 확인한 정답|S11
swap.gold.commit_label|최근에 올린 것|S11
swap.gold.commit_none|기록을 읽지 못했습니다.|S11
swap.gold.docs_label|점수에 쓰는 정답|S11
swap.gold.docs_value|개발용 문서 {count}건|S11
swap.gold.eval_label|최종 평가용 정답|S11
swap.gold.eval_value|{count}건. 점수가 부풀지 않도록 파일을 열지 않고 개수만 셉니다.|S11
swap.gold.selected_label|지금 비교 중인 정답|S11
swap.gold.other_selected|지금 점수는 이 정답이 아니라 다른 정답과 비교합니다.|S11
swap.gold.use_gold|이 정답으로 바꾸기|S11
swap.gold.checking|GitHub를 확인하고 있습니다.|S11
swap.gold.behind_title|GitHub에 더 새 정답이 있습니다. 개발용 문서 {dev}건, 최종 평가 문서 {eval_docs}건이 다릅니다.|S11
swap.gold.behind_body|터미널에서 아래 명령으로 받은 뒤 다시 확인하기를 누르세요. 앱을 다시 켤 필요는 없습니다.|S11
swap.gold.branch_note|이 앱은 {branch} 가지에서 켜져 있어 main의 정답을 합치는 명령을 보여 줍니다.|S11
swap.gold.latest|GitHub의 정답과 같습니다. 받을 것이 없습니다.|S11
swap.gold.offline|GitHub에 연결하지 못했습니다. 받아 둔 정답은 그대로 쓸 수 있습니다.|S11
swap.gold.changed_title|지난번 뒤로 새 정답이 들어왔습니다. 개발용 문서 {dev}건, 최종 평가 문서 {eval_docs}건이 바뀌었습니다.|S11
swap.gold.changed_docs|바뀐 개발용 문서: {docs}|S11
swap.gold.after|새 정답을 받으면 저장된 결과의 점수를 AI 없이 다시 계산합니다. 저장된 AI 결과는 바뀌지 않습니다.|S11
swap.gold.recheck|다시 확인하기|S11
swap.gold.open_scores|최근 결과의 점수 보기|S11
swap.problems.swap_no_path.message|폴더를 찾지 못했습니다: {path}|S11
swap.problems.swap_no_path.fix|폴더의 전체 경로를 적어 주세요. 예: /Users/내이름/Downloads/version18|S11
swap.problems.swap_doc_folder.message|{name}은 문서 하나의 폴더입니다.|S11
swap.problems.swap_doc_folder.fix|그 위 폴더를 고르세요.|S11
swap.problems.swap_bad_name.message|폴더 이름을 쓸 수 없습니다: {name}|S11
swap.problems.swap_bad_name.fix|글자, 숫자, 밑줄만 남도록 이름을 바꾼 뒤 다시 검사하세요. 예: version18|S11
swap.problems.swap_no_docs.message|{name} 바로 안에 문서 폴더가 없습니다.|S11
swap.problems.swap_no_docs.fix|압축을 풀었는지 확인하세요. 한 단계 안쪽 폴더일 수도 있습니다. 문서 폴더에는 p001.txt 같은 파일이 있습니다.|S11
swap.problems.swap_unusable.message|{name}에는 시험할 수 있는 문서가 없습니다.|S11
swap.problems.swap_unusable.fix|폴더를 보낸 담당에게 줄 번호가 있는 판을 요청하세요.|S11
swap.problems.swap_conflict.message|앱에 같은 이름의 다른 폴더가 있습니다: {target}|S11
swap.problems.swap_conflict.fix|받은 폴더의 이름을 바꾼 뒤 다시 검사하세요. 예: version18_2|S11
swap.problems.swap_copy_failed.message|폴더를 복사하지 못했습니다: {detail}|S11
swap.problems.swap_copy_failed.fix|디스크 공간과 폴더 권한을 확인한 뒤 다시 누르세요. 복사하다 만 파일은 남지 않습니다.|S11
guide.ai.rented_time|빌린 서버는 켜는 데 3~6분 걸려요. 요청이 20분 없으면 앱이 닫아요.|G10
help.setup.new_data|새 문서 폴더나 새 정답을 받았으면 화면 위쪽의 새 자료 받기를 누르세요. 문서 폴더는 검사한 뒤 앱으로 복사하고, 정답은 GitHub에서 받는 명령을 알려 줍니다.|S07
help.servers.states|화면 위쪽에서 상태를 봅니다. AI 꺼짐은 정상입니다. 빌린 서버를 만들면 켜는 중이 3~6분 보이고, 연결된 모델이 보이면 시험을 보낼 수 있습니다.|S07
help.servers.waiting|10분이 지나도 켜는 중이면 AI 켜기와 비용의 자세히 보기에서 서버 기록을 확인하세요. 모델이 40분 동안 응답하지 않으면 앱이 서버를 지웁니다.|S07

### glossary — S07 용어 · S01, S02 첫 소개

키|글|쓰는 곳
---|---|---
glossary.silver.term|AI 정답 초안(실버)|S07
glossary.silver.meaning|AI가 먼저 만든 비교용 답입니다. 예: data/silver/claude에 있는 답입니다.|S07
glossary.gold.term|사람이 확인한 정답(골드)|S07
glossary.gold.meaning|사람이 검토해 확정한 답입니다. 예: data/gold/T21-S001.json입니다.|S07
glossary.weighted.term|중요도를 반영한 전체 점수(가중 종합)|S07
glossary.weighted.meaning|각 기준에 중요도만큼 비중을 주어 계산한 점수입니다. 예: 최근 전체 점수 82.4점의 목표는 90점입니다.|S07
glossary.must_count.term|필수 기준의 목표 달성 수|S07
glossary.must_count.meaning|필수 기준 중 각자의 목표 점수에 닿은 기준 수입니다. 예: 12/17은 필수 17개 중 12개가 목표에 닿았다는 뜻입니다.|S07
glossary.must.term|각각 목표를 채워야 하는 기준(필수)|S07
glossary.must.meaning|전체 점수와 별개로 각 기준의 목표를 확인하는 등급입니다. 예: 필수 기준 하나의 점수 비중은 3입니다.|S07
glossary.important.term|그다음으로 중요한 기준(중요)|S07
glossary.important.meaning|필수보다 작은 비중으로 전체 점수에 반영하는 등급입니다. 예: 중요 기준 하나의 점수 비중은 2입니다.|S07
glossary.ordinary.term|나머지 점수 기준(일반)|S07
glossary.ordinary.meaning|전체 점수에 가장 작은 비중으로 반영하는 등급입니다. 예: 일반 기준 하나의 점수 비중은 1입니다.|S07
glossary.section.term|안전 문서를 나눈 주제(항)|S07
glossary.section.meaning|화학제품 안전 설명서(MSDS)를 나눈 16개 주제 중 하나입니다. 예: 3번 부분은 성분을 다룹니다.|S07
glossary.item.term|점수를 매기는 기준(항목)|S07
glossary.item.meaning|AI가 값을 제대로 옮겼는지 확인하는 검사 단위입니다. 예: 이 앱은 23개 기준으로 점수를 매깁니다.|S07
glossary.prompt.term|AI에게 시킬 일(지시문)|S07,S03
glossary.prompt.meaning|어떤 값을 어떤 형식으로 뽑을지 AI에게 주는 설명입니다. 예: “숫자와 단위를 원문 그대로 옮기세요.”|S07
glossary.prompt_version.term|AI에게 시킬 일을 고친 차례|S07,S04
glossary.prompt_version.meaning|AI에게 보내는 글의 변경 순서를 구분하는 번호입니다. 예: 8번째 설명은 s8로 기록합니다.|S07
glossary.input.term|원문 글자를 모은 폴더|S07
glossary.input.meaning|AI에게 보낼 원문의 쪽별 글자를 모아 둔 곳입니다. 예: 이전 개발 자료 묶음에는 문서마다 쪽별 글자 파일이 있습니다.|S07
glossary.page_text.term|문서 한 쪽의 글자|S07
glossary.page_text.meaning|문서 한 페이지에서 읽어 낸 글입니다. 예: 원문 화면에서 예시 문서 1의 2쪽 글자를 읽습니다.|S07
glossary.line.term|원문의 쪽과 줄 번호|S07
glossary.line.meaning|값이 원문 어디에 있는지 나타내는 위치입니다. 예: p2:L23은 2쪽 23번째 줄입니다.|S07
glossary.base_run.term|새 답을 끼워 넣을 이전 결과(기준 실행)|S07
glossary.base_run.meaning|새로 시험한 부분의 답만 바꿔 점수를 계산할 이전 결과입니다. 예: 82.4점에서 한 부분만 바꿔 계산한 점수는 82.8점입니다.|S07
glossary.practice.term|AI 없이 보낼 내용 확인(입력 확인 연습)|S07
glossary.practice.meaning|AI를 부르지 않고 원문과 시킬 일만 확인하는 연습입니다. 예: 연습 결과에는 보낼 내용만 있고 AI의 답은 없습니다.|S07
glossary.try.term|같은 문서를 다시 처리하기(다시 시험)|S07
glossary.try.meaning|고른 문서의 일부나 전체를 AI에게 다시 읽히는 작업입니다. 예: 예시 문서 1의 8번 부분만 다시 시험합니다.|S07
glossary.batch.term|여러 문서 시험(본 실행)|S07
glossary.batch.meaning|고른 개발용 문서를 같은 조건으로 처리하는 작업입니다. 예: 개발용 10건을 2회 반복합니다.|S07
glossary.comparison.term|여러 결과를 모은 표(비교표)|S07
glossary.comparison.meaning|선택한 결과의 점수와 시간을 나란히 보여 주는 표입니다. 예: 선택한 첫 결과가 첫 번째 열에 들어갑니다.|S07
glossary.missing.term|정답에 있는데 못 뽑음(빠뜨림)|S07
glossary.missing.meaning|정답에는 있고 AI 결과에는 없는 값입니다. 예: 성분 B의 2 mg/m³가 결과에서 빠졌습니다.|S07
glossary.invented.term|정답에 없는 값을 만듦(지어냄)|S07
glossary.invented.meaning|AI 결과에는 있고 정답에는 없는 값입니다. 예: 자료가 없는 성분 H에 AI가 3 mg/m³를 적었습니다.|S07
glossary.wrong.term|정답과 다른 값을 뽑음(틀림)|S07
glossary.wrong.meaning|같은 칸의 값이 정답과 다른 경우입니다. 예: 성분 A의 5 mg/m³를 AI가 8 mg/m³로 옮겼습니다.|S07
glossary.empty_row.term|자료 없음으로 적힌 행(값 없는 행)|S07
glossary.empty_row.meaning|실제 수치 대신 자료 없음 같은 상태만 적힌 표의 줄입니다. 예: 빈 행을 뺀 보조 점수는 83.0점입니다.|S07
glossary.calls.term|문서와 부분별 AI 요청 표(호출 격자)|S07
glossary.calls.meaning|각 부분을 처리한 AI 요청의 상태를 모은 표입니다. 예: 첫 번째 안전자료의 1~16번 부분이 표시됩니다.|S07
glossary.reextract.term|AI에게 다시 뽑도록 요청(재추출)|S07
glossary.reextract.meaning|첫 답에서 발견한 문제를 알려 한 번 더 요청하는 처리입니다. 예: 두 번째 답이 첫 답보다 나을 때만 두 번째 답을 씁니다.|S07
glossary.output_limit.term|답변 길이 제한(출력 한도)|S07
glossary.output_limit.meaning|AI가 한 번에 답할 수 있는 최대 길이입니다. 예: 길이 제한에 걸린 요청은 요청 기록에서 구분합니다.|S07
glossary.whitespace.term|빈칸만 계속 답함(공백폭주)|S07
glossary.whitespace.meaning|AI가 답 대신 긴 빈칸을 내보내는 상태입니다. 예: 한도에 걸린 답의 공백 비율이 50%를 넘으면 이 상태로 분류합니다.|S07
glossary.repetition.term|같은 답을 계속 되풀이함(반복)|S07
glossary.repetition.meaning|AI가 같은 글을 반복하다 답변 길이 제한에 걸린 상태입니다. 예: 끝부분의 같은 글이 20자 이상이고 4번 이상 이어지면 반복으로 분류합니다.|S07
glossary.model_tag.term|AI 설정의 짧은 이름(모델 태그)|S07
glossary.model_tag.meaning|모델과 접속 설정을 구분하는 이름입니다. 예: 시안의 AI 모델 A는 demo-model-a입니다.|S07
glossary.runpod.term|시간당 요금을 내는 빌린 서버(RunPod)|S07
glossary.runpod.meaning|모델을 켜 둔 시간에 따라 요금을 내는 서버입니다. 예: 시간당 $2.49로 2시간을 쓰면 추정 비용은 $4.98입니다.|S07
glossary.rngd.term|회사에서 쓰는 AI 서버(RNGD)|S07
glossary.rngd.meaning|한 번에 모델 하나를 준비하는 회사 장비입니다. 예: 추가 임대료는 없고 모델 준비에는 보통 15~25분 걸립니다.|S07
glossary.pod.term|빌린 서버 한 대(Pod)|S07
glossary.pod.meaning|RunPod에서 만들어 AI 모델을 실행하는 서버 한 대입니다. 예: 시안의 demo-pod-a는 앱이 만든 서버입니다.|S07
glossary.repeat.term|같은 조건을 반복한 차례(회차)|S07
glossary.repeat.meaning|동일한 조건으로 몇 번째 시험했는지 나타내는 번호입니다. 예: _r2는 두 번째 시험입니다.|S07
glossary.extras.term|표 밖에 남은 값(extras)|S07,S01
glossary.extras.meaning|정해진 결과 칸에 넣지 못해 따로 보관한 값입니다. 예: 표 행 수 비교에는 남은 값 3개도 표시됩니다.|S07
glossary.key_gap.term|정답 초안에서 확인할 빈칸|S07
glossary.key_gap.meaning|정답 자체에서 빠졌거나 검토해야 하는 곳입니다. 예: 시안은 성분 B의 출처 칸 1개를 확인 대상으로 표시합니다.|S07
glossary.concurrency.term|한꺼번에 보내는 AI 요청 수(동시 호출)|S07
glossary.concurrency.meaning|동시에 처리하도록 보낸 요청의 수입니다. 예: 비교 화면의 두 실행은 한 번에 2개씩 보냈습니다.|S07
glossary.rows.term|한 줄에 한 행씩 받는 답(행 형식)|S07
glossary.rows.meaning|표의 열 순서대로 AI가 한 줄씩 답하는 방식입니다. 예: 성분 A &#124; 작업장 기준 &#124; 5 mg/m³|S07
glossary.variation.term|같은 조건에서 생기는 결과 차이(흔들림)|S07
glossary.variation.meaning|같은 조건을 반복해도 점수가 달라지는 현상입니다. 예: 같은 조건의 반복 결과를 두 결과 비교에서 확인합니다.|S07
glossary.exposure.term|작업장 공기의 기준(노출기준)|S07
glossary.exposure.meaning|공기 속 물질이 얼마나 있어도 되는지 정한 값이 허용 농도입니다. 예: 가짜 원문의 성분 A 허용 농도는 5 mg/m³입니다.|S07
glossary.concentration_unit.term|공기 속 물질의 양을 나타내는 단위(mg/m³)|S07
glossary.concentration_unit.meaning|공기 1세제곱미터에 든 물질의 양을 밀리그램으로 나타냅니다. 예: 5 mg/m³는 공기 1세제곱미터에 물질 5밀리그램이 있다는 뜻입니다.|S07
glossary.twa.term|8시간 평균 허용 농도(TWA)|S07 용어 · 말풍선
glossary.twa.meaning|하루 8시간 일할 때 평균으로 넘지 말아야 하는 공기 중 농도입니다. 예: TWA 5 mg/m³는 8시간 평균이 5 mg/m³를 넘지 않아야 한다는 뜻입니다.|S07 용어 · 말풍선
glossary.stel.term|15분 허용 농도(STEL)|S07 용어 · 말풍선
glossary.stel.meaning|짧은 시간(보통 15분) 동안 넘지 말아야 하는 공기 중 농도입니다. 예: STEL 10 mg/m³는 15분 평균이 10 mg/m³를 넘지 않아야 한다는 뜻입니다.|S07 용어 · 말풍선
glossary.acgih.term|미국 산업위생 전문가 협의회(ACGIH)|S07 용어 · 말풍선
glossary.acgih.meaning|작업장 노출기준을 권고하는 미국 단체입니다. 예: 같은 성분에 국내기준과 ACGIH 값이 따로 있을 수 있습니다.|S07 용어 · 말풍선
glossary.ld50.term|실험동물 절반이 죽는 양(LD50)|S07 용어 · 말풍선
glossary.ld50.meaning|먹이거나 피부에 바른 양으로 잰 독성 값입니다. 값이 작을수록 독성이 큽니다. 예: LD50 300 mg/kg은 몸무게 1kg당 300 mg입니다.|S07 용어 · 말풍선
glossary.lc50.term|생물 절반이 죽는 농도(LC50)|S07 용어 · 말풍선
glossary.lc50.meaning|공기나 물에 든 농도로 잰 독성 값입니다. 값이 작을수록 독성이 큽니다. 예: LC50 5 mg/L는 물 1L에 5 mg입니다.|S07 용어 · 말풍선
glossary.ec50.term|생물 절반에 영향을 주는 농도(EC50)|S07 용어 · 말풍선
glossary.ec50.meaning|물벼룩이나 조류 같은 물속 생물의 절반에 영향을 주는 농도입니다. 값이 작을수록 독성이 큽니다. 예: EC50 2 mg/L는 물 1L에 2 mg입니다.|S07 용어 · 말풍선
glossary.stop_order.term|켜 둔 서버를 끄는 순서|S07 용어 · 말풍선
glossary.stop_order.meaning|시험으로 돌아가기는 서버를 끄지 않습니다. 결과를 본 뒤 AI 켜기와 비용에 다시 와서 끕니다. 예: 시험으로 돌아가기 → 결과 확인 → 서버 지우고 요금 멈추기.|S07 용어 · 말풍선

### 표에 없던 키 — 글은 위 표나 UI_TEXT와 같습니다

11/2 step 6에서 모든 키가 자기 행을 갖도록 더했습니다. 안내(`guide.source.image_note`, `guide.ai.steps`, `guide.ai.return_order`, `guide.trial.steps_note`) 넷은 이번 step의 새 글입니다. `guide.screens.G03.lead`, `guide.data.source.change`, `guide.data.answers.change` 셋은 이번 step에 고친 글입니다. 나머지는 글을 바꾸지 않았습니다.

키|글|쓰는 곳
---|---|---
compare.conditions.labels.모델|AI 모델|S04
compare.conditions.labels.입력 판|원문 글자 묶음|S04
compare.criteria.same|같음|S04
compare.prompt.rows|한 줄에 한 행씩 받는 답(행 형식)|S04
compare.values.kind|문제 종류|S04
compare.values.content|기록된 내용|S04
compare.rows.table|표|S04
compare.target_line|목표 점수 {line}점|S04
compare.unknown|확인 안 됨|S04
jobs.result.section|{section}번 부분|S03·S05
jobs.status.failed|실패|S03·S05
jobs.kind.try|한 부분 시험|S03·S05
jobs.kind.compare|비교표|S03·S05
jobs.record.progress|진행|S03·S05
jobs.record.kind|종류|S03·S05
jobs.form.model|AI 모델|S03·S05
jobs.form.doc|문서|S03·S05
jobs.form.section|{section}번 부분|S03·S05
jobs.form.all|문서 전체 · 16개 부분|S03·S05
jobs.form.prompt|AI에게 시킬 일(지시문)|S03·S05
jobs.form.run_name|실행 이름|S03·S05
score.criteria.msds_original|(MSDS 건수)|S01
score.criteria.management_original|(관리정보)|S01
score.criteria.product_original|(제품명)|S01
score.criteria.signal_original|(신호어)|S01
score.criteria.pictogram_original|(그림문자)|S01
score.criteria.hazard_original|(H 코드)|S01
score.criteria.precaution_original|(P 코드)|S01
score.criteria.classification_original|(유해성 분류)|S01
score.criteria.components_original|(구성성분(CAS))|S01
score.criteria.component_fields_original|(구성성분 필드)|S01
score.criteria.content_original|(함유량)|S01
score.criteria.exposure_original|(8번 부분 · 노출기준)|S01
score.criteria.physchem_required_original|(9번 부분 필수 물성)|S01
score.criteria.physchem_other_original|(9번 부분 기타 물성)|S01
score.criteria.acute_original|(11번 부분 급성독성)|S01
score.criteria.toxicity_other_original|(11번 부분 기타 독성)|S01
score.criteria.cmr_original|(11번 부분 CMR)|S01
score.criteria.ecology_original|(12번 부분 생태)|S01
score.criteria.domestic_original|(15번 부분 국내 규제)|S01
score.criteria.regulation_concentration_original|(15번 부분 국내 규제 기준농도)|S01
score.criteria.foreign_original|(15번 부분 해외)|S01
score.criteria.transport_original|(14번 부분 운송)|S01
score.criteria.narrative_original|(서술형)|S01
score.summary.target_line|목표 점수 {line}점|S01
score.basis.fallback|확인 안 됨|S01
score.item_names.MSDS 건수|문서 안 안전자료 수|S01
score.item_names.관리정보|작성일과 개정 정보|S01
score.item_names.제품명|제품과 회사 정보|S01
score.item_names.신호어|위험을 알리는 말|S01
score.item_names.그림문자|위험 표시 그림|S01
score.item_names.H 코드|위험 문구 번호|S01
score.item_names.P 코드|예방 문구 번호|S01
score.item_names.유해성 분류|위험의 종류와 정도|S01
score.item_names.구성성분(CAS)|들어 있는 성분 목록|S01
score.item_names.구성성분 필드|성분 이름과 번호|S01
score.item_names.함유량|성분이 들어 있는 양|S01
score.item_names.8항 노출기준|작업장 공기 중 허용 농도|S01
score.item_names.9항 필수 물성|주요 물리·화학 성질|S01
score.item_names.9항 기타 물성|그 밖의 물리·화학 성질|S01
score.item_names.11항 급성독성|짧은 노출의 독성|S01
score.item_names.11항 기타 독성|그 밖의 독성|S01
score.item_names.11항 CMR|암·유전·생식 관련 독성|S01
score.item_names.12항 생태|환경에 미치는 영향|S01
score.item_names.15항 국내 규제|국내 규제 해당 여부|S01
score.item_names.15항 국내 규제 기준농도|국내 규제의 기준 농도|S01
score.item_names.15항 해외|해외 규제 해당 여부|S01
score.item_names.14항 운송|운송에 필요한 정보|S01
score.item_names.서술형|문장으로 쓰인 설명|S01
score.item_methods.MSDS 건수|자료를 몇 건으로 나눴는지 비교|S01
score.item_methods.관리정보|번호와 날짜와 개정 횟수 비교|S01
score.item_methods.제품명|이름과 긴급 전화 비교|S01
score.item_methods.신호어|위험·경고 같은 말 비교|S01
score.item_methods.그림문자|선택한 위험 그림 종류 비교|S01
score.item_methods.H 코드|위험 문구 번호의 목록 비교|S01
score.item_methods.P 코드|예방 문구 번호의 목록 비교|S01
score.item_methods.유해성 분류|위험 종류와 단계의 짝 비교|S01
score.item_methods.구성성분(CAS)|성분 식별 번호로 목록 비교|S01
score.item_methods.구성성분 필드|성분별 이름과 국내 번호 비교|S01
score.item_methods.함유량|부등호와 수치와 단위 비교|S01
score.item_methods.8항 노출기준|성분과 기준 종류와 수치 비교|S01
score.item_methods.9항 필수 물성|끓는점 등 주요 성질 비교|S01
score.item_methods.9항 기타 물성|색과 냄새 등 나머지 성질 비교|S01
score.item_methods.11항 급성독성|먹음·피부·흡입 독성 비교|S01
score.item_methods.11항 기타 독성|자극과 과민 반응 비교|S01
score.item_methods.11항 CMR|세 종류 독성의 분류 비교|S01
score.item_methods.12항 생태|생물 독성과 분해성 비교|S01
score.item_methods.15항 국내 규제|규제 항목과 해당 여부 비교|S01
score.item_methods.15항 국내 규제 기준농도|규제가 적용되는 농도 비교|S01
score.item_methods.15항 해외|해외 규제 항목과 해당 여부 비교|S01
score.item_methods.14항 운송|운송 번호와 위험 등급 비교|S01
score.item_methods.서술형|응급조치 등 문장의 글자 유사도 비교|S01
score.cause_keys.missing|빠뜨림|S01
score.cause_keys.wrong|틀림|S01
score.cause_keys.made|지어냄|S01
score.cause_names.missing|못 뽑음|S01
score.cause_names.wrong|틀림|S01
score.cause_names.made|없는 값을 만듦|S01
score.actions.retest|이 부분 다시 시험하기|S01
source.empty.pages|원문 쪽 자료가 없습니다. 할 일: 원문이 있는 문서 묶음을 고르세요.|S02
source.empty.lines|이 쪽에는 줄 글자가 없습니다.|S02
source.labels.run|실행|S02
source.labels.doc|문서|S02
source.labels.section|부분|S02
source.labels.page|쪽|S02
source.labels.selected|선택됨|S02
source.kinds.wrong|틀림|S02
source.kinds.made|만듦|S02
source.kinds.missing|못 뽑음|S02
source.kinds.same|정답과 같음|S02
source.section_names.1|제품과 회사|S02
source.section_names.2|위험성|S02
source.section_names.4|응급조치|S02
source.section_names.5|화재 대처|S02
source.section_names.6|누출 대처|S02
source.section_names.7|취급과 저장|S02
source.section_names.8|노출 방지와 보호구|S02
source.section_names.9|물리·화학 성질|S02
source.section_names.10|안정성과 반응|S02
source.section_names.11|독성|S02
source.section_names.12|환경 영향|S02
source.section_names.13|폐기|S02
source.section_names.14|운송|S02
source.section_names.16|그 밖의 정보|S02
source.table_names.components|성분|S02
source.table_names.exposure_limits|노출기준|S02
source.table_names.physchem|물리·화학 성질|S02
source.table_names.toxicity|독성|S02
source.table_names.cmr|암·유전·생식 관련 독성|S02
source.table_names.ecotox|환경에 미치는 영향|S02
source.table_names.transport|운송|S02
source.table_names.regulations|규제|S02
source.table_names.extras|표 밖에 남은 값|S02
source.field_names.q|값|S02
servers.models.connected|연결됨|S06
servers.models.off|AI 꺼짐|S06
servers.models.empty|등록된 모델이 없습니다.|S06
servers.models.tag|AI 설정의 짧은 이름(모델 태그)|S06
journey.band.open|처음 사용 안내 열기|안내
help.settings.runpod_key_name|RUNPOD_VLLM_API_KEY|S07
help.settings.company_url_name|RNGD_BASE_URL|S07
help.navigation.example|예|S07
guide.chapters.1|시작|안내
guide.chapters.5|완료|안내
guide.close.action|안내 닫기|안내
guide.close.cancel|안내 계속하기|안내
guide.screens.G03.lead|1 최근 결과에서 [문제의 원문 보기] → 2 원문 줄 확인 → 3 [이 부분 다시 시험하기]|안내 G03
guide.example.brand|화학 안전문서 AI 결과 검토|안내
guide.example.score_unit|/ 100점|안내
guide.example.answer_label|정답|안내
guide.example.set|문서 묶음|안내
guide.example.document|문서|안내
guide.example.part|부분|안내
guide.example.instruction_title|AI에게 시킬 일|안내
guide.example.ai_title|AI 켜기와 비용|안내
guide.example.model|AI 모델|안내
guide.example.model_duration|15~25분|안내
guide.example.guide_return|안내로 돌아가기|안내
guide.practice_skip|건너뛰기|안내
guide.target|{doc} · {section}번 부분|안내
guide.ready.states.present|있음|안내
guide.ready.states.absent|없음|안내
guide.ready.states.unknown|확인 안 됨|안내
guide.source.key_value|정답|안내
guide.practice.prompt|AI에게 시킬 일|안내
guide.ai.return|안내로 돌아가기|안내
guide.trial.retry|다시 시험|안내
guide.trial.complete|완료|안내
guide.trial.progress|진행 중|안내
guide.skipped|건너뜀|안내
guide.choices.selected|선택됨|안내
guide.source.image_note|원문 맞춰 보기 화면의 그림은 쪽 안의 위치를 확인하는 곳이에요. 글자는 원문 글자 칸에서 읽어요.|안내 G07
guide.ai.steps|AI 켜기 화면은 서버 고르기 → 켜기 → 준비 기다리기 → 쓰고 나서 끄기 순서예요.|안내 G10
guide.ai.return_order|AI가 준비되면 [안내로 돌아가기]를 눌러요. 돌아가도 서버는 꺼지지 않아요. 다 쓴 뒤 그 화면에 다시 와서 꺼요.|안내 G10
guide.trial.steps_note|다시 시험 화면은 무엇을 → 어느 AI로 → 무엇을 시킬지 → 시험 → 결과 순서예요. 이 카드는 앞의 세 단계를 미리 채워 둬요.|안내 G11
guide.data.source.change|두 화면 뒤에서 바로 고를 수 있어요. 안내를 닫은 뒤에는 위쪽 막대의 [문서 묶음]을 눌러요. 그 묶음으로 돌린 저장 결과만 보여요.|안내 G16
guide.data.answers.change|다음 화면에서 바로 고를 수 있어요. 안내를 닫은 뒤에는 위쪽 막대의 [정답]을 눌러요. 저장된 결과를 AI 없이 다시 채점해요.|안내 G17
