# ADR-0001: 폐쇄망 MSDS 검수 프론트엔드 아키텍처 결정 기록

- **상태:** Accepted
- **작성 범위:** `frontend/` (Next.js 16 + React 19 + TypeScript 5.9 + Tailwind CSS v4 + TanStack Query v5 + Zod v4)
- **제약 조건:** 사내 폐쇄망(외부 인터넷·CDN·웹폰트 불가), Node 런타임 없는 단일 FastAPI 정적 서빙, 다중 검토자 동시 검수 안전성, 고객 데이터 비반출(NDA).

---

## 1. `output: "export"` 정적 SPA 채택 vs SSR/RSC 서버 런타임

### 결정
`next.config.ts`에서 `output: "export"`를 고정해 순수 정적 산출물(`frontend/out/`)만 생성하고, FastAPI 백엔드가 동일 출처(`/api/...`)로 정적 파일과 API를 함께 서빙한다. 문서 식별자와 탭 상태는 동적 경로(`/review/[id]`) 대신 쿼리 파라미터(`?doc=...&tab=...&finding=...`)로 표현한다.

### 검토한 대안
- **Next.js Node 서버(SSR/RSC) 병행 운영:** 서버 사이드 렌더링과 nonce 기반 CSP는 유리하지만, 폐쇄망 반입 시 Node 런타임 프로세스·리버스 프록시 관리가 추가되고 사내 배포 단위가 이원화된다.
- **Vite + React Router SPA:** 빌드 구성은 단순하지만 Next.js App Router의 파일 기반 정적 프리렌더와 정적 export 파이프라인을 그대로 활용하는 편이 팀 표준에 맞았다.

### 트레이드오프 및 보완
- 정적 export에서는 `next.config.ts`의 `headers()`가 실행되지 않으므로, 공개 쇼케이스 정적 호스팅을 위해 `public/_headers` 및 `vercel.json`에 보안 헤더(CSP, `X-Frame-Options`, `X-Content-Type-Options`)를 별도 선언했다.
- 정적 HTML의 RSC 하이드레이션 인라인 스크립트 특성상 `script-src`에 `'unsafe-inline'`이 필요하다. 대신 외부 스크립트·객체·프레임 삽입(`object-src 'none'`, `frame-ancestors 'none'`, `connect-src 'self'`)을 엄격히 차단하고 Zod v4 `jitless` 설정으로 `eval` 시도를 완전히 제거했다.
- 공개 쇼케이스용 합성 데모는 `NEXT_PUBLIC_DEMO_MODE=1` 빌드 플래그로 분리하고, 기본값을 `next.config.ts`의 `env`에 `"0"`으로 고정해 기본 폐쇄망 빌드에서는 데모 대역 모듈이 100% 트리 쉐이킹되도록 보장했다.

---

## 2. `requestJson` + Zod v4 런타임 계약 경계 (`ApiContractError` vs `ApiRequestError`)

### 결정
모든 API 응답은 `src/api/client.ts`의 `requestJson`을 거쳐 Zod v4 스키마(`src/api/schemas.ts`, `judgment.ts`, `save.ts`, `history.ts`)로 런타임 파싱한 뒤에만 UI에 전달한다. TypeScript 타입은 수기 작성하지 않고 `z.infer`로 단일화한다.

### 설계 근거
- **오류 원인 즉시 분리:** HTTP 4xx/5xx 거절은 `ApiRequestError`로, 200 응답이지만 계약 형태가 어긋난 경우는 `ApiContractError`(위반 경로 포함)로 구분한다.
- **교차 필드 불변식 검사:** `judgmentViewSchema.superRefine`으로 모든 `finding.id`에 대응하는 `display[finding.id]`가 존재하는지 검증해, 일부 표시 문장이 누락된 반쪽짜리 표가 렌더링되는 침묵 실패를 차단한다.
- **영구 오류 폴링 중단:** `isPermanentError`가 4xx와 `ApiContractError`를 영구 실패로 판별해 TanStack Query `refetchInterval` 폴링을 즉시 멈춘다(5xx·네트워크 단절은 자동 복구 폴링 유지).
- **엄격한 CSP 호환:** `z.config({ jitless: true })`를 전역 적용해 Zod v4의 `new Function` JIT 프로브로 인한 `script-src` CSP 위반을 0건으로 유지한다.

