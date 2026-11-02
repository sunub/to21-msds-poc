/*
 * 저장 요청. 검수 결과를 서버에 스냅숏으로 남긴다.
 * 명세 미확정, 서버 확정 후 맞출 것: 요청 경로(POST /api/v1/documents/{doc}/snapshots), 요청 본문, 응답 모양은
 * 명세서 방향만 보고 정한 임시 값이다. 개발 중이고 문서 번호가 "demo" 이면 백엔드 없이 데모 응답을 쓴다.
 */
import { z } from "zod";
import { requestJson } from "./client";
import { DEMO_DOC_ID } from "./demo";
import { demoSave } from "./demo-save";

/** 저장 화면의 옵션 (PDF 에 넣을 것) */
export type SaveOptions = { includeRevisionAppendix: boolean; includeOpinions: boolean };

/** 저장에 포함하는 처리 상태 요약 */
export type SaveSummary = { reviewer: string; confirmed: number; exception: number; unresolved: number };

export const saveResponseSchema = z.object({
  snapshot_id: z.string(),
  /** ISO-8601, 시간대 포함 */
  saved_at: z.iso.datetime({ offset: true }),
  included: z.object({
    confirmed: z.int().nonnegative(),
    exception: z.int().nonnegative(),
    unreviewed: z.int().nonnegative(),
  }),
});
export type SaveResponse = z.infer<typeof saveResponseSchema>;

/** demo.fail 은 데모 문서에서만 듣는다 (실패 화면을 백엔드 없이 보려는 용도) */
export const saveDocument = (
  docId: string,
  options: SaveOptions,
  summary: SaveSummary,
  demo?: { fail?: boolean },
): Promise<SaveResponse> =>
  process.env.NODE_ENV !== "production" && docId === DEMO_DOC_ID
    ? demoSave(summary, !!demo?.fail)
    : requestJson(saveResponseSchema, `/api/v1/documents/${encodeURIComponent(docId)}/snapshots`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          options: { include_revision_appendix: options.includeRevisionAppendix, include_opinions: options.includeOpinions },
          reviewer: summary.reviewer,
          review: { confirmed: summary.confirmed, exception_approved: summary.exception, unreviewed: summary.unresolved },
        }),
      });
