/*
 * 판정·저장 임시 서버 (개발용). 계약 5-api(consistency/2)의 판정 경로를 Node 내장 http 만으로 흉내 낸다. 포트 8021.
 *   pnpm mock:judgment
 * 화면에서 쓰려면 프론트를 NEXT_PUBLIC_JUDGMENT_API_BASE=http://127.0.0.1:8021 (추출 쪽 신규 경로도 쓰려면 NEXT_PUBLIC_API_BASE 도 같은 주소) 로 띄운다.
 * CORS 는 localhost 를 허용한다. 이 폴더는 src 밖이라 pnpm build 결과물에 들어가지 않는다.
 *
 * 판정 서버 (B2)
 *   GET  /api/judgments/{job}/status
 *   GET  /api/judgments/{job}?version=N          (없으면 최신)
 *   GET  /api/judgments/{job}/versions
 *   GET  /api/judgments/{job}/history            판정 검토·저장 이력 (최근 것부터)
 *   GET  /api/judgments/{job}/save-overview
 *   GET  /api/judgments/summary?job_ids=a,b,c
 *   POST /api/judgments/{job}/reviews            201 review_event. 낡은 seen_version·seen_event_id 409, 확인·확정 대상이 아닌 판정 422
 *   POST /api/judgments/{job}/snapshots          201 snapshot. 낡은 판정 409. 저장할 때마다 snapshot_no 증가
 *   POST /api/judgments/{job}/reports            html·xlsx·pdf·json 파일 (개발용 내용). 파일 이름 헤더는 filename* 만, html 은 헤더 없음, CORS 로 노출하지 않음 (실제 서버와 같다)
 * 추출 서버 (A) 쪽 신규 칸 — demo 문서만
 *   POST /api/documents/{id}/handoffs            201 {job_id, handoff_seq, as_of, extraction_sha256, validator}. 실제 서버의 넘김 경로. 3초 뒤 새 판정이 생긴다
 *   POST /api/documents/{id}/to-judgment         200 {job_id, handoff_seq}. 계약의 이름 (실제 서버에는 없다)
 *   GET  /api/documents/{id}/review/log          추출값 검수 기록 (history_entry[]). 계약의 A2 경로 (실제 서버에는 아직 없다)
 *   MOCK_NO_A2=1 이면 위 두 계약 경로를 404 로 답한다
 *   MOCK_NO_JUDGE=1 이면 /api/judgments/* 가 404 Not Found (판정 서비스 미연결), MOCK_SUMMARY_FAIL=1 이면 판정 요약만 500
 * 목록 시험 문서 (docs.ts): U-20261103-006 판정 실패 · 005 추출 중 · 004 대기 · 003 실패 · 002 검수 중(판정 없음) · 001 완료(저장본, 골드)
 *   GET  /api/documents, GET /api/documents/{id} queue_fields·document_extras 가 붙은 문서 목록·상세
 *
 * 응답 데이터와 상태 규칙은 이 폴더의 core.ts(서버가 하는 일을 흉내 낸 핵심 함수), 문서는 docs.ts 에 있다.
 * 시작할 때 TypeScript 를 .gen/ 에 옮겨 읽는다. 요청 본문과 응답은 이 폴더의 contract/ (계약 그대로의 strict zod. 화면 src 의 느슨한 zod 와 따로 둔다)로 확인하고,
 * 어긋나면 로그에 이유를 남긴다 (응답이 어긋나면 500).
 *
 * 상황은 job_id 로 가른다 (계약의 job_id 는 U-날짜-순번 이라 demo 계열 이름도 받는다):
 *   demo            판정 있음, 처리 전 (그 밖의 U-… 번호도 같다)
 *   demo-states     설명 작성 중 1건(8초 뒤 완료), 판정이 바뀐(stale) 검토 1건, 판정 중 + 더 새 넘김(pending_handoff)
 *   demo-conflict   읽어 간 판정(버전 1)이 낡는다: 첫 검토·저장 요청은 409, 다시 읽으면 버전 2
 *   demo-savefail   저장이 500 으로 실패한다
 *   demo-pdffail    PDF 리포트가 422(글이 빠진 PDF)로 거절된다
 *   demo-none       아직 판정이 없다 (판정 없음 → 넘김 → 판정 중 → 판정 있음). 판정·저장 개요는 그 전까지 404 "판정이 없음"
 *   demo-single / demo-unknown  단일물질(수소) / 단일·혼합을 판별하지 못함
 * 상태는 서버 메모리에만 있다 (서버를 다시 켜면 사라진다).
 */
