# 화면별로 필요한 데이터와 API

작성 2026-11-02 · 상태: 승인 전

`frontend/src/app/`의 화면, `frontend/templates/`의 목업(1.1~2.4), 화면 코드 안의 "…가 들어올 자리" 메모를 대조해 화면마다 필요한 데이터를 정리했다.
- **기존**: 지금 `frontend/src/api/schemas.ts`(zod)에 있고 `api/extract_app.py`가 이미 준다.
- **추가**: 기존 응답에 칸을 더한다.
- **신규**: 새 경로다.

스키마 위치는 `5-api.schema.json#/$defs/<이름>` 형태로 적는다. 판정 데이터의 본체는 `3-consistency.schema.json`이다.

## 0. 공통: 머리줄 · 단계 띠 · 요약 줄 (`components/shell`, 모든 문서 화면)

목업 예: `T21-025 황산 MSDS · KZ-A-S004 · 14쪽 · 실버 · 미검수`, 단계 띠 `1 추출 · 완료 / 2 검수 · 추출값 확인 건너뜀 · 판정 확인 중 / 3 저장`, 요약 줄 `개정일 2022-06-29 · 혼합물(성분 2) · 기준일 2026-10-31 · 지식 reference / ref-2026.10`

| 화면에 찍는 것 | 출처 | 상태 |
|---|---|---|
| 문서 번호, 파일 이름, 쪽 수, 기준일, 작업 상태·단계 | `GET /api/documents/{id}` → `documentDetailSchema` | 기존 |
| 제품명, 문서 코드, 개정일, 혼합물(성분 수), 추출값 검수 상태(미검수/일부/완료, 확인 n/전체) | 같은 응답 + `document_extras` | 추가 [A2] |
| 대기 순번, 예상 시간, 사람 구간 상태(검수 대기/추출값 확인 중/판정으로 넘김) | 같은 응답 + `queue_fields` | 추가 [A1·A2] |
| 판정 상태(판정 중/있음), 미검토 수, 데이터 등급(실버/골드), 저장 여부 | `GET /api/judgments/{job_id}/status` → `judgment_status`, 등급은 `judgment_batch_item.data_grade` | 신규 [B2] |
| 지식 provider·version | 판정 보기의 `consistency.knowledge` | 신규 [B2] |
| 검토자 이름 | 브라우저 localStorage (`lib/reviewer.ts`). 서버에서 받지 않음 | 기존 |

## 1.1 목록 (`app/page.tsx`)

| 화면에 찍는 것 | 출처 | 상태 |
|---|---|---|
| 업로드(PDF, 기준일) | `POST /api/documents` | 기존 |
| 작업한 문서 표: 문서·쪽 수·마지막 작업, 보기 전환 개수 | `GET /api/documents?status=` → `documentListResponseSchema` | 기존 |
| 문서 칸의 제품명·문서 코드 | `items[]` + `document_extras` | 추가 [A2] |
| 단계 칸: `추출 중 3/4단계` · `검수 중 · 미검수` · `완료`, 진행 칸 `9 / 9항` | A: `status`·`stage_index`·`counts` / B: `judgment_batch_item` | 기존 + 신규 [B2] |
| 데이터 등급 칸 `실버`/`골드` | `judgment_batch_item.data_grade` | 신규 [B2] (미결 2) |
| 버튼: 진행 보기 / 이어서 하기 / 열기 | 화면이 A 상태와 B 상태를 합쳐 정한다 (아래 규칙) | — |
| 대기 순번·예상 시간 | `queue_fields` | 추가 [A1] |

목록은 A의 `GET /api/documents` 한 번과 B의 `GET /api/judgments/summary?job_ids=…` 한 번으로 그린다. 두 응답은 `job_id`(= A의 `id`)로 합친다. A와 B가 서로를 부르지 않게 하려고 합치는 일은 화면이 맡는다.

| A `status` | B `state` / 저장 | 단계 칸 | 버튼 |
|---|---|---|---|
| queued·running | — | 추출 중 n/4단계 (대기 중이면 대기 n번째) | 진행 보기 |
| failed·interrupted | — | 실패 | 진행 보기 (다시 실행) |
| done | 저장본 없음 | 검수 중 · (미검수/일부/완료) | 이어서 하기 |
| done | 저장본 있음 | 완료 | 열기 |

## 1.2 · 1.3 추출 진행 (`app/extract/page.tsx`)

| 화면에 찍는 것 | 출처 | 상태 |
|---|---|---|
| 단계 n/4, 쪽 수 확인 중, 전처리 진행, 항별 상태(대기/추출 중/완료/실패), 경고 | `GET /api/documents/{id}` (1~2초 폴링) | 기존 |
| 원문 쪽 이미지·줄 | `GET …/pages/{n}/image`, `…/pages/{n}/lines` | 기존 |
| 대기 n번째 · 약 n분 | `queue_fields` | 추가 [A1] |
| 단계에 `checks`(검증) 추가 | `jobStageSchema`에 `checks`, `stage_total` 4 → 5 | 변경 [A2] (약속 ②) |

