/*
 * 판정·저장 임시 서버 (개발용). 계약 5-api 의 판정 경로를 Node 내장 http 만으로 흉내 낸다. 포트 8021.
 *   pnpm mock:judgment
 * 화면에서 쓰려면 프론트를 NEXT_PUBLIC_JUDGMENT_API_BASE=http://127.0.0.1:8021 로 띄운다 (CORS 는 localhost 를 허용).
 * 이 폴더는 src 밖이라 pnpm build 결과물에 들어가지 않는다.
 *
 * 구현한 경로
 *   GET  /api/judgments/{job}/status
 *   GET  /api/judgments/{job}?version=N        (없으면 최신)
 *   GET  /api/judgments/{job}/versions
 *   POST /api/judgments/{job}/reviews          201 review_event. seen_version < 최신 → 409, 예외 승인·의견에 comment 없음 → 422
 *   POST /api/judgments/{job}/snapshots        201 snapshot.     seen_version < 최신 → 409. 저장할 때마다 snapshot_no 증가
 *   POST /api/documents/{id}/to-judgment       200 {job_id, handoff_seq}. 3초 뒤 새 판정 버전(2)이 생긴다
 *
 * 판정 데이터는 src/api/demo-judgment.ts 를 그대로 쓴다 (시작할 때 TypeScript 로 .gen/ 에 옮겨 읽는다. 두 번 쓰지 않는다).
 * 요청 본문과 응답은 src/api/contract 의 zod 로 확인하고, 어긋나면 로그에 이유를 남긴다 (응답이 어긋나면 500).
 *
 * 상황은 job_id 로 가른다 (계약의 job_id 는 U-날짜-순번 이라 demo 계열 이름도 받는다):
 *   demo            판정 있음, 처리 전 (그 밖의 U-… 번호도 같다)
 *   demo-states     설명 작성 중 1건(8초 뒤 완료), 판정이 바뀐(stale) 검토 1건, 판정 중 + 더 새 넘김(pending_handoff)
 *   demo-conflict   읽어 간 판정(버전 1)이 낡는다: 첫 검토·저장 요청은 409, 다시 읽으면 버전 2
 *   demo-savefail   저장이 500 으로 실패한다
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

/* ── 프론트의 TypeScript 를 읽을 수 있게 옮긴다 ── */
const ts = createRequire(path.join(ROOT, "package.json"))("typescript");
const GEN = path.join(HERE, ".gen");
fs.rmSync(GEN, { recursive: true, force: true });
for (const f of ["client", "schemas", "demo-judgment", "contract/api", "contract/common", "contract/consistency"]) {
  const src = fs.readFileSync(path.join(ROOT, "src", "api", `${f}.ts`), "utf8");
  const js = ts
    .transpileModule(src, { compilerOptions: { module: "esnext", target: "es2022" } })
    .outputText.replace(/from "(\.\.?\/[^"]+)"/g, 'from "$1.js"');
  fs.mkdirSync(path.dirname(path.join(GEN, `${f}.js`)), { recursive: true });
  fs.writeFileSync(path.join(GEN, `${f}.js`), js);
}
fs.writeFileSync(path.join(GEN, "package.json"), '{"type":"module"}');
const load = (f) => import(pathToFileURL(path.join(GEN, f)).href);
const D = await load("demo-judgment.js");
const A = await load("contract/api.js");

/* ── 도우미 ── */
const kst = (ms = Date.now()) => `${new Date(ms + 9 * 3600_000).toISOString().slice(0, 19)}+09:00`;
const DEMO_JOB = "U-20261102-025";
const validJob = (job) => job === "demo" || job.startsWith("demo-") || /^U-\d{8}-\d{3,}$/.test(job);
const jobOut = (job) => (/^U-/.test(job) ? job : DEMO_JOB);
const scenarioOf = (job) =>
  job.startsWith("demo-states") ? "states" : job.startsWith("demo-conflict") ? "conflict" : job.startsWith("demo-savefail") ? "savefail" : "plain";