import fs from "node:fs";
import http from "node:http";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");
const PORT = Number(process.env.PORT ?? 8021);
/** MOCK_NO_A2=1: 추출 서버에 아직 없는 계약 경로(review/log, to-judgment)를 404 로 답한다 */
const NO_A2 = process.env.MOCK_NO_A2 === "1";
/** MOCK_NO_JUDGE=1: 판정 서비스가 없는 서버(/api/judgments/* 가 404 Not Found). MOCK_SUMMARY_FAIL=1: 목록의 판정 요약만 500 */
const NO_JUDGE = process.env.MOCK_NO_JUDGE === "1";
const SUMMARY_FAIL = process.env.MOCK_SUMMARY_FAIL === "1";

/* ── 프론트의 TypeScript 를 읽을 수 있게 옮긴다 ── */
const ts = createRequire(path.join(ROOT, "package.json"))("typescript");
const GEN = path.join(HERE, ".gen");
fs.rmSync(GEN, { recursive: true, force: true });
for (const [f, dir] of [["schemas", path.join(ROOT, "src", "api")], ["docs", HERE], ["core", HERE], ["contract/api", HERE], ["contract/common", HERE], ["contract/consistency", HERE]]) {
  const src = fs.readFileSync(path.join(dir, `${f}.ts`), "utf8");
  const js = ts
    .transpileModule(src, { compilerOptions: { module: "esnext", target: "es2022" } })
    .outputText.replace(/from "(\.\.?\/[^"]+)"/g, 'from "$1.js"');
  fs.mkdirSync(path.dirname(path.join(GEN, `${f}.js`)), { recursive: true });
  fs.writeFileSync(path.join(GEN, `${f}.js`), js);
}
fs.writeFileSync(path.join(GEN, "package.json"), '{"type":"module"}');
const load = (f) => import(pathToFileURL(path.join(GEN, f)).href);
const D = await load("core.js");
const A = await load("contract/api.js");
const DOCS = await load("docs.js");
const S = await load("schemas.js");

/* ── 도우미 ── */
const validJob = (job) => job === "demo" || job.startsWith("demo-") || /^U-\d{8}-\d{3,}$/.test(job);
const log = (...a) => console.log(new Date().toTimeString().slice(0, 8), ...a);
const warn = (...a) => console.error(new Date().toTimeString().slice(0, 8), "[계약 어긋남]", ...a);
const issuesText = (error) => error.issues.slice(0, 6).map((i) => `${i.path.join(".") || "(최상위)"}: ${i.message}`).join("; ");

const stores = new Map();
const storeOf = (job) => {
  let st = stores.get(job);
  if (!st) stores.set(job, (st = D.newStore(job)));
  return st;
};

function cors(req, res) {
  const origin = req.headers.origin ?? "";
  if (/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin)) {
    res.setHeader("Access-Control-Allow-Origin", origin);
    res.setHeader("Vary", "Origin");
  }
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,PUT,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type,Accept");
  // 실제 서버는 Content-Disposition 을 노출하지 않는다 (다른 출처의 화면은 파일 이름 헤더를 읽지 못한다)
}

/** JSON 응답. schema 가 있으면 계약으로 확인하고 어긋나면 500 */
function send(res, status, body, schema, what) {
  if (schema) {
    const parsed = schema.safeParse(body);
    if (!parsed.success) {
      warn(`응답 ${what}: ${issuesText(parsed.error)}`);
      status = 500;
      body = { detail: `서버 응답이 계약과 다릅니다 (${what})` };
    }
  }
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(body));
  return status;
}

const fail = (res, status, detail) => send(res, status, { detail });

/** FastAPI 의 422 모양 */
const invalid = (res, error, what) => {
  warn(`요청 ${what}: ${issuesText(error)}`);
  return send(res, 422, { detail: error.issues.map((i) => ({ type: i.code, loc: ["body", ...i.path], msg: i.code === "custom" ? "예외 승인·의견에는 comment 가 필요합니다" : i.message })) });
};

