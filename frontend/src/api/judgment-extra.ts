/*
 * 판정 API 중 2항·15항 탭이 쓰지 않는 것: 저장 개요, 저장(스냅샷), 목록 요약, 버전 목록, 리포트 파일, 409 이유 문장.
 * judgment.ts 와 같은 방식이다: 화면이 읽는 칸만 확인하는 느슨한 zod 이고, 요청은 call() 을 거친다.
 * (?judgmentMock 대역은 이 경로들을 모른다. 대역이 켜져 있으면 "연결 전"과 같은 404 로 답한다.)
 * 서버 기준: backend/src/msds/api/judge_app.py, judge/service.py, judge/reports.py.
 */
import { queryOptions } from "@tanstack/react-query";
import { z } from "zod";
import { ApiRequestError, apiUrl, toRequestError } from "./client";
import { chunk, isJobId } from "@/lib/doc-stage";
import { call, judgmentKeys } from "./judgment";

const count = z.number().int().min(0);

/** 저장본 한 건 (5-api snapshot). 새 것부터 온다 */
export const snapshotSchema = z.object({
  snapshot_no: z.number().int().min(1),
  version: z.number().int().min(1),
  last_review_event_id: z.number().nullable().optional(),
  counts: z.object({
    findings: count,
    미검토: count,
    "불일치 확정": count,
    "예외 승인": count,
    확인: count,
    "미검수 칸": count,
  }),
  saved_by: z.string().optional(),
  saved_at: z.string(),
  note: z.string().nullable().optional(),
});
export type Snapshot = z.infer<typeof snapshotSchema>;

/** 판정 건수. 계약의 일곱 가지 판정 이름이 칸이다 (모르는 칸은 버린다) */
const verdictCounts = z.object({
  일치: count,
  불일치: count,
  경계: count,
  근거부족: count,
  경고: count,
  참고: count,
  "범위 외": count,
});

/** GET /api/judgments/{job_id}/save-overview — 저장 화면 3.1~3.2 */
export const saveOverviewSchema = z.object({
  job_id: z.string(),
  version: z.number().int().min(1),
  verdicts: z.object({ total: verdictCounts }),
  reviews: z.object({
    미검토: count,
    "불일치 확정": count,
    "예외 승인": count,
    확인: count,
    unreviewed_ids: z.array(z.string()),
  }),
  values: z.object({
    state: z.enum(["미검수", "일부", "완료"]),
    model_as_is: count,
    confirmed: count,
    edited: count,
    fields_total: count,
  }),
  snapshots: z.array(snapshotSchema),
});
export type SaveOverview = z.infer<typeof saveOverviewSchema>;

/** GET /api/judgments/summary?job_ids= 의 한 줄 (목록 화면용) */
export const judgmentSummaryItemSchema = z.object({
  job_id: z.string(),
  state: z.enum(["판정 없음", "판정 중", "판정 있음", "판정 실패"]),
  latest_version: z.number().nullable(),
  unreviewed: count,
  saved_snapshot: z.number().nullable(),
  saved_at: z.string().nullable(),
  data_grade: z.enum(["실버", "골드"]),
});
export type JudgmentSummaryItem = z.infer<typeof judgmentSummaryItemSchema>;

/** GET /api/judgments/{job_id}/versions 의 한 줄 (새 것부터) */
export const versionItemSchema = z.object({
  version: z.number().int().min(1),
  handoff_seq: z.number().int().min(1),
  judged_at: z.string(),
  changed_findings: z.array(z.string()),
});

const job = (id: string) => `/api/judgments/${encodeURIComponent(id)}`;
const send = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const overviewKey = (id: string) => [...judgmentKeys.all(id), "overview"] as const;

/** 저장 화면이 읽는 개요. 저장·검토가 끝나면 judgmentKeys.all(id) 를 무효화해 다시 받는다 */
export const saveOverviewQuery = (id: string) =>
  queryOptions({
    queryKey: overviewKey(id),
    queryFn: ({ signal }) => call(saveOverviewSchema, `${job(id)}/save-overview`, { signal }),
    staleTime: 0,
  });

/**
 * 목록 화면용: 여러 작업의 판정 상태·등급. 서버는 작업 번호(U-날짜-순번) 200개까지만 받아 200개씩 나눠 부르고,
 * 작업 번호가 아닌 것은 보내지 않는다(섞이면 한 번에 422). 일부만 실패하면 받은 것만 돌려주고, 전부 실패하면 오류다.
 * 호출한 쪽은 오류일 때 판정 칸을 "-"로 두고 추출 정보만으로 그린다.
 */