목업 1.3은 "쪽별 상태"지만 지금 화면과 서버는 항별 상태로 바꿔 두었다(`schemas.ts` 머리 주석). 이 결정을 유지한다.

## 2.1 방식 선택 (`app/review/mode/page.tsx`)

| 화면에 찍는 것 | 출처 | 상태 |
|---|---|---|
| 입력 유형, 권장 방식 | `text_layer` → `lib/status.ts inputType()` | 기존 |
| 추출 상태 (n개 항 중 완료·실패·검토 필요) | `counts` | 기존 |
| 고른 방식 기억 (다시 열 때 이어서) | `queue_fields.review_stage`. "추출값 확인 시작하기"를 누르면 `추출값 확인 중`이 된다 | 추가 [A2] |

## 2.2 추출값 확인 (`components/review/values-panel.tsx`)

| 화면에 찍는 것 | 출처 | 상태 |
|---|---|---|
| 재생성 MSDS, 항별 확인 상태, 칸 값·원래 값·확인함/수정됨·근거 쪽 | `GET /api/documents/{id}/review`, `…/regenerated` | 기존 |
| 칸 확인·수정·되돌림, 항 확인 | `PUT …/review/fields`, `PUT …/review/sections` | 기존 |
| 칸의 `신뢰도 낮음`·`검사 실패` 표시와 문장 | `reviewField` + `review_field_extras` | 추가 [A2] |
| "2항 판정으로 가기" | `POST /api/documents/{id}/to-judgment` → `to_judgment_request`/`to_judgment_response`. 응답을 받은 뒤 판정 화면으로 간다 | 신규 [A2] |

판정 검수 화면의 "추출값" 탭에서 칸을 고치면, 기존 `PUT …/review/fields`가 넘김②를 자동으로 만든다. 그 뒤 화면은 `judgment_status.pending_handoff`가 비워질 때까지(새 판정 버전이 생길 때까지) 판정 탭에 "다시 판정하는 중"을 띄운다.

## 2.3 검수 · 2항 판정 (`app/review/page.tsx?tab=hazard`)

데이터 한 번: `GET /api/judgments/{job_id}` → `judgment_view` (최신 판정 버전). 판정이 아직이면 먼저 `judgment_status`를 폴링한다.

| 목업 영역 | 쓰는 칸 |
|---|---|
| 건수 알약 `전체 9 · 불일치 1 · 경계 0 · 근거부족 2 · 경고 1 · 일치 5` | `consistency.results[m].summary` (2항 finding만 화면이 다시 세거나 `save_overview.verdicts.by_section`) |
| 표: 유해성 항목 · MSDS 기재 · 검증 결과 · 판정 방법 · 판정(+심각도) | finding `label`, `display.msds`, `display.expected`, `method`, `verdict`·`severity`·`type` |
| `▸ 일치 5건 (펼치기)`, `범위 외 · 비교 제외 7건 (해당 없음 5 · 대조 2)` | `verdict` = 일치 / 범위 외 + `out_of_scope_reason` |
| 상세 머리 `급성 독성 (흡입) · 불일치 · 중간`, 값 칩 `증기 → 미스트` | finding `label`·`verdict`·`severity`, `msds.route_form` → `expected.route_form` (또는 `display`) |
| AI 설명 + `검사 ✓` | `explanations[id]` (`status` 작성 중/완료, `by`, `checked`) |
| 판단 근거와 계산 과정 | `display.basis_lines`, `display.calc_lines` (원본은 `consistency.traces[trace_id]`) |
| 원문 탭 `2항 p.4 · 11항 p.9` | `display.source_pages` → 기존 쪽 이미지·줄 API |
| 불일치 확정 · 예외 승인 버튼, 현재 처리 상태 | `reviews[id]` (`status`, `stale`) / 누르면 `POST /api/judgments/{job_id}/reviews` → `review_event_request` |
| 리포트 (HTML) · (Excel) | `POST /api/judgments/{job_id}/reports` → `report_request` (`format` html·xlsx) |
| 하단 "추출값 검수를 건너뛰었습니다" | `document_extras.values_review.state` = 미검수 |

## 2.4 검수 · 15항 법적 규제 (`?tab=regulation`)

2.3과 같은 `judgment_view`를 `section = "15"`인 finding으로 거른다.