async function readJson(req) {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  try {
    return { ok: true, value: JSON.parse(Buffer.concat(chunks).toString("utf8") || "null") };
  } catch {
    return { ok: false };
  }
}

/** 핵심 함수가 던지는 FakeHttpError 를 응답으로. 409 본문은 conflict_response 로 확인한다 */
function sendError(res, e) {
  if (e instanceof D.FakeHttpError) {
    if (e.status === 409) {
      const parsed = A.conflictResponse.safeParse(e.body);
      if (!parsed.success) warn(`409 본문: ${issuesText(parsed.error)}`);
    }
    return send(res, e.status, e.body);
  }
  throw e;
}

async function withBody(req, res, schema, what, fn) {
  const body = await readJson(req);
  if (!body.ok) return fail(res, 422, "본문이 JSON 이 아닙니다");
  const parsed = schema.safeParse(body.value);
  if (!parsed.success) return invalid(res, parsed.error, what);
  try {
    return fn(parsed.data);
  } catch (e) {
    return sendError(res, e);
  }
}

/** 서버(reports.content_disposition): filename* 만 준다. html 은 헤더가 없다 */
const contentDisposition = (filename) => `attachment; filename*=UTF-8''${encodeURIComponent(filename)}`;

async function judgments(req, res, url, job, sub) {
  const st = storeOf(job);
  const guard = (fn) => {
    try {
      return fn();
    } catch (e) {
      return sendError(res, e);
    }
  };
  if (req.method === "GET" && sub === "status") return guard(() => send(res, 200, D.statusOf(job, st), A.judgmentStatus, "judgment_status"));
  if (req.method === "GET" && sub === "versions") return guard(() => send(res, 200, D.versionsOf(job, st), A.versionListItem.array(), "versions"));
  if (req.method === "GET" && sub === "history") return guard(() => send(res, 200, D.historyOf(job, st), A.historyEntry.array(), "history"));
  if (req.method === "GET" && sub === "save-overview") return guard(() => send(res, 200, D.saveOverviewOf(job, st), A.saveOverview, "save_overview"));
  if (req.method === "GET" && !sub) {
    const raw = url.searchParams.get("version");
    const version = raw === null ? undefined : Number(raw);
    return guard(() => send(res, 200, D.viewOf(job, st, version), A.judgmentView, "judgment_view"));
  }
  if (req.method === "POST" && sub === "reviews") {
    return withBody(req, res, A.reviewEventRequest, "reviews", (r) => send(res, 201, D.postReviewTo(job, st, r), A.reviewEvent, "review_event"));
  }
  if (req.method === "POST" && sub === "snapshots") {
    return withBody(req, res, A.saveRequest, "snapshots", (r) => send(res, 201, D.postSnapshotTo(job, st, r), A.snapshot, "snapshot"));
  }
  if (req.method === "POST" && sub === "reports") {
    return withBody(req, res, A.reportRequest, "reports", (r) => {
      const file = D.reportOf(job, st, r);
      if (r.format === "json") {
        const parsed = A.reportDocument.safeParse(JSON.parse(file.body));
        if (!parsed.success) {
          warn(`응답 report_document: ${issuesText(parsed.error)}`);
          return fail(res, 500, "서버 응답이 계약과 다릅니다 (report_document)");
        }
      }
      const headers = { "Content-Type": file.contentType };
      if (r.format !== "html") headers["Content-Disposition"] = contentDisposition(file.filename);
      res.writeHead(200, headers);
      res.end(Buffer.from(file.body, "utf8"));
      return 200;
    });
  }
  return fail(res, 405, "지원하지 않는 요청입니다");
}

