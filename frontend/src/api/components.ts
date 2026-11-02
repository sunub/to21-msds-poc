/*
 * 성분별 요약 API 호출과 TanStack Query 설정 (API-14).
 * findings.ts 와 같은 방식이다. 캐시 키는 componentKeys 한 곳에서 만든다.
 */
import { queryOptions } from "@tanstack/react-query";
import { requestJson } from "./client";
import { isDemoDoc, loadDemo } from "@/lib/demo";
import { componentsResponseSchema } from "./components-schemas";

/** product 는 demo 문서에서만 듣는다 (단일물질·판별 불가 화면을 백엔드 없이 보려는 용도). 운영 요청에는 실리지 않는다 */
export type ComponentsParams = { msdsId?: string; product?: "single" | "unknown" };

export const componentKeys = {
  all: ["components"] as const,
  list: (doc: string, validation: string, params: ComponentsParams = {}) =>
    [...componentKeys.all, doc, validation, params] as const,
};

/** API-14. 성분별 요약 */
export const componentsQuery = (doc: string, validation: string, params: ComponentsParams = {}) =>
  queryOptions({
    queryKey: componentKeys.list(doc, validation, params),
    queryFn: async ({ signal }) => {
      if (isDemoDoc(doc)) return (await loadDemo.components()).demoComponents(params.product);
      const query: Record<string, string> = {};
      if (params.msdsId) query.msds_id = params.msdsId;
      return requestJson(
        componentsResponseSchema,
        `/api/v1/documents/${encodeURIComponent(doc)}/validations/${encodeURIComponent(validation)}/components`,
        { query, signal },
      );
    },
  });
