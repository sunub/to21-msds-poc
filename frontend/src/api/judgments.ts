/*
 * 판정 API 호출 (계약 5-api, consistency/2). 응답은 api/contract/ 의 zod 로 확인한 뒤에만 쓴다.
 *   GET  /api/judgments/{job_id}/status
 *   GET  /api/judgments/{job_id}?version=N      (없으면 최신)
 *   GET  /api/judgments/{job_id}/versions
 *   GET  /api/judgments/{job_id}/history
 *   GET  /api/judgments/{job_id}/save-overview
 *   GET  /api/judgments/summary?job_ids=a,b,c   (목록 화면: A 의 문서 목록과 job_id 로 합친다)
 *   POST /api/judgments/{job_id}/reviews        201 review_event. seen_version·seen_event_id 가 낡으면 409
 *   POST /api/judgments/{job_id}/snapshots      201 snapshot. 낡은 판정이면 409
 *   POST /api/judgments/{job_id}/reports        응답은 파일 (html·xlsx·pdf·json). 글이 빠진 PDF 는 422
 *   POST /api/documents/{id}/to-judgment        추출 서버(A) 주소로 보낸다 (판정 주소가 아니다)
 * 문서 번호(doc)가 곧 job_id 다. 데모 문서는 lib/demo.ts 의 스위치가 켜져 있을 때만 고정 데이터를 쓴다.
 */
import { queryOptions } from "@tanstack/react-query";
import { z } from "zod";
import { isDemoDoc, loadDemo } from "@/lib/demo";
import { ApiRequestError, apiUrl, requestJson } from "./client";
import {
  historyEntry,
  judgmentBatchItem,
  judgmentStatus,
  judgmentView,
  reviewEvent,
  saveOverview,
  snapshot,
  toJudgmentResponse,
  versionListItem,
  type ConflictResponse,
  type JudgmentView,
  type ReportRequest,
  type ReviewEventRequest,
  type SaveRequest,
} from "./contract/api";

/** 데모 문서에서만 듣는 모양 바꾸기(성분 요약의 &product=single·unknown). 운영 요청에는 실리지 않는다 */
export type DemoVariant = "single" | "unknown" | undefined;

/** 판정 API 주소 앞부분. 추출 API 와 따로 둘 수 있고(NEXT_PUBLIC_JUDGMENT_API_BASE), 비어 있으면 추출 API 주소(NEXT_PUBLIC_API_BASE)를 쓴다. 정해 두면 데모 문서도 이 서버를 부른다 (개발용 임시 서버 시험) */
const JUDGMENT_BASE = process.env.NEXT_PUBLIC_JUDGMENT_API_BASE || undefined;
const useDemo = (job: string) => isDemoDoc(job) && !JUDGMENT_BASE;

const base = (job: string) => `/api/judgments/${encodeURIComponent(job)}`;
const json = (body: unknown, signal?: AbortSignal) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
  signal,
});
const post = (body: unknown, signal?: AbortSignal) => ({ base: JUDGMENT_BASE, ...json(body, signal) });

/** 검토·저장 요청이 409 로 막혔는가 (더 새로운 판정 버전이나 다른 검토자의 처리가 있다). 본문은 error.data 의 conflict_response */
export const isConflict = (error: unknown) => error instanceof ApiRequestError && error.status === 409;

export async function getJudgmentStatus(job: string, signal?: AbortSignal) {
  if (useDemo(job)) return (await loadDemo.judgment()).demoStatus(job);
  return requestJson(judgmentStatus, `${base(job)}/status`, { base: JUDGMENT_BASE, signal });
}

export async function getJudgmentView(job: string, version?: number, variant?: DemoVariant, signal?: AbortSignal): Promise<JudgmentView> {
  if (useDemo(job)) return (await loadDemo.judgment()).demoView(job, variant);
  return requestJson(judgmentView, base(job), { base: JUDGMENT_BASE, query: version ? { version: String(version) } : undefined, signal });
}

export async function getJudgmentVersions(job: string, signal?: AbortSignal) {
  if (useDemo(job)) return (await loadDemo.judgment()).demoVersions(job);
  return requestJson(z.array(versionListItem), `${base(job)}/versions`, { base: JUDGMENT_BASE, signal });
}

/** 판정 쪽 검토 이력 (최근 것부터). 검토 이력 탭이 추출값 쪽 이력과 at 으로 합친다 */
export async function getJudgmentHistory(job: string, signal?: AbortSignal) {
  if (useDemo(job)) return (await loadDemo.judgment()).demoHistory(job);
  return requestJson(z.array(historyEntry), `${base(job)}/history`, { base: JUDGMENT_BASE, signal });
}

export async function getSaveOverview(job: string, signal?: AbortSignal) {
  if (useDemo(job)) return (await loadDemo.judgment()).demoSaveOverview(job);
  return requestJson(saveOverview, `${base(job)}/save-overview`, { base: JUDGMENT_BASE, signal });
}