---

## 3. `JudgmentGate` 순수 상태 분기 (`src/lib/judgment-gate.ts`)

### 결정
판정 API를 읽는 모든 탭(2항·15항·성분별 요약·저장) 앞에 `JudgmentGate`를 두고, 화면 분기 규칙을 순수 함수 `gateView(doc, status, isApiMissing)`로 분리해 단위 테스트(`judgment-gate.test.ts`)로 고정했다.

### 설계 근거
- **위험한 오판("이상 없음 0건") 방지:** 추출 미완료(`not-extracted`), 판정 서버 미연결(`not-connected`, 404), 판정 실패(`failed`), 판정 실행 중(`judging`), 버전 누락 상태를 명시적으로 구분한다. 백엔드가 연결되지 않았거나 실패했을 때 빈 목록을 "불일치 0건"으로 오인하는 사고를 원천 차단한다.
- **조회 중 버전 고정:** 판정 화면은 처음 연 `version`을 고정하고, 추출값 수정으로 재판정(`pending_handoff !== null`)이 진행 중이거나 더 최신 버전이 생기면 상단 배너로 알리며 처리 버튼만 잠근다. 읽던 표가 사용자 의도와 무관하게 갑자기 바뀌지 않는다.

---

## 4. 동시 검토자 낙관적 잠금(`seen_version` · `seen_event_id`)과 직렬화 쓰기

### 결정
- 판정 처리 요청(`ReviewEventRequest`)마다 화면이 조회한 `seen_version`과 해당 행의 마지막 이벤트 번호 `seen_event_id`를 함께 전송한다.
- 서버가 `409 Conflict`를 반환하면 `isVersionConflict`로 감지해 관련 판정 쿼리를 즉시 무효화하여 최신 상태를 다시 불러오되, 검토자가 입력 중이던 의견 초안(`regulationDrafts`)은 상위 `ReviewBody` 상태에 유지해 유실을 막는다.
- 추출값 수정(`useReviewWrite`)에는 TanStack Query `scope: { id: "review-${docId}" }`를 지정해 동일 문서의 연속 저장 요청을 직렬화한다. 늦게 도착한 이전 응답이 최신 수정값을 덮어쓰는 경쟁 상태를 방지한다.

---

## 5. 폐쇄망 동일 출처 `pdfjs-dist` 뷰어와 동적 청크 분할

### 결정
- `scripts/copy-pdfjs.mjs`가 `dev`/`build` 전에 `node_modules/pdfjs-dist`에서 `pdf.worker.min.mjs`, `cmaps/`, `standard_fonts/`, `wasm/`, `iccs/`를 `public/pdfjs/`로 동기화해 외부 CDN 의존성을 완전히 제거한다.
- `PdfViewer`는 `pdfjs-dist`를 정적 import하지 않고 문서 오픈 시 `import("pdfjs-dist")`로 동적 로드한다.
- 결과적으로 `/review/` 초기 JS는 **1,281.3 KB → 844.6 KB (-34.1% Raw, -33.3% Gzip)**로 감소했고, 원문 뷰어가 없는 화면(`/`, `/save/`, `/review/mode/`, `/design-system/`)은 `pdfjs-dist`를 전혀 내려받지 않는다.
- 원문 강조는 `devicePixelRatio`를 반영한 `<canvas>` 위에 투명 `TextLayer`를 겹치고, 공백 정규화·다중 스팬 매칭 순수 함수(`src/lib/viewer.ts`)로 줄바꿈에 걸쳐 쪼개진 CAS 번호·문구까지 하이라이트한다.