const WRITING_MS = 8000;
const JUDGE_MS = 3000;
const log = (...a) => console.log(new Date().toTimeString().slice(0, 8), ...a);
const warn = (...a) => console.error(new Date().toTimeString().slice(0, 8), "[계약 어긋남]", ...a);

const jobs = new Map();
function stateOf(job) {
  let st = jobs.get(job);
  if (st) return st;
  const scen = scenarioOf(job);
  const seed = D.demoView(scen === "states" ? "demo-states" : "demo").reviews;
  st = {
    scen,
    latest: 1,
    handoff: scen === "states" ? 2 : 1,
    pending: scen === "states" ? 2 : null,
    judging: scen === "states",
    startedAt: Date.now(),
    eventSeq: 0,
    snapshots: [],
    armConflict: scen === "conflict",
    // 처음부터 있던 검토 (demo-states 의 stale 검토). verdict_seen 은 모르므로 staleSeed 로 표시한다
    reviews: Object.fromEntries(Object.entries(seed).map(([id, r]) => [id, { ...r, verdict_seen: null, staleSeed: r.stale }])),
  };
  jobs.set(job, st);
  return st;
}

/** 버전 2 에서 바뀌는 판정: 금속부식성 근거부족 → 경계 (stale 시험용) */
const CHANGED_ID = "m0/F2:PH_METAL_CORR:-";

function viewOf(job, version) {
  const st = stateOf(job);
  const v = structuredClone(D.demoView(st.scen === "states" ? "demo-states" : "demo"));
  v.job_id = jobOut(job);
  v.version = version;
  v.is_latest = version === st.latest;
  v.handoff_seq = version === 1 ? 1 : st.handoff;
  if (version >= 2) {
    v.judged_at = kst(st.v2At ?? Date.now());
    const r = v.consistency.results[0];
    const f = r.findings.find((x) => x.id === CHANGED_ID);
    if (f && f.verdict === "근거부족") {
      f.verdict = "경계";
      r.summary["근거부족"] -= 1;
      r.summary["경계"] += 1;
    }
  }
  // 작성 중 설명은 일정 시간 뒤 완료된다
  if (Date.now() - st.startedAt > WRITING_MS) {
    for (const [id, e] of Object.entries(v.explanations)) {
      if (e.status === "작성 중") v.explanations[id] = { status: "완료", by: "template", checked: true, summary: "작성한 설명입니다.", reasons: [], basis: [] };
    }
  }
  const verdictOf = new Map(v.consistency.results[0].findings.map((f) => [f.id, f.verdict]));
  v.reviews = Object.fromEntries(
    Object.entries(st.reviews).map(([id, r]) => {
      const stale = r.staleSeed || (r.verdict_seen !== null && verdictOf.has(id) && verdictOf.get(id) !== r.verdict_seen);
      return [id, { status: r.status, comment: r.comment, reviewer: r.reviewer, at: r.at, history_count: r.history_count, stale: !!stale }];
    }),
  );
  return v;
}

const statusOf = (job) => {
  const st = stateOf(job);
  const exps = Object.values(viewOf(job, st.latest).explanations);
  return {
    job_id: jobOut(job),
    state: st.judging ? "판정 중" : "판정 있음",
    latest_version: st.latest,
    pending_handoff: st.pending,
    explanations: { done: exps.filter((e) => e.status === "완료").length, total: exps.length },
    saved_snapshot: st.snapshots.length ? st.snapshots.length : null,
    error: null,
  };
};

const versionsOf = (job) => {
  const st = stateOf(job);
  const base = viewOf(job, 1);
  const list = [{ version: 1, handoff_seq: 1, judged_at: base.judged_at, summary: base.consistency.results[0].summary, changed_findings: [] }];
  for (let n = 2; n <= st.latest; n += 1) {
    const v = viewOf(job, n);
    list.push({ version: n, handoff_seq: v.handoff_seq, judged_at: v.judged_at, summary: v.consistency.results[0].summary, changed_findings: [CHANGED_ID] });
  }
  return list.reverse();
};

/* ── HTTP ── */
const issuesText = (error) => error.issues.slice(0, 6).map((i) => `${i.path.join(".") || "(최상위)"}: ${i.message}`).join("; ");

