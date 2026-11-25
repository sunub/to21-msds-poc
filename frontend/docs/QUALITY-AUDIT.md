# Frontend Quality Audit Report

> **측정 환경 및 투명성 고지 (NOT RUM)**
> 본 문서의 모든 성능·접근성·보안 수치는 실사용자 트래픽(RUM)이 아닌 **로컬 정적 export(`frontend/out`) + 100% 합성 데모 모드(`NEXT_PUBLIC_DEMO_MODE=1`) + Headless Chromium(1440×900, localhost `127.0.0.1:3103`)** 환경에서 직접 계측·검증한 결과다. 원본 기업 PoC 문서·식별자·DB 값은 일체 포함하지 않는다.

---

## 1. 정적 Export 번들 분석 및 `pdfjs-dist` 동적 분할 효과

- **빌드 명령:** 기본 폐쇄망 정적 빌드 (`output: "export"`, `NEXT_PUBLIC_DEMO_MODE` 미설정)
- **데모 코드 제거 검증:** 기본 빌드 `out/_next/static/chunks/` 전체에서 데모 대역 코드(`demoDocumentResponse`, `judgment-mock`, 공개 데모 배너 문구 등) **0건** 확인 (`next.config.ts`의 명시적 기본값 `"0"` + Dead Code Elimination).

### 라우트별 초기 번들 크기 (`out/_next/static/`)

| 라우트 | 초기 JS 청크 수 | 초기 JS (Raw) | 초기 JS (Gzip) | 초기 CSS (Raw / Gzip) | 초기 번들에 `pdfjs-dist` 포함 여부 |
|---|---:|---:|---:|---:|:---:|
| `/` | 15 | 806.2 KB | 251.8 KB | 27.8 KB / 6.6 KB | 미포함 (`false`) |
| `/design-system/` | 12 | 771.9 KB | 239.3 KB | 27.8 KB / 6.6 KB | 미포함 (`false`) |
| `/extract/` | 15 | 781.5 KB | 244.1 KB | 27.8 KB / 6.6 KB | 미포함 (`false`) |
| `/review/` | 16 | 844.6 KB | 261.1 KB | 27.8 KB / 6.6 KB | 미포함 (`false`) |
| `/review/mode/` | 13 | 755.3 KB | 234.6 KB | 27.8 KB / 6.6 KB | 미포함 (`false`) |
| `/save/` | 15 | 778.5 KB | 242.8 KB | 27.8 KB / 6.6 KB | 미포함 (`false`) |

### `pdfjs-dist` 지연 로딩(Dynamic Import) Before → After 정량 비교

`src/components/extract/pdf-viewer.tsx`는 `import("pdfjs-dist")`를 동적 import로 분리하고, 워커·CMap·표준 글꼴·WASM 자산을 `public/pdfjs/`(총 203개 파일, 4.43 MB)에 동봉해 원문 뷰어가 열리는 시점에만 동일 출처로 지연 로드한다.

| 측정 항목 | 정적 번들 포함 시 (Before 추정 기준선) | 동적 Import 적용 후 (After 실측) | 절감 효과 |
|---|---:|---:|---:|
| `pdfjs-dist` 코어 청크 (`dcfbdfdc.*.js`) | 초기 번들 합산 | 지연 청크 분리 (**436.7 KB Raw / 130.6 KB Gzip**) | 초기 파싱 제외 |
| `pdf.worker.min.mjs` (동일 출처 워커) | — | 원문 오픈 시 별도 스레드 로드 (**1,242.1 KB Raw / 371.2 KB Gzip**) | 메인 스레드 분리 |
| `/review/` 초기 JS (Raw / Gzip) | 1,281.3 KB / 391.7 KB | **844.6 KB / 261.1 KB** | **-34.1% Raw / -33.3% Gzip** |
| `/extract/` 초기 JS (Raw / Gzip) | 1,218.2 KB / 374.7 KB | **781.5 KB / 244.1 KB** | **-35.9% Raw / -34.9% Gzip** |
| 비-PDF 라우트 (`/`, `/save/`, `/review/mode/`, `/design-system/`) | 436.7 KB 불필요 로드 | **0 KB 로드** (`pdfjs` 요청 0건) | 100% 회피 |

---

## 2. 웹 접근성 감사 — WCAG 2.2 AA (`@axe-core/playwright`)

- **감사 도구:** Playwright Headless Chromium + `@axe-core/playwright` (`wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa`)
- **대상 범위:** 핵심 11개 화면 상태 (`/`, `/design-system/`, `/extract/` 완료·진행 중, `/review/mode/`, `/review/` 5개 탭 전체, `/save/`)

### 자동 감사에서 포착·수정한 실제 결함 (Before → After)

| 결함 유형 (규칙 ID / 심각도) | Before (최초 감사 적발) | 원인 및 수정 조치 | After (재감사) |
|---|---|---|---|
| `label` (**Critical**) | 2개 라우트 5개 노드 위반 (`/`, `/design-system/`) | `Dropzone` 내부 `sr-only` `<input type="file">`에 접근 가능한 이름 누락 → `aria-label={buttonLabel}` 부여 (`src/components/ui/dropzone.tsx`) | **0건** |
| `color-contrast` (**Serious**) | `/design-system/` 선택 행(`--sel: #eaf3ff`) 위 녹색 상태 라벨(`--grn: #15803d`) 명도 대비 **4.48:1** (기준 4.5:1 미달) | 디자인 토큰 `--grn`을 `#137333`으로 미세 보정 (`src/styles/tokens.css`) → `#eaf3ff` 위 **5.16:1**, 흰 배경 위 **6.02:1** 확보 | **0건** |
| `label-content-name-mismatch` (**Serious**, WCAG 2.5.3) | 6개 라우트 위반 (`PdfViewer` 배율 버튼, `HazardTable`·`RegulationTable` 행 버튼) | 가시 텍스트(`107%`, 표 셀 텍스트)가 `aria-label`에 포함되지 않음 → `PdfViewer` `aria-label`에 현재 배율 포함, 판정 표 행은 중복 `aria-label`을 제거하고 셀 내부 `sr-only` 접두어로 전환 | **0건** |
| WAI-ARIA Tabs 키보드 탐색 (수동·자동 점검) | `UnderlineTabs`에 화살표·`Home`/`End` 키 및 roving `tabIndex` 미구현 | `src/lib/tabs.ts` 순수 로직 + `UnderlineTabs` 키보드 핸들러·roving `tabIndex`·`tabpanel` 연결 추가, 단위 테스트 5건 + 브라우저 키보드 E2E 검증 | **통과** |