/** 목록 화면용: 여러 작업의 판정 상태·등급을 한 번에. 데모 문서는 데모 데이터, 나머지는 서버 한 번 */
export async function getJudgmentSummary(jobIds: string[], signal?: AbortSignal) {
  const demo = jobIds.filter(useDemo);
  // 서버 요약은 작업 번호(U-날짜-순번)만 받는다. 개발용 demo 이름은 서버에 보내지 않는다
  const real = jobIds.filter((id) => !useDemo(id) && /^U-d{8}-d{3,}$/.test(id));
  // 데모 문서의 job_id 는 계약 모양(U-날짜-순번)으로 오므로, 목록이 합칠 수 있게 요청한 문서 번호로 바꾼다
  const demoItems = demo.length ? (await loadDemo.judgment()).demoSummary(demo).map((item, i) => ({ ...item, job_id: demo[i] })) : [];
  const realItems = real.length
    ? await requestJson(z.array(judgmentBatchItem), "/api/judgments/summary", { base: JUDGMENT_BASE, query: { job_ids: real.join(",") }, signal })
    : [];
  return [...demoItems, ...realItems];
}

export async function postReview(job: string, request: ReviewEventRequest) {
  if (useDemo(job)) return (await loadDemo.judgment()).demoPostReview(job, request);
  return requestJson(reviewEvent, `${base(job)}/reviews`, post(request));
}

export async function postSnapshot(job: string, request: SaveRequest, demo?: { fail?: boolean }) {
  if (useDemo(job)) return (await loadDemo.judgment()).demoPostSnapshot(job, request, !!demo?.fail);
  return requestJson(snapshot, `${base(job)}/snapshots`, post(request));
}

/** 서버가 주는 넘김 응답: {job_id, handoff_seq, as_of, extraction_sha256, validator}. 화면은 앞의 둘만 쓴다 */
const handoffResponse = z.looseObject({ job_id: z.string(), handoff_seq: z.int().min(1) });

/**
 * 추출값 확인을 마치고 판정으로 넘긴다 (넘김②를 만든다). A(추출 서버) 경로라 판정 주소가 아니라 추출 API 주소로 보낸다.
 * 서버 구현(extract_app.py)은 POST /api/documents/{id}/handoffs 다: 본문이 없고(검토자는 받지 않는다) 201 로 답하며,
 * 판정 준비가 안 됐으면 409 에 이유 문장이 온다. 계약의 이름(to-judgment)만 있는 서버를 위해, 길이 없는 응답(404 Not Found·405)이면 그 이름으로 한 번 더 부른다.
 */
export async function postToJudgment(docId: string, reviewer: string) {
  if (useDemo(docId)) return (await loadDemo.judgment()).demoToJudgment(docId);
  const path = `/api/documents/${encodeURIComponent(docId)}`;
  try {
    return await requestJson(handoffResponse, `${path}/handoffs`, { method: "POST" });
  } catch (e) {
    const noRoute = e instanceof ApiRequestError && (e.status === 405 || (e.status === 404 && e.message === "Not Found"));
    if (!noRoute) throw e;
    return requestJson(toJudgmentResponse, `${path}/to-judgment`, json({ reviewer }));
  }
}

/**
 * Content-Disposition 에서 파일 이름을 읽는다 (서버는 filename*=UTF-8''… 만 준다. html 은 헤더가 없다).
 * 다른 출처(next dev → API 서버)에서는 서버가 이 헤더를 노출하지 않아 읽을 수 없다: 그때는 fallback(제품명_MSDS_검토결과.확장자)을 쓴다
 */
function fileNameOf(res: Response, fallback: string) {
  const header = res.headers.get("Content-Disposition") ?? "";
  const star = /filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)/.exec(header)?.[1];
  if (star) {
    try {
      return decodeURIComponent(star);
    } catch {
      // 잘못된 인코딩이면 아래로
    }
  }
  return /filename\s*=\s*"?([^";]+)"?/.exec(header)?.[1] ?? fallback;
}

/** 리포트 파일을 받는다. 실패(422 글이 빠진 PDF 등)는 서버 문장을 담은 ApiRequestError */
export async function postReport(job: string, request: ReportRequest, baseName?: string, signal?: AbortSignal): Promise<{ blob: Blob; filename: string }> {
  if (useDemo(job)) return (await loadDemo.judgment()).demoReport(job, request);
  const res = await fetch(apiUrl(`${base(job)}/reports`, undefined, JUDGMENT_BASE), { ...json(request, signal), headers: { "Content-Type": "application/json", Accept: "*/*" } });
  if (!res.ok) {
    const body: unknown = await res.json().catch(() => null);
    const detail = body && typeof body === "object" && "detail" in body ? (body as { detail: unknown }).detail : null;
    throw new ApiRequestError(res.status, `http_${res.status}`, typeof detail === "string" ? detail : `서버가 ${res.status} 로 응답했습니다.`);
  }
  return { blob: await res.blob(), filename: fileNameOf(res, `${baseName ?? job}_MSDS_검토결과.${request.format}`) };
}

/* ── 읽기 쿼리 ─────────────────────────────────────────────── */