function cors(req, res) {
  const origin = req.headers.origin ?? "";
  if (/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin)) {
    res.setHeader("Access-Control-Allow-Origin", origin);
    res.setHeader("Vary", "Origin");
  }
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,PUT,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type,Accept");
}

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

/** demo-conflict: 화면이 버전 1 을 읽은 뒤 더 새 판정(버전 2)이 생긴 것으로 한다. 첫 쓰기 요청 때 일어난다 */
function armConflict(st) {
  if (!st.armConflict) return;
  st.armConflict = false;
  st.latest = 2;
  st.v2At = Date.now();
  st.handoff = 2;
}

const REVIEW_STATUS = { "불일치 확정": "불일치 확정", "예외 승인": "예외 승인", 확인: "확인" };

async function postReview(job, req, res) {
  const body = await readJson(req);
  if (!body.ok) return fail(res, 422, "본문이 JSON 이 아닙니다");
  const parsed = A.reviewEventRequest.safeParse(body.value);
  if (!parsed.success) return invalid(res, parsed.error, "reviews");
  const r = parsed.data;
  const st = stateOf(job);
  armConflict(st);
  if (r.seen_version < st.latest) return fail(res, 409, `더 새로운 판정 버전이 있습니다 (최신 ${st.latest}, 본 것 ${r.seen_version})`);
  if (r.seen_version > st.latest) return fail(res, 422, `아직 없는 판정 버전입니다: ${r.seen_version}`);
  const f = viewOf(job, st.latest).consistency.results[0].findings.find((x) => x.id === r.finding_id);
  if (!f) return fail(res, 404, `없는 판정 항목: ${r.finding_id}`);
  const prev = st.reviews[r.finding_id];
  const at = kst();
  const status = r.action === "되돌리기" ? "미검토" : r.action === "의견" ? (prev?.status ?? "미검토") : REVIEW_STATUS[r.action];
  st.reviews[r.finding_id] = {
    status,
    comment: r.action === "되돌리기" ? null : (r.comment ?? prev?.comment ?? null),
    reviewer: r.reviewer,
    at,
    history_count: (prev?.history_count ?? 0) + 1,
    verdict_seen: f.verdict,
    staleSeed: false,
  };
  const event = { event_id: ++st.eventSeq, job_id: jobOut(job), finding_id: r.finding_id, action: r.action, comment: r.comment ?? null, reviewer: r.reviewer, at, version: st.latest, verdict_seen: f.verdict };
  return send(res, 201, event, A.reviewEvent, "review_event");
}

async function postSnapshot(job, req, res) {
  const body = await readJson(req);
  if (!body.ok) return fail(res, 422, "본문이 JSON 이 아닙니다");
  const parsed = A.saveRequest.safeParse(body.value);
  if (!parsed.success) return invalid(res, parsed.error, "snapshots");
  const r = parsed.data;
  const st = stateOf(job);
  if (st.scen === "savefail") return fail(res, 500, "서버가 저장을 마치지 못했습니다.");
  armConflict(st);
  if (r.seen_version < st.latest) return fail(res, 409, `더 새로운 판정 버전이 있습니다 (최신 ${st.latest}, 본 것 ${r.seen_version})`);
  if (r.seen_version > st.latest) return fail(res, 422, `아직 없는 판정 버전입니다: ${r.seen_version}`);
  const view = viewOf(job, st.latest);
  const counts = { findings: 0, 미검토: 0, "불일치 확정": 0, "예외 승인": 0, 확인: 0, "미검수 칸": 0 };
  const fields = new Set();
  for (const f of view.consistency.results[0].findings) {
    if (f.kind === "product_type") continue;
    counts.findings += 1;
    counts[view.reviews[f.id]?.status ?? "미검토"] += 1;
    for (const e of [...(f.msds.evidence ?? []), ...(f.expected.evidence ?? [])]) fields.add(`${view.consistency.results[0].msds_index}|${e.field}`);
  }
  const checked = new Set(view.field_status.map((s) => `${s.msds_index}|${s.field}`));
  counts["미검수 칸"] = [...fields].filter((k) => !checked.has(k)).length;
  const snap = {
    contract: "snapshot/1", job_id: jobOut(job), snapshot_no: st.snapshots.length + 1, handoff_seq: view.handoff_seq, version: view.version,
    last_review_event_id: st.eventSeq || null, counts, saved_by: r.reviewer, saved_at: kst(), note: r.note ?? null,
  };
  const status = send(res, 201, snap, A.snapshot, "snapshot");
  if (status === 201) st.snapshots.push(snap);
  return status;
}

