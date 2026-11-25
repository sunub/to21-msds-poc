# MSDS 검수 프론트엔드 (`frontend/`)

폐쇄망(Air-Gapped) 환경에서 화학물질 MSDS PDF의 추출 진행 확인, 원문 대조 검수(2항 유해성·위험성 / 15항 법적 규제 / 성분별 요약 / 추출값), 검토 이력 추적, 스냅샷 저장을 수행하는 정적 SPA 프론트엔드입니다.

---

## 문제 정의와 제약 조건

- **해결 대상:** 안전·규제 검토자가 수십 쪽 분량의 MSDS PDF 원문과 AI 추출값·법령 정합성 판정 결과를 대조하며 발생하는 누락·오판("연결 실패를 이상 없음으로 착각", "동시 검토 덮어쓰기", "원문 근거 탐색 병목")을 UI 계층에서 구조적으로 차단합니다.
- **운용 제약:** 외부 인터넷·CDN·웹폰트 접근 불가(폐쇄망), 별도 Node SSR 서버 없이 FastAPI가 정적 산출물(`out/`)을 단일 출처로 서빙.

---

## 기여 범위 (개인 vs 팀 협업)

| 구분 | 범위 | 핵심 구현 내용 |
|---|---|---|
| **개인 기여 (`sunub`, `frontend/` 30/40 커밋)** | FE 아키텍처·디자인 시스템·검수 워크플로우 전반 | CSS 토큰/Tailwind v4 디자인 시스템, Zod v4 런타임 API 계약(`schemas.ts`, `client.ts`), `JudgmentGate` 상태 분기, `seen_version`·`seen_event_id` 409 낙관적 잠금, 폐쇄망 동적 분할 `pdfjs-dist` 원문 뷰어, WAI-ARIA Tabs 키보드 내비게이션, 공개 합성 데모 모드·CSP·품질 감사 |
| **팀원 협업 (`frontend/` 10/40 커밋 + 백엔드)** | 백엔드 추출·정합성 엔진 및 FE 연동 보조 | FastAPI 추출/판정/지식DB API 서버, 추출 검증 알림 연동·GHS 표지 카탈로그 보조 |

---

## 검증된 프론트엔드 품질 지표

> 모든 성능·접근성·보안 지표는 **로컬 정적 export(`out/`) + 100% 합성 데모 모드 + Headless Chromium(1440×900)**에서 실측한 결과이며 실사용자 RUM 데이터가 아닙니다. 상세 기록: [QUALITY-AUDIT.md](./docs/QUALITY-AUDIT.md) · 아키텍처 결정: [ADR-0001](./docs/ADR-0001-frontend-architecture.md)