- **최종 결과:** 11/11 라우트 전체 **WCAG 2.2 AA 위반 0건** (총 318개 axe 규칙 통과, 콘솔 오류 0건, 페이지 예외 0건).
- **WAI-ARIA Tabs 실브라우저 키보드 검증 (`/review/?doc=DEMO-CHEM-001&tab=hazard`):**
  - 초기 roving `tabindex`: `["0", "-1", "-1", "-1", "-1"]`
  - `ArrowRight` → 포커스 `review-tab-regulation` (`aria-selected="true"`, URL `tab=regulation`)
  - `End` → 포커스 `review-tab-values` (`tab=values`)
  - `Home` → 포커스 `review-tab-hazard` (`tab=hazard`)
  - `ArrowLeft` → 끝으로 순환(`review-tab-values`, `tab=values`)

---

## 3. 보안 헤더(CSP) 및 동일 출처(Air-Gapped) 검증

정적 호스팅용 헤더 정책(`public/_headers`, `vercel.json`)을 로컬 테스트 서버(`127.0.0.1:3103`)에 직접 적용해 브라우저 `securitypolicyviolation` 이벤트를 수집했다.

```text
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; worker-src 'self' blob:; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
```

- **CSP 위반 포착 및 해결 (Before → After):**
  - **Before:** 11/11 라우트에서 `script-src`가 `eval`을 차단하는 `securitypolicyviolation` 1건씩 발생. 원인 추적 결과 **Zod v4의 런타임 JIT(`new Function`) 가용성 프로브**가 엄격한 CSP(`'unsafe-eval'` 미허용)와 충돌함을 확인.
  - **After:** `src/api/schemas.ts` 최상단에 `z.config({ jitless: true })` 적용 → 11/11 라우트 전체 **CSP 위반 0건** 달성.
- **동일 출처 검증:** 11개 라우트 전체 외부 도메인 네트워크 요청 **0건**. `pdfjs-dist` 워커(`/pdfjs/pdf.worker.min.mjs`)와 합성 샘플 PDF(`/demo/sample-msds-synthetic.pdf`) 모두 동일 출처로 로드되어 `<canvas>`(`632×894px`) 및 `.textLayer`(텍스트 스팬 19개) 정상 렌더링 확인.
- **잔존 트레이드오프 투명 표기:** Next.js `output: "export"` 정적 HTML은 서버 nonce 주입이 불가능해 RSC 하이드레이션 인라인 스크립트용 `'unsafe-inline'`과 `pdfjs-dist` WASM 디코더용 `'wasm-unsafe-eval'`을 유지했다. 추후 서버 리버스 프록시/미들웨어 도입 시 nonce 기반 CSP로 강화할 수 있다.

---

## 4. 로컬 Core Web Vitals 및 기능 회귀 검증 (`PerformanceObserver`)

> 주의: 로컬 loopback(`127.0.0.1:3103`) + 합성 API 지연(80~120ms) 환경의 **로컬 벤치마크 수치**이며, 실네트워크 환경의 RUM p75 수치가 아니다.

| 라우트 | LCP (ms) | FCP (ms) | CLS | 전송량 (KB, 비압축 로컬 HTTP) | axe 위반 | CSP 위반 | 외부 요청 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `/` | 28 | 28 | 0.0002 | 906.0 | 0 | 0 | 0 |
| `/design-system/` | 28 | 28 | 0.0000 | 853.7 | 0 | 0 | 0 |
| `/extract/` (완료) | 148 | 32 | 0.0004 | 2,595.4 | 0 | 0 | 0 |
| `/extract/` (진행 중) | 148 | 16 | 0.0016 | 2,581.5 | 0 | 0 | 0 |
| `/review/mode/` | 144 | 32 | 0.0004 | 868.3 | 0 | 0 | 0 |
| `/review/?tab=hazard` | 416 | 16 | 0.0451 | 2,585.7 | 0 | 0 | 0 |
| `/review/?tab=regulation` | 416 | 16 | 0.0451 | 2,585.7 | 0 | 0 | 0 |
| `/review/?tab=components` | 412 | 36 | 0.0451 | 2,585.7 | 0 | 0 | 0 |
| `/review/?tab=history` | 412 | 32 | 0.0727 | 879.3 | 0 | 0 | 0 |
| `/review/?tab=values` | 236 | 16 | 0.0483 | 2,566.5 | 0 | 0 | 0 |
| `/save/` | 408 | 40 | 0.0004 | 896.0 | 0 | 0 | 0 |

- **동시 검토자 충돌(HTTP 409) 시뮬레이션 검증 (`?judgmentMock=conflict`):**
  - 의견 입력란에 초안을 입력한 뒤 `불일치 확정` 클릭 시 409 충돌 경고(`role="alert"`)가 정상 표시되고, 최신 판정 재조회 후에도 작성 중이던 의견 초안이 유실되지 않음(`draftPreserved: true`)을 확인했다.