async function postToJudgment(id, req, res) {
  const body = await readJson(req);
  if (!body.ok) return fail(res, 422, "본문이 JSON 이 아닙니다");
  const parsed = A.toJudgmentRequest.safeParse(body.value);
  if (!parsed.success) return invalid(res, parsed.error, "to-judgment");
  const st = stateOf(id);
  st.handoff += 1;
  st.pending = st.handoff;
  st.judging = true;
  const seq = st.handoff;
  setTimeout(() => {
    st.latest += 1;
    st.v2At = Date.now();
    st.judging = false;
    st.pending = null;
    st.startedAt = 0; // 새 판정의 설명은 처음부터 완료
    log(`판정 끝: ${id} 버전 ${st.latest} (넘김 ${seq})`);
  }, JUDGE_MS);
  return send(res, 200, { job_id: jobOut(id), handoff_seq: seq }, A.toJudgmentResponse, "to-judgment");
}

const server = http.createServer(async (req, res) => {
  cors(req, res);
  const url = new URL(req.url ?? "/", `http://${req.headers.host}`);
  let status = 404;
  try {
    if (req.method === "OPTIONS") {
      res.writeHead(204);
      res.end();
      status = 204;
    } else {
      const p = url.pathname.replace(/\/$/, "");
      let m;
      if (req.method === "GET" && p === "/api/health") {
        status = send(res, 200, { ok: true, mock: "judgment" });
      } else if (req.method === "POST" && (m = p.match(/^\/api\/documents\/([^/]+)\/to-judgment$/))) {
        const id = decodeURIComponent(m[1]);
        status = validJob(id) ? await postToJudgment(id, req, res) : fail(res, 404, `없는 문서: ${id}`);
      } else if ((m = p.match(/^\/api\/judgments\/([^/]+)(?:\/(status|versions|reviews|snapshots))?$/))) {
        const job = decodeURIComponent(m[1]);
        const sub = m[2];
        if (!validJob(job)) {
          status = fail(res, 404, `없는 판정: ${job}`);
        } else if (req.method === "GET" && sub === "status") {
          status = send(res, 200, statusOf(job), A.judgmentStatus, "judgment_status");
        } else if (req.method === "GET" && sub === "versions") {
          status = send(res, 200, versionsOf(job), A.versionListItem.array(), "versions");
        } else if (req.method === "GET" && !sub) {
          const st = stateOf(job);
          const raw = url.searchParams.get("version");
          const version = raw === null ? st.latest : Number(raw);
          if (!Number.isInteger(version) || version < 1 || version > st.latest) {
            status = fail(res, 404, `없는 판정 버전: ${raw}`);
          } else {
            status = send(res, 200, viewOf(job, version), A.judgmentView, "judgment_view");
          }
        } else if (req.method === "POST" && sub === "reviews") {
          status = await postReview(job, req, res);
        } else if (req.method === "POST" && sub === "snapshots") {
          status = await postSnapshot(job, req, res);
        } else {
          status = fail(res, 405, "지원하지 않는 요청입니다");
        }
      } else {
        status = fail(res, 404, "Not Found");
      }
    }
  } catch (e) {
    warn(`처리 중 오류: ${e instanceof Error ? e.stack : e}`);
    if (!res.headersSent) status = fail(res, 500, "임시 서버 오류");
  }
  log(`${req.method} ${url.pathname}${url.search} → ${status}`);
});

server.listen(PORT, "127.0.0.1", () => log(`판정 임시 서버: http://127.0.0.1:${PORT}  (demo, demo-states, demo-conflict, demo-savefail)`));
