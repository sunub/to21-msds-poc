# 요구 추적표 (B1·B2)

작업을 끝낼 때 상태를 고친다. 상태: 완료 / 일부 / 대역(상대 역할 대기) / 미구현. 시험 파일은 `backend/tests/` 기준.

## 개요 · 나누기 문서

| 요구 | 근거 | 코드 | 시험 | 상태 |
|---|---|---|---|---|
| `judge(extraction, as_of, provider)` 상태 없음, DB에 안 씀 | 나누기 B1 | `compliance/judge.py` | `contracts/test_3_consistency.py` | 완료 |
| finding ID를 내용으로 (순번 무관) | 계약 README 3절 | `judge.py` | `test_성분_순번이_바뀌어도…`, `test_같은_CAS_두_줄…` | 완료 (CAS·이름 없는 성분은 B-19 예외) |
| 같은 입력·같은 버전이면 바이트까지 같음 | 개요 2·4절 | `judge.py` | `test_같은_입력이면_프로세스와_해시시드…`, 실제 HTODB 2회 | 완료 |
| 한 PDF의 msds 여러 건 | 계약 README 6절 | `judge.py` | `test_한_PDF의_MSDS_여러_건…` | 완료 |
| 추출 실패 항 = 근거부족 | 계약 README 6절 | `_apply_failed` | `test_추출_실패_항…` | 완료 |
| 규칙표·입력 정리~판정 집계 (설계서 47장 1~7단계. 나누기 문서는 48장으로 적음) | 나누기 B1 | 우진 `compliance/*` | `test_F_*`, `test_E_*` | 일부: 차이 목록은 `decisions.md` "엔진 쪽 남은 차이" |
| 설계서 48장 오류 주입 | 설계서 48장 | 우진 엔진 + `judge.py` | `test_설계서_48장_오류_주입…`, `test_F_inject` | 완료 |
| 지식 제공자 교체 (HTODB/CSV) | 설계서 15장 | `provider` 인자 | `test_실제_HTODB로도…` | 일부: `to21` API·3개 함수 경계·config 없음. 적합성은 값 없음·형식·버전만 시험 (Q-03) |
| `ghsclass` 끼움 자리 | 나누기 B1, 파트 B 3절 | 로직 id만 기록 | — | 미구현 (Q-03) |
| 흡입 형태 재지정 D-22 | 설계서 51장, 파트 B 3절 | `consistency._reassign_gas` | `test_액체_물질의…D22`, `test_기체_물질은…D22` | 완료 |
| 시험용 넘김 넣기 | 파트 B 6절 | `POST /_test/handoffs` | `test_시험용_넘김_API는…` | 완료 |
| 칸 수 | 약속 ① `fields_total` | `value_counts` | `test_칸_수는_넘김_기록의…` | 대역: A2 값 미확인 |
| 넘김 표 가져가기, B는 그 표만 읽음 | 개요 6.2 | `claim_handoff` | `test_밀린_넘김…`, `test_계정_권한…` | 대역: 표는 A2 |
| 판정 키로 재계산 안 함 | 개요 6.2 | `_judge_and_store` | `test_확인만_한…`, `test_값을_되돌리면…` | 완료 |
| 판정 버전, 버전 간 차이 | 나누기 B2 | `versions` | `test_값을_고치면…` | 완료 |
| 재시작해도 잃지 않음 | 개요 4절 | `recover` | `test_서버가_죽은_뒤…`, 실서버 kill -9 20건 | 완료 |
| 쓰기 계정 분리 | 개요 5절 | `b2_001`, `b2_002` | `test_계정_권한…` | 완료 (B 쪽) |
| 설명: 숫자 환각 검사, 문장틀 대체, 바뀐 항목만, 창구 뒤쪽 | 나누기 B2 | `judge/explain.py` | `test_모델_설명이…`, `test_모델이_예외를…`, `test_바뀌지_않은…`, `test_검사를_통과한…` | 대역: 실제 모델 미호출, 창구 A1 |
| AI 설명이 엔진과 다른 값을 말하면 안 나감 | 개요 4절 | `check` + `claim_problems` + 문장틀 | `test_모델_설명이…`, `test_설명이_엔진과…` | 일부: 흔한 문장 모양만 본다. 실제 모델 응답 미확인 |
| 검토 이벤트, 이력 보존 | 나누기 B2 | `add_review` | `test_검토는…`, `test_재판정해도…` | 완료 |
| 저장본, 미검토 저장 허용 | 개요 8절 | `save_snapshot` | `test_미검토가_남아도…` | 완료 |
| A 없이 B가 끝까지 돈다 | 개요 7절 | 전체 | 실서버 e2e, `test_넘김_한_건이…` | 완료 |
| 둘을 붙여 업로드 → 저장 | 개요 7절 | — | — | A2 대기 |
| 20건 부하 | 나누기 5절 | 작업자 | 실서버 실버 20~21건, 설명 문장틀 | 일부: 판정만, 모델 미포함 |

