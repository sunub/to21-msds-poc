/*
 * 2항·15항 판정 API 호출과 TanStack Query 설정.
 * documents.ts 와 같은 방식이다. 캐시 키는 findingKeys 한 곳에서 만든다.
 */
import { queryOptions } from "@tanstack/react-query";
import { isDemoDoc, loadDemo } from "@/lib/demo";
import { requestJson } from "./client";
import { findingDetailSchema, findingsResponseSchema, type Verdict } from "./findings-schemas";

export type FindingsParams = { verdict?: Verdict; section?: 2 | 15 };

const validationPath = (doc: string, validation: string) =>
  `/api/v1/documents/${encodeURIComponent(doc)}/validations/${encodeURIComponent(validation)}`;

export const findingKeys = {
  all: ["findings"] as const,
  list: (doc: string, validation: string, params: FindingsParams = {}) =>
    [...findingKeys.all, doc, validation, "list", params] as const,
  detail: (doc: string, validation: string, findingId: string) =>
    [...findingKeys.all, doc, validation, "detail", findingId] as const,
};

/** API-12. 판정 목록 */
export const findingsQuery = (doc: string, validation: string, params: FindingsParams = {}) =>
  queryOptions({
    queryKey: findingKeys.list(doc, validation, params),
    queryFn: async ({ signal }) => {
      if (isDemoDoc(doc)) return (await loadDemo.findings()).demoFindingsResponse(params);
      const query: Record<string, string> = {};
      if (params.verdict) query.verdict = params.verdict;
      if (params.section) query.section = String(params.section);
      return requestJson(findingsResponseSchema, `${validationPath(doc, validation)}/findings`, { query, signal });
    },
  });

/** API-13. 판정 한 건의 상세 */
export const findingDetailQuery = (doc: string, validation: string, findingId: string) =>
  queryOptions({
    queryKey: findingKeys.detail(doc, validation, findingId),
    queryFn: async ({ signal }) =>
      isDemoDoc(doc)
        ? (await loadDemo.findings()).demoFindingDetailOrThrow(findingId)
        : requestJson(
            findingDetailSchema,
            `${validationPath(doc, validation)}/findings/${encodeURIComponent(findingId)}`,
            { signal },
          ),
  });
