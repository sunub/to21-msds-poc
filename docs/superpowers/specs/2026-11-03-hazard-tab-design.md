# 2항 유해성·위험성 탭: 분석과 연결 지점

작성 2026-11-03 · 근거: `cowork/6-screens.md`, `docs/superpowers/specs/contracts/`, 시안 `frontend/templates/2.3 검수 · 2항 판정-html`, PR #133과 그 뒤 `f/compliance` 커밋(`0d90e8b`, `3686db8`) · 15항은 `2026-11-03-judgment-connection-analysis.md` 참고

## 1. 무엇이 어긋나 있었나

- 이 탭은 추출 화면이 아니라 검수 화면 `app/review/page.tsx?tab=hazard`에 있다.
- 이전 화면 `hazard-results.tsx`는 모델 추출값(`/result`의 `hazard`)을 나열했다. 의도한 화면은 MSDS 기재와 검증 결과를 비교한 **판정 검수**(시안 2.3)다.

| | 이전 | 시안·계약 (지금) |
|---|---|---|
| 데이터 | `GET /api/documents/{id}/result` | `GET /api/judgments/{job_id}` → `judgment_view` |
| 표 | 분류·문구 목록 | 유해성 항목 · MSDS 기재 · 검증 결과 · 판정 방법 · 판정 |
| 상세 | 없음 | 값 비교, 설명, 판단 근거·계산 과정, 불일치 확정·예외 승인·의견 |
| 원문 | 2항 쪽 버튼 | 판정마다 근거 쪽 (`2항 p.1`, `11항 p.2`) |
| 끝 | 비활성 저장 버튼 | 추출값 확인 · 15항 판정 보기 |

## 2. 시안과 칸 대응

| 시안 영역 | 칸 |
|---|---|
| 건수 알약 | 2항 `findings`를 `verdict`로 센다. 전체에서 참고·범위 외는 뺀다. 경고는 있을 때만 보인다 |
| 표 | `label`, `display.msds`, `display.expected`, `method`, `verdict`·`type`·`severity`, `reviews` |
| 일치·범위 외 묶음 | `verdict`, `out_of_scope_reason` |
| 값 칩 | `display.msds` → `display.expected`. 불일치만 틀린 값(빨강 취소선)과 맞는 값(초록)으로 가른다 |
| 설명 | `explanations[id]`. 검사를 통과하지 못한 설명은 보이지 않는다 |
| 근거 | `display.basis_lines`, `display.calc_lines`, `expected.source` |
| 원문 쪽 | `display.source_pages`, `msds.evidence[0].source_text` |
| 처리 | `POST /api/judgments/{job_id}/reviews` (`seen_version`, 409) |
| 리포트 | `POST /api/judgments/{job_id}/reports` (`report_request`, 응답은 파일) |

## 3. 연결 방법

서버는 main에 들어와 있다. `api/judge_app.py`가 `contracts/5-api` 모양으로 `/api/judgments/*`를 내고, `compliance/judge.py`가 엔진 결과를 `consistency/2`로 옮긴다. 추출 앱에 함께 띄우려면 `MSDS_JUDGE_IN_EXTRACT_APP=1`을 켠다. 꺼져 있으면 경로가 404라 `JudgmentGate`가 "연결 전"을 보여 준다. 개발 서버에서는 `&judgmentMock=ready`로 가상 판정을 본다.

- 화면: `components/review/hazard/` (`hazard-tab`, `hazard-detail`, `hazard-table`)
- 규칙: `lib/hazard.ts` (시험 `hazard.test.ts`), 처리 대상·정렬·문구는 `lib/regulation.ts`와 같다
- 리포트: `api/judgment-report.ts`
- 대역: `api/judgment-mock.ts`의 `HAZARD_MIX`. 값은 모두 가상이다

## 4. 서버 모양

API-12·13 모양(`compliance/api_view.py`)과 `contracts/` 모양 중 서버는 `contracts/`로 만들어졌다. 그래서 `api/judgment.ts`의 연결부를 바꾸지 않아도 된다.

- finding ID는 내용 기반이다 (`m0/F2:HH_ACUTE_INHAL:분진·미스트`). 다시 판정해도 검토 이력이 같은 줄에 붙는다.
- 표시 요소는 코드별 한 줄이다 (`F2L:H:H314`, `F2L:SIGNAL`).
- 화면 zod는 계약의 값 목록보다 좁았다. `해외 규제`, `구버전 제외`, `해외`, `내부 불일치`, `화평법 항목 누락`이 오면 응답 전체가 거부되므로 계약에 맞춰 넓혔다.

확인한 것: 계약 샘플 `judgment_view.json`, `judgment_status.json`이 화면 zod를 통과한다. 확인하지 않은 것: 실제 서버 응답, 리포트 내려받기, 검토 저장·409.

**지식DB 장애:** 연결이 안 되면 엔진은 멈추지 않고 근거부족을 낼 수 있다. 2항이 평범한 근거부족처럼 보이지 않는지 실제 서버로 확인해야 한다.

## 5. 다음 순서

1. `MSDS_JUDGE_IN_EXTRACT_APP=1`로 띄워 실제 판정 응답이 2항 탭을 통과하는지 확인한다.
2. 검토 저장과 409, 리포트 내려받기를 실제 서버로 확인한다.
3. `해외` 법령 줄과 `해외 규제` 사유가 화면에 어떻게 보여야 하는지 시안과 맞춘다. 지금은 값을 받아 그대로 보여 주기만 한다.

## 6. 함께 볼 것

- `e/frontend-review`(E, PR 없음)에도 2항 패널(`components/review/hazard/`)과 계약→화면 변환 계층(`api/adapt/`)이 있다. 경로와 역할이 겹치므로 병합 전에 어느 쪽을 기준으로 할지 정해야 한다.
- 리포트의 `include`는 재생성 MSDS만 빼고 모두 켰다. 시안에 정해진 값이 없어 잠정으로 고른 값이다.