const server = http.createServer(async (req, res) => {
  cors(req, res);
  const url = new URL(req.url ?? "/", `http://${req.headers.host}`);
  let status = 404;
  try {
    const p = url.pathname.replace(/\/$/, "");
    let m;
    if (req.method === "OPTIONS") {
      res.writeHead(204);
      res.end();
      status = 204;
    } else if (req.method === "GET" && p === "/api/health") {
      status = send(res, 200, { ok: true, mock: "judgment" });
    } else if (NO_JUDGE && p.startsWith("/api/judgments")) {
      status = fail(res, 404, "Not Found");
    } else if (req.method === "GET" && p === "/api/judgments/summary" && SUMMARY_FAIL) {
      status = fail(res, 500, "판정 요약을 만들지 못했습니다");
    } else if (req.method === "GET" && p === "/api/judgments/summary") {
      const ids = (url.searchParams.get("job_ids") ?? "").split(",").filter(Boolean);
      status = ids.some((id) => !/^U-\d{8}-\d{3,}$/.test(id))
        ? fail(res, 422, "job_ids 는 작업 번호(U-날짜-순번)여야 합니다")
        : send(res, 200, ids.map((id) => D.summaryItemOf(id, storeOf(id))), A.judgmentBatchItem.array(), "summary");
    } else if ((m = p.match(/^\/api\/judgments\/([^/]+)(?:\/(status|versions|history|save-overview|reviews|snapshots|reports))?$/))) {
      const job = decodeURIComponent(m[1]);
      status = validJob(job) ? await judgments(req, res, url, job, m[2]) : fail(res, 404, `없는 판정: ${job}`);
    } else if (req.method === "POST" && (m = p.match(/^\/api\/documents\/([^/]+)\/handoffs$/))) {
      // 서버 구현의 넘김: 본문이 없고 201. (실제 서버는 PostgreSQL 작업에서만 되고, 아니면 409 에 이유 문장)
      const id = decodeURIComponent(m[1]);
      for await (const _ of req); // 본문을 읽지 않고 흘려 보낸다
      status = validJob(id) ? send(res, 201, D.handoffTo(id, storeOf(id))) : fail(res, 404, `없는 문서: ${id}`);
    } else if (req.method === "POST" && (m = p.match(/^\/api\/documents\/([^/]+)\/to-judgment$/))) {
      // 계약의 이름. 실제 서버에는 없다 (MOCK_NO_A2=1 이면 이 경로도 404)
      if (NO_A2) {
        status = fail(res, 404, "Not Found");
        log(`${req.method} ${url.pathname} → ${status}`);
        return;
      }
      const id = decodeURIComponent(m[1]);
      status = validJob(id)
        ? await withBody(req, res, A.toJudgmentRequest, "to-judgment", () => send(res, 200, D.toJudgmentTo(id, storeOf(id)), A.toJudgmentResponse, "to_judgment_response"))
        : fail(res, 404, `없는 문서: ${id}`);
    } else if (req.method === "GET" && (m = p.match(/^\/api\/documents\/([^/]+)\/review\/log$/))) {
      // 계약의 A2 경로. 실제 서버에는 아직 없다 (MOCK_NO_A2=1 이면 404 로 답해 없는 서버를 흉내 낸다)
      status = NO_A2 ? fail(res, 404, "Not Found") : send(res, 200, D.reviewLogOf(), A.historyEntry.array(), "review/log");
    } else if (req.method === "GET" && p === "/api/documents") {
      const filter = url.searchParams.get("status") ?? "all";
      status = send(res, 200, DOCS.demoList(filter), S.documentListResponseSchema, "documents");
    } else if (req.method === "GET" && (m = p.match(/^\/api\/documents\/([^/]+)$/))) {
      const id = decodeURIComponent(m[1]);
      status = validJob(id) ? send(res, 200, DOCS.demoDetail(id), S.documentDetailSchema, "document") : fail(res, 404, `없는 문서: ${id}`);
    } else {
      status = fail(res, 404, "Not Found");
    }
  } catch (e) {
    warn(`처리 중 오류: ${e instanceof Error ? e.stack : e}`);
    if (!res.headersSent) status = fail(res, 500, "임시 서버 오류");
  }
  log(`${req.method} ${url.pathname}${url.search} → ${status}`);
});

// 방금 끈 서버의 포트가 잠시 잡혀 있으면(Windows 의 EFAULT·EADDRINUSE) 몇 초 뒤 다시 시도한다
const listen = () => server.listen(PORT, "127.0.0.1", () => log(`판정 임시 서버: http://127.0.0.1:${PORT}  (demo, demo-states, demo-conflict, demo-savefail, demo-pdffail, demo-single, demo-unknown)`));
let tries = 0;
server.on("error", (e) => {
  if ((e.code === "EFAULT" || e.code === "EADDRINUSE") && tries++ < 30) {
    log(`포트 ${PORT} 를 아직 쓸 수 없음(${e.code}). 2초 뒤 다시 시도 (${tries}/30)`);
    setTimeout(listen, 2000);
  } else throw e;
});
listen();
