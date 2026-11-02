/*
 * 판정 API 호출 (계약 5-api). 응답은 api/contract/ 의 zod 로 확인한 뒤에만 쓴다.
 *   GET  /api/judgments/{job_id}/status
 *   GET  /api/judgments/{job_id}?version=N      (없으면 최신)
 *   GET  /api/judgments/{job_id}/versions
 *   POST /api/judgments/{job_id}/reviews        (seen_version 이 낡으면 409)
 *   POST /api/judgments/{job_id}/snapshots
 *   POST /api/documents/{id}/to-judgment
 * 문서 번호(doc)가 곧 job_id 다. 데모 문서는 lib/demo.ts 의 스위치가 켜져 있을 때만 고정 데이터를 쓴다.
 *
 * 계약에 응답 모양이 적혀 있지 않은 것: POST /reviews 의 응답(review_event 로 본다), POST /snapshots 의 응답(snapshot 으로 본다).
 * 서버 확정 후 맞출 것.
 */
import { queryOptions } from "@tanstack/react-query";
import { isDemoDoc, loadDemo } from "@/lib/demo";
import { ApiRequestError, requestJson } from "./client";
import {
  judgmentStatus,
  judgmentView,
  reviewEvent,
  snapshot,
  toJudgmentResponse,
  versionListItem,
  type JudgmentView,
  type ReviewEventRequest,
  type SaveRequest,
} from "./contract/api";
import { z } from "zod";

/** 데모 문서에서만 듣는 모양 바꾸기(성분 요약의 &product=single·unknown). 운영 요청에는 실리지 않는다 */
export type DemoVariant = "single" | "unknown" | undefined;

const base = (job: string) => `/api/judgments/${encodeURIComponent(job)}`;
const post = (body: unknown, signal?: AbortSignal) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
  signal,
});

/** 검토·저장 요청이 409 로 막혔는가 (더 새로운 판정 버전이 있다) */
export const isConflict = (error: unknown) => error instanceof ApiRequestError && error.status === 409;

export async function getJudgmentStatus(job: string, signal?: AbortSignal) {
  if (isDemoDoc(job)) return (await loadDemo.judgment()).demoStatus(job);
  return requestJson(judgmentStatus, `${base(job)}/status`, { signal });
}

export async function getJudgmentView(job: string, version?: number, variant?: DemoVariant, signal?: AbortSignal): Promise<JudgmentView> {
  if (isDemoDoc(job)) return (await loadDemo.judgment()).demoView(job, variant);
  return requestJson(judgmentView, base(job), { query: version ? { version: String(version) } : undefined, signal });
}

export async function getJudgmentVersions(job: string, signal?: AbortSignal) {
  if (isDemoDoc(job)) return (await loadDemo.judgment()).demoVersions(job);
  return requestJson(z.array(versionListItem), `${base(job)}/versions`, { signal });
}

export async function postReview(job: string, request: ReviewEventRequest) {
  if (isDemoDoc(job)) return (await loadDemo.judgment()).demoPostReview(job, request);
  return requestJson(reviewEvent, `${base(job)}/reviews`, post(request));
}

export async function postSnapshot(job: string, request: SaveRequest, demo?: { fail?: boolean }) {
  if (isDemoDoc(job)) return (await loadDemo.judgment()).demoPostSnapshot(job, request, !!demo?.fail);
  return requestJson(snapshot, `${base(job)}/snapshots`, post(request));
}

/** 추출값 확인을 마치고 판정으로 넘긴다 (넘김②를 만든다) */
export async function postToJudgment(docId: string, reviewer: string) {
  if (isDemoDoc(docId)) return (await loadDemo.judgment()).demoToJudgment(docId);
  return requestJson(toJudgmentResponse, `/api/documents/${encodeURIComponent(docId)}/to-judgment`, post({ reviewer }));
}

/* ── 읽기 쿼리 ─────────────────────────────────────────────── */

export const judgmentKeys = {
  all: ["judgment"] as const,
  view: (job: string, version: string, variant?: DemoVariant) => [...judgmentKeys.all, job, "view", version, variant ?? ""] as const,
  status: (job: string) => [...judgmentKeys.all, job, "status"] as const,
  versions: (job: string) => [...judgmentKeys.all, job, "versions"] as const,
};

const hasWriting = (view: JudgmentView | undefined) => !!view && Object.values(view.explanations).some((e) => e.status === "작성 중");

/** 판정 화면이 읽는 판정 한 벌. 판정·성분 요약·검토 상태가 모두 여기서 나온다. 설명이 작성 중이면 다시 묻는다 */
export const judgmentViewQuery = (job: string, version = "latest", variant?: DemoVariant) =>
  queryOptions({
    queryKey: judgmentKeys.view(job, version, variant),
    queryFn: ({ signal }) => getJudgmentView(job, version === "latest" ? undefined : Number(version), variant, signal),
    refetchInterval: (query) => (hasWriting(query.state.data) ? 5_000 : false),
  });

/** 판정 화면에 들어가기 전 확인. 판정 중이거나 더 새 넘김이 있으면 다시 묻는다 */
export const judgmentStatusQuery = (job: string) =>
  queryOptions({
    queryKey: judgmentKeys.status(job),
    queryFn: ({ signal }) => getJudgmentStatus(job, signal),
    refetchInterval: (query) => {
      const s = query.state.data;
      return s && (s.state === "판정 중" || s.pending_handoff !== null) ? 5_000 : false;
    },
  });

export const judgmentVersionsQuery = (job: string) =>
  queryOptions({ queryKey: judgmentKeys.versions(job), queryFn: ({ signal }) => getJudgmentVersions(job, signal) });