export const judgmentKeys = {
  all: ["judgment"] as const,
  view: (job: string, version: string, variant?: DemoVariant) => [...judgmentKeys.all, job, "view", version, variant ?? ""] as const,
  status: (job: string) => [...judgmentKeys.all, job, "status"] as const,
  versions: (job: string) => [...judgmentKeys.all, job, "versions"] as const,
  history: (job: string) => [...judgmentKeys.all, job, "history"] as const,
  overview: (job: string) => [...judgmentKeys.all, job, "overview"] as const,
  summary: (jobIds: string[]) => [...judgmentKeys.all, "summary", ...jobIds] as const,
};

const hasWriting = (view: JudgmentView | undefined) => !!view && Object.values(view.explanations).some((e) => e.status === "작성 중");

/** 판정 화면이 읽는 판정 한 벌. 판정·성분 요약·검토 상태가 모두 여기서 나온다. 설명이 작성 중이면 다시 묻는다 */
export const judgmentViewQuery = (job: string, version = "latest", variant?: DemoVariant) =>
  queryOptions({
    queryKey: judgmentKeys.view(job, version, variant),
    queryFn: ({ signal }) => getJudgmentView(job, version === "latest" ? undefined : Number(version), variant, signal),
    refetchInterval: (query) => (hasWriting(query.state.data) ? 5_000 : false),
  });

/** 판정 화면에 들어가기 전 확인. 판정 중이거나 더 새 넘김이 있으면 5초마다, 아직 판정이 없으면 15초마다 다시 묻는다 */
export const judgmentStatusQuery = (job: string) =>
  queryOptions({
    queryKey: judgmentKeys.status(job),
    queryFn: ({ signal }) => getJudgmentStatus(job, signal),
    refetchInterval: (query) => {
      const s = query.state.data;
      if (!s) return false;
      if (s.state === "판정 중" || s.pending_handoff !== null) return 5_000;
      // 아직 넘기지 않은 문서도 가끔 묻는다: 다른 검토자가 넘기면 화면이 스스로 판정을 읽어 온다
      return s.state === "판정 없음" ? 15_000 : false;
    },
  });

export const judgmentVersionsQuery = (job: string) =>
  queryOptions({ queryKey: judgmentKeys.versions(job), queryFn: ({ signal }) => getJudgmentVersions(job, signal) });

export const judgmentHistoryQuery = (job: string) =>
  queryOptions({ queryKey: judgmentKeys.history(job), queryFn: ({ signal }) => getJudgmentHistory(job, signal) });

export const saveOverviewQuery = (job: string) =>
  queryOptions({ queryKey: judgmentKeys.overview(job), queryFn: ({ signal }) => getSaveOverview(job, signal) });

/** 목록 화면의 판정 요약. 판정 서버가 없을 때는 한 번만 묻고 포기한다 (목록은 추출 쪽 정보로 그린다) */
export const judgmentSummaryQuery = (jobIds: string[]) =>
  queryOptions({
    queryKey: judgmentKeys.summary(jobIds),
    queryFn: ({ signal }) => getJudgmentSummary(jobIds, signal),
    enabled: jobIds.length > 0,
    retry: false,
  });

/**
 * 판정을 불러오지 못했을 때의 안내.
 *  - 판정 서버는 있는데 이 문서의 판정이 아직 없으면(404 "판정이 없음: …") 서버 문장 그대로 판정을 아직 만들지 않았다고 알린다
 *  - 판정 API 자체가 없거나(404 Not Found·405) 연결이 안 되면 준비 중이라고 알린다
 */
export function judgmentErrorText(error: unknown, fallback: string) {
  if (error instanceof ApiRequestError && error.status === 404 && error.message.startsWith("판정이 없음")) {
    return "아직 판정이 없습니다. 추출값을 확인한 뒤 판정으로 넘겼는지, 판정 중인지 확인해 주세요.";
  }
  const notReady = (error instanceof ApiRequestError && (error.status === 404 || error.status === 405)) || error instanceof TypeError;
  return notReady ? "판정 서비스 준비 중입니다. 추출 단계까지 사용할 수 있습니다." : fallback;
}

/**
 * 검토·저장이 409 로 막혔을 때의 안내. 본문(conflict_response)의 pending_handoff·message 로 이유를 가른다 (서버 문장:
 * "넘김 기록 N을 아직 판정하지 않음" / "최신 판정 버전은 N" / "다른 검토자가 먼저 처리함 (이벤트 N)")
 */
export function conflictText(error: unknown): string {
  const detail = error instanceof ApiRequestError ? (error.data as ConflictResponse | undefined)?.detail : undefined;
  if (detail?.pending_handoff != null) return "더 새로운 추출값을 판정하는 중입니다. 판정이 끝난 뒤 새로고침해 주세요.";
  if (detail?.message.startsWith("다른 검토자")) return "다른 검토자가 먼저 처리했습니다. 새로고침해 주세요.";
  return "더 새로운 판정 버전이 있습니다. 새로고침해 주세요.";
}