## 화면별 (`6-screens.md`)

| 화면 | 경로·칸 | 상태 |
|---|---|---|
| 0 공통 | `/status` (`unreviewed` 포함), `summary.data_grade`, `consistency.knowledge` | 완료 |
| 1.1 목록 | `GET /summary?job_ids=` | 완료 |
| 2.3 2항 | `GET /{job_id}`: finding `label`·`method`·`verdict`, 옆의 `display`·`explanations`·`reviews`, 범위 외 분류 | 완료 |
| 2.3 원문 탭 | `display.source_pages` (2·3·9·11·12·14·15항 근거) | 완료. 추출본에 근거가 없으면 비어 있다 |
| 2.3 처리 | `POST /reviews` | 완료 |
| 2.3 리포트 | `POST /reports` html·xlsx, `include`, 심각도 순, 미검토 수 | 완료 |
| 2.4 15항 | `law_label`, `display.component`, 비교 값 | 완료 |
| 2.4 구버전 표시 | `type: 구버전`, `effective_from` | 미구현 (Q-01, D-09) |
| 성분별 요약 | `components[]`(`component_summary`), `limitations[]` | 일부: ATE는 쓴 단계만 있고 단계별 없음 상태는 없음 (목업 기준) |
| 검토 이력 | `GET /history` (`ref.version`·`ref.in_latest`, 저장 줄 포함) | 완료 (B 쪽) |
| 2.5 저장 전 경고 | `save_overview.reviews.unreviewed_ids` | 완료 |
| 3.1~3.2 저장 | `save-overview`, `POST /snapshots`, json·pdf | 완료 |
| 추출값 수정 뒤 다시 판정 | `pending_handoff` | 완료 (B 쪽) |
| A 쪽 칸 (`document_extras`, `queue_fields`, `review_field_extras`) | main 계약에 있음 | A1·A2 |

## 실행 기록 (시험 파일 밖에서 직접 돌린 것)

| 날짜 | 내용 | 결과 |
|---|---|---|
| 2026-11-02 | 실제 HTODB(`htodb-94f8b6ff7f24`, `HTODB.zip` 해시 일치) + 실서버: 25번 넘김 → 판정 → 검토 → 값 수정 → 새 버전 → 저장 → 리포트 4종 | 통과. 첫 판정 3.1초, 재판정 1.9초 |
| 2026-11-02 | 실버 20~21건 동시 넣기 (설명은 문장틀, 모델 미호출) | 35.2초에 모두 판정 |
| 2026-11-02 | 위 20건 처리 중 서버 kill -9 뒤 재시작 (트랜잭션 수정 후 다시 실행) | 재시작 뒤 26.1초에 20건 모두 판정, 중복 버전 0, 설명 124건 완료, 저장·리포트 4종 정상 (PDF 58KB) |
| 2026-11-02 | 실버 20~21건 PDF의 판정 줄 수 전수 대조 (`test_실버_전체의_PDF…`), 위치를 옮긴 25번 4가지 | 줄 유실 0. 만든 뒤 줄 수 검사가 런타임에도 돈다 |
| 2026-11-02 | 상태·목록 응답 시간 (샘플 CSV, 실버 20~21건) | 목록 요약 20건 258ms, 상태 3ms, 판정 화면 5ms |
| 2026-11-02 | main + f/compliance + B 코드 병합 시험 (B 앱 UI 시험 제외, 2134건) | 2113 통과, 19 건너뜀, 2 실패. 실패는 main에도 있는 `test_E_regenerated` (재생성 스크립트 3.12 문법) |
