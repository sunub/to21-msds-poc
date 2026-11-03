/*
 * 검토 이력 API. 계약: contracts/5-api history_entry.
 * 추출값 이력(A2 /api/documents/{id}/review/log)과 판정 이력(B2 /api/judgments/{id}/history)은 모양이 같고 서버가 다르다.
 * 둘 다 아직 없다. 경로가 생기면 화면을 고치지 않고 이어진다.
 */
import { queryOptions } from "@tanstack/react-query";
import { z } from "zod";
import { documentKeys } from "./documents";
import { call, judgmentKeys } from "./judgment";

export const historyEntrySchema = z.object({
  at: z.string().refine((v) => !Number.isNaN(Date.parse(v)), "시각을 읽을 수 없습니다"),
  reviewer: z.string(),
  area: z.enum(["추출값", "2항", "15항", "저장"]),
  target: z.string(),
  action: z.string(),
  detail: z.string().nullable(),
  comment: z.string().nullable(),
  // 계약의 ref 는 형식이 정해져 있지 않다. 맞지 않는 값은 버리고 이동 칸만 덜 정확해지게 한다
  ref: z
    .object({ finding_id: z.string().optional(), msds_index: z.number().optional(), path: z.string().optional() })
    .optional()
    .catch(undefined),
});
export type HistoryEntry = z.infer<typeof historyEntrySchema>;

const historyListSchema = z.array(historyEntrySchema);

export const valuesLogKey = (id: string) => [...documentKeys.detail(id), "review-log"] as const;
export const judgmentHistoryKey = (id: string) => [...judgmentKeys.all(id), "history"] as const;

// 다른 탭에서 처리하고 돌아오면 바로 보이도록 열 때마다 다시 받는다
export const valuesLogQuery = (id: string) =>
  queryOptions({
    queryKey: valuesLogKey(id),
    queryFn: ({ signal }) => call(historyListSchema, `/api/documents/${encodeURIComponent(id)}/review/log`, { signal }),
    staleTime: 0,
  });

export const judgmentHistoryQuery = (id: string) =>
  queryOptions({
    queryKey: judgmentHistoryKey(id),
    queryFn: ({ signal }) => call(historyListSchema, `/api/judgments/${encodeURIComponent(id)}/history`, { signal }),
    staleTime: 0,
  });