| 영역 | 지표 / 검증 결과 | 근거 문서·명령 |
|---|---|---|
| **자동화 테스트** | **13개 테스트 파일 · 107개 케이스 100% 통과** (`src/lib/*.test.ts` 12개 102건 + `tests/a2-validation.test.cjs` 5건) | `pnpm test` · `node --test tests/a2-validation.test.cjs` |
| **번들 분할 (`pdfjs-dist`)** | `/review/` 초기 JS **1,281.3 KB → 844.6 KB (-34.1% Raw / -33.3% Gzip)**, 비-PDF 라우트 `pdfjs` 로드 **0 KB** | [QUALITY-AUDIT.md §1](./docs/QUALITY-AUDIT.md#1-정적-export-번들-분석-및-pdfjs-dist-동적-분할-효과) |
| **WCAG 2.2 AA (`axe-core`)** | 11개 핵심 화면 감사: **Before 9건 위반(Critical 1종·Serious 2종) → After 0건 위반** (318개 규칙 통과) + WAI-ARIA Tabs 키보드(`ArrowLeft/Right/Home/End`, roving `tabIndex`) 검증 | [QUALITY-AUDIT.md §2](./docs/QUALITY-AUDIT.md#2-웹-접근성-감사--wcag-22-aa-axe-coreplaywright) |
| **보안 경계 (CSP & 동일 출처)** | 정적 CSP(`public/_headers`, `vercel.json`) 적용 후 Zod v4 `jitless` 전환으로 **CSP 위반 11/11 → 0/11**, 외부 네트워크 요청 **0건** | [QUALITY-AUDIT.md §3](./docs/QUALITY-AUDIT.md#3-보안-헤더csp-및-동일-출처air-gapped-검증) |
| **로컬 CWV (11개 라우트)** | LCP **28~416 ms**, FCP **16~40 ms**, CLS **0.0000~0.0727**, 콘솔/페이지 오류 **0건** | [QUALITY-AUDIT.md §4](./docs/QUALITY-AUDIT.md#4-로컬-core-web-vitals-및-기능-회귀-검증-performanceobserver) |
| **CI 가드레일** | NDA 식별자 차단, 타입체크, 단위/검증 테스트, 기본·데모 이중 빌드, 기본 빌드 내 데모 코드 0건 검사, `pnpm audit --prod` | [`.github/workflows/frontend-ci.yml`](../.github/workflows/frontend-ci.yml) |

---

## 실행 및 빌드 방법

요구 환경: Node.js 24 (`frontend/.nvmrc`), pnpm 10.32 (`packageManager`).

```bash
cd frontend
pnpm install --frozen-lockfile

# 1. 타입 체크 & 자동화 테스트 (13개 파일 / 107개 테스트)
pnpm run typecheck
pnpm run test
node --test tests/a2-validation.test.cjs

# 2. 기본 폐쇄망(온프레미스) 정적 빌드 — 데모 대역 코드 0% 포함
pnpm run build

# 3. 공개 쇼케이스용 합성 데모 정적 빌드 — 백엔드 없이 독립 실행
NEXT_PUBLIC_DEMO_MODE=1 pnpm run build

# 4. 서브경로 정적 호스팅(예: GitHub Pages)용 공개 데모 빌드
NEXT_PUBLIC_DEMO_MODE=1 NEXT_PUBLIC_BASE_PATH=/msds-demo pnpm run build
```

### 공개 데모 시나리오 (`NEXT_PUBLIC_DEMO_MODE=1`)

정적 `out/` 디렉터리를 로컬 HTTP 서버로 열면 백엔드 없이 전체 화면을 체험할 수 있습니다. 상단 배너 또는 URL 쿼리(`?judgmentMock=...`)로 다음 시나리오를 즉시 전환할 수 있습니다.

- `ready`: 혼합물(가상물질 A·B) 2항/15항 판정, 원문 PDF 렌더링(`public/demo/sample-msds-synthetic.pdf`), 추출값 수정 및 저장
- `conflict`: 동시 검토자 `409 Conflict` 낙관적 잠금 시뮬레이션(작성 중 의견 초안 보존 확인)
- `stale`: 재판정으로 기존 검토가 무효화된 상태 확인
- `single`: 단일물질 기준 요약 및 판정 보기

---

## NDA 및 데이터 투명성 고지

- 본 `frontend/` 디렉터리와 공개 데모 빌드에는 **원본 기업 PoC PDF, 문서 식별자, 실제 제품명·성분 수치, 외부 상용 DB 데이터가 일체 포함되지 않습니다.**
- 데모 모드에 사용되는 문서 목록, 추출값, 2항·15항 판정, 2쪽 분량 샘플 PDF(`public/demo/sample-msds-synthetic.pdf`)는 모두 UI·계약 검증을 위해 새로 작성한 **100% 합성 데이터**입니다.
- CI 워크플로우(`.github/workflows/frontend-ci.yml`)가 매 푸시·PR마다 `frontend/src/` 및 `frontend/public/`의 식별자 유입과 기본 빌드의 데모 코드 잔존 여부를 자동으로 차단합니다.