| 목업 영역 | 쓰는 칸 |
|---|---|
| 법령 거르기 `전체 · 산안법 · 화관법 · 화평법 · 위험물법 · 불일치만` | finding `law_label`, `verdict` |
| 표: 법령 · 규제 항목 · 성분(함량) · MSDS 기재 · 규제DB 결과(기준) · 판정 | `law_label`, `label`, `display.component`, `display.msds`, `display.expected`, `verdict`·`type`·`severity` |
| `▸ 물 (7732-18-5, 2~7%): 모든 항목 비해당 — 일치 (펼치기)` | `comp`별로 묶어 모든 finding이 일치면 접는다 (화면 규칙) |
| 상세의 `구버전 · 시행 2025-01-01` | `type` = 구버전, `expected.effective_from` (미결 1) |
| 판단 근거 `황산 93~98% ≥ 10% → 해당` | `display.basis_lines` |

## 성분별 요약 탭 (`?tab=components`, 목업 없음 · 설계서 v0.4 화면 예시 ④)

| 화면 메모 | 쓰는 칸 |
|---|---|
| 구성성분별 판단 요약 표: 성분 · CAS · 함량 · 기준 분류(출처) · 사용 ATE(단계) · 15항 해당 · 자료 | `consistency.results[m].components[]` (`name`, `cas`, `content`, `reference_classes`, `ate`, `regulation_hits`, `reliability`) |
| 성분 상세 (ATE를 가져온 순서, 단일물질이면 기준 분류 비교) | `components[].notes`, 해당 성분 finding의 trace |
| 제약사항 · 검토 필요 | `consistency.results[m].limitations[]` |

## 검토 이력 탭 (`?tab=history`, 목업 없음)

| 화면 메모 | 출처 |
|---|---|
| 처리하지 않은 판정 | `save_overview.reviews.unreviewed_ids` 또는 `judgment_view.reviews`에서 미검토 |
| 이력 표: 시각 · 검토자 · 구분 · 대상 · 처리 내용 · 의견 | `GET /api/documents/{id}/review/log` [A2, 신규] + `GET /api/judgments/{job_id}/history` [B2, 신규]. 둘 다 `history_entry[]`. 화면이 `at`으로 합쳐 정렬한다 |

## 2.5 저장 전 경고 (`components/review/save-guard-dialog.tsx`)

| 화면 메모 | 쓰는 칸 |
|---|---|
| 미검토 판정 목록 | `save_overview.reviews.unreviewed_ids` + `judgment_view`의 `label` |
| "미검토로 두고 저장하기" | 저장 화면으로 이동. 실제 저장은 저장 화면에서 한다 |

## 3.1~3.2 저장 (`app/save/page.tsx`, 목업 없음)

데이터 한 번: `GET /api/judgments/{job_id}/save-overview` → `save_overview`

| 화면 메모 | 쓰는 칸 |
|---|---|
| 2차 판정 요약과 처리 상태 (판정 건수, 미검토·처리 건수, 추출값 검수 여부) | `verdicts`, `reviews`, `values.state` |
| 데이터베이스에 저장: 저장 상태, 저장 시각, 값의 출처별 칸 수, 다시 저장 | `snapshots[0]`(`saved_at`, `counts`), `values`(`model_as_is`·`confirmed`·`edited`) / 저장 `POST /api/judgments/{job_id}/snapshots` → `save_request` → `snapshot` |
| JSON 내려받기 | `report_request` `format: json` (저장본 + 추출값 + 판정 + 검토) |
| PDF로 출력: 구성·포함 항목 선택·미리 보기 | `report_request` `format: pdf`, `include` / 미리 보기는 `format: html`에 `snapshot_no: null` |

## 화면 쪽에서 고칠 것 (`frontend/src/api/schemas.ts`)
- `jobStageSchema`에 `checks`를 넣고 `stage_index`·`stage_total`을 5단계로 바꾼다 (약속 ②).
- `documentSummarySchema`에 `document_extras`·`queue_fields`를 더한다.
- `reviewFieldSchema`에 `review_field_extras`를 더한다.
- 판정 쪽 zod(`judgment.ts` 새 파일)를 `3-consistency`·`5-api`에서 옮긴다. `contracts/` 견본을 zod로 파싱하는 시험을 둔다 (스키마와 zod가 따로 놀지 않게).

## 미결 (사용자 확인 필요)
1. **구버전 판정**: 목업 2.4는 "구버전 · 시행 2025-01-01"을 보여주지만, 설계서 v0.4 D-09는 "항목별 시행일이 DB에 없어 PoC 제외"다. 스키마는 `type: 구버전`과 `effective_from`을 열어 두고, PoC에서는 채우지 않는 것으로 두었다.
2. **데이터 등급 실버/골드**: 목업 1.1의 "데이터 등급"을 "실버 = 모델 추출 그대로, 골드 = 최신 저장본이 미검수 칸 0·미검토 0"으로 정했다 (Claude 판단). 기준이 다르면 `judgment_batch_item.data_grade` 설명만 바꾸면 된다.
3. 목업 2.2·1.1의 "16항" 표기는 지금 추출 대상 9개 항으로 이미 바뀌어 있다 (커밋 22598f5). 목업을 따르지 않는다.