export const judgmentSummaryQuery = (ids: string[]) => {
  const valid = ids.filter(isJobId);
  return queryOptions({
    queryKey: ["judgments", "summary", ...valid] as const,
    queryFn: async ({ signal }) => {
      const results = await Promise.allSettled(
        chunk(valid).map((part) =>
          call(z.array(judgmentSummaryItemSchema), `/api/judgments/summary?job_ids=${encodeURIComponent(part.join(","))}`, { signal }),
        ),
      );
      const ok = results.flatMap((r) => (r.status === "fulfilled" ? r.value : []));
      const failed = results.find((r) => r.status === "rejected");
      if (ok.length === 0 && failed) throw failed.reason;
      return ok;
    },
    enabled: valid.length > 0,
    retry: false,
  });
};

export const versionsQuery = (id: string) =>
  queryOptions({
    queryKey: [...judgmentKeys.all(id), "versions"] as const,
    queryFn: ({ signal }) => call(z.array(versionItemSchema), `${job(id)}/versions`, { signal }),
  });

/** POST /api/judgments/{job_id}/snapshots — 저장. 미검토가 남아도 받고, 낡은 판정이면 409 */
export const postSnapshot = (id: string, body: { reviewer: string; seen_version: number; note?: string | null }) =>
  call(snapshotSchema, `${job(id)}/snapshots`, send(body));

/* ── 리포트 ───────────────────────────────────────────────── */

export type ReportFormat = "html" | "xlsx" | "pdf" | "json";
export type ReportInclude = { regenerated_msds: boolean; findings_2: boolean; findings_15: boolean; components: boolean; history: boolean };
export const ALL_INCLUDE: ReportInclude = { regenerated_msds: true, findings_2: true, findings_15: true, components: true, history: true };

/**
 * Content-Disposition 에서 파일 이름을 읽는다. 서버는 filename*=UTF-8''… 만 주고 html 에는 헤더가 없다.
 * 다른 출처(next dev → API 서버)에서는 서버가 이 헤더를 노출하지 않아 읽을 수 없다: 그때는 fallback 을 쓴다.
 */
export function reportFileName(headers: Headers, fallback: string) {
  const header = headers.get("Content-Disposition") ?? "";
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

/**
 * POST /api/judgments/{job_id}/reports — 리포트 파일을 받는다. snapshot_no 가 없으면 최신 판정으로 만든다(저장 전 미리 보기).
 * 실패(422 글이 빠진 PDF, 404 없는 저장본 등)는 서버 문장을 담은 ApiRequestError 다.
 * 파일 이름은 서버 헤더가 우선이고, 못 읽으면 `${baseName}_MSDS_검토결과.확장자` (서버 이름 규칙: 제품명_MSDS_검토결과.확장자).
 */
export async function requestReport(
  id: string,
  request: { format: ReportFormat; snapshot_no: number | null; include?: ReportInclude },
  baseName?: string,
): Promise<{ blob: Blob; filename: string }> {
  if (process.env.NODE_ENV === "development") {
    const mock = await import("./judgment-mock");
    if (mock.mockActive()) throw new ApiRequestError(404, "unknown", "Not Found");
  }
  const res = await fetch(apiUrl(`${job(id)}/reports`), {
    ...send({ include: ALL_INCLUDE, ...request }),
    headers: { "Content-Type": "application/json", Accept: "*/*" },
  });
  if (!res.ok) throw await toRequestError(res);
  return { blob: await res.blob(), filename: reportFileName(res.headers, `${baseName ?? id}_MSDS_검토결과.${request.format}`) };
}

/* ── 409 ─────────────────────────────────────────────────── */

/** 409 본문(conflict_response)의 이유 칸 */
function conflictDetail(error: unknown): { message: string; pending_handoff: number | null } | null {
  const body = error instanceof ApiRequestError ? (error.data as { detail?: unknown } | undefined) : undefined;
  const detail = body?.detail;
  if (!detail || typeof detail !== "object") return null;
  const { message, pending_handoff } = detail as { message?: unknown; pending_handoff?: unknown };
  return typeof message === "string" ? { message, pending_handoff: typeof pending_handoff === "number" ? pending_handoff : null } : null;
}

/**
 * 검토·저장이 409 로 막혔을 때의 안내. 서버 문장은 "넘김 기록 N을 아직 판정하지 않음" / "최신 판정 버전은 N" /
 * "다른 검토자가 먼저 처리함 (이벤트 N)" 이고, pending_handoff 가 있으면 판정 중이다.
 */
export function conflictText(error: unknown): string {
  const detail = conflictDetail(error);
  if (detail?.pending_handoff != null) return "더 새로운 추출값을 판정하는 중입니다. 판정이 끝난 뒤 새로고침해 주세요.";
  if (detail?.message.startsWith("다른 검토자")) return "다른 검토자가 먼저 처리했습니다. 새로고침해 주세요.";
  return "더 새로운 판정 버전이 있습니다. 새로고침해 주세요.";
}
