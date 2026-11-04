/*
 * 저장 화면(3.1~3.2)의 API. 계약: contracts/5-api save_overview · save_request · snapshot · report_request, 6-screens 3.1~3.2.
 * 저장 화면 재료는 save-overview 한 번이고, 저장은 snapshots 에 한 줄을 더한다 (다시 저장하면 새 번호).
 * 리포트(PDF·JSON·미리 보기 HTML)는 파일이라 JSON 입구를 쓰지 않는다.
 */
import { queryOptions } from "@tanstack/react-query";
import { z } from "zod";
import { ApiRequestError, apiUrl, toRequestError } from "./client";
import { call, judgmentKeys } from "./judgment";

/** 3-consistency msds_result.summary: 판정별 건수 */
const verdictCountsSchema = z.object({
  일치: z.number(),
  불일치: z.number(),
  경계: z.number(),
  근거부족: z.number(),
  경고: z.number(),
  참고: z.number(),
  "범위 외": z.number(),
});

export const snapshotSchema = z.object({
  contract: z.literal("snapshot/1"),
  job_id: z.string(),
  snapshot_no: z.number().int().min(1),
  handoff_seq: z.number().int().min(1),
  version: z.number().int().min(1),
  last_review_event_id: z.number().nullable(),
  counts: z.object({
    findings: z.number(),
    미검토: z.number(),
    "불일치 확정": z.number(),
    "예외 승인": z.number(),
    확인: z.number(),
    "미검수 칸": z.number(),
  }),
  saved_by: z.string(),
  saved_at: z.string(),
  note: z.string().nullable(),
});

export const saveOverviewSchema = z.object({
  job_id: z.string(),
  version: z.number().int().min(1),
  handoff_seq: z.number().int().min(1),
  verdicts: z.object({
    total: verdictCountsSchema,
    by_section: z.object({ "2": verdictCountsSchema, "15": verdictCountsSchema }),
  }),
  reviews: z.object({
    미검토: z.number(),
    "불일치 확정": z.number(),
    "예외 승인": z.number(),
    확인: z.number(),
    unreviewed_ids: z.array(z.string()),
  }),
  values: z.object({
    state: z.enum(["미검수", "일부", "완료"]),
    model_as_is: z.number(),
    confirmed: z.number(),
    edited: z.number(),
    fields_total: z.number(),
  }),
  /** 최근 저장본이 앞에 온다 */
  snapshots: z.array(snapshotSchema),
});

export type VerdictCounts = z.infer<typeof verdictCountsSchema>;
export type Snapshot = z.infer<typeof snapshotSchema>;
export type SaveOverview = z.infer<typeof saveOverviewSchema>;
export type SaveRequest = { reviewer: string; seen_version: number; note: string | null };

const job = (id: string) => `/api/judgments/${encodeURIComponent(id)}`;

export const saveKeys = { overview: (id: string) => [...judgmentKeys.all(id), "save-overview"] as const };

/** 저장 화면을 열 때마다 다시 받는다. 검수 탭에서 처리하고 오면 바로 맞는 건수가 보여야 한다 */
export const saveOverviewQuery = (id: string) =>
  queryOptions({
    queryKey: saveKeys.overview(id),
    queryFn: ({ signal }) => call(saveOverviewSchema, `${job(id)}/save-overview`, { signal }),
    staleTime: 0,
  });

/** 미검토가 남아도 저장된다. 본 판정 버전이 최신이 아니거나 넘김을 아직 판정하지 않았으면 409 */
export const postSnapshot = (id: string, body: SaveRequest) =>
  call(snapshotSchema, `${job(id)}/snapshots`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export type ReportInclude = {
  regenerated_msds: boolean;
  findings_2: boolean;
  findings_15: boolean;
  components: boolean;
  history: boolean;
};

/**
 * 리포트 파일을 받는다. snapshot_no 가 null 이면 지금 판정으로 만든 "저장 전 미리 보기"다.
 * 개발용 대역이 켜져 있으면 파일을 만들 수 없어 연결 전(404)으로 알린다.
 */
export async function fetchReport(
  id: string,
  format: "pdf" | "json" | "html",
  include: ReportInclude,
  snapshotNo: number | null,
): Promise<{ blob: Blob; disposition: string | null }> {
  if (process.env.NODE_ENV === "development") {
    const mock = await import("./judgment-mock");
    if (mock.mockActive()) throw new ApiRequestError(404, "unknown", "Not Found");
  }
  const res = await fetch(apiUrl(`${job(id)}/reports`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ format, snapshot_no: snapshotNo, include }),
  });
  if (!res.ok) throw await toRequestError(res);
  return { blob: await res.blob(), disposition: res.headers.get("Content-Disposition") };
}
