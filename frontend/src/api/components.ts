/*
 * 성분별 요약 API 호출과 TanStack Query 설정 (API-14).
 * findings.ts 와 같은 방식이다. 캐시 키는 componentKeys 한 곳에서 만든다.
 */
import { queryOptions } from "@tanstack/react-query";
import { requestJson } from "./client";
import { componentsResponseSchema, type ComponentsResponse } from "./components-schemas";
import { DEMO_COMPONENTS_MIXTURE, DEMO_COMPONENTS_SINGLE, DEMO_COMPONENTS_UNKNOWN } from "./demo-components";
import { DEMO_DOC_ID } from "./demo";

/** product 는 demo 문서에서만 듣는다 (단일물질·판별 불가 화면을 백엔드 없이 보려는 용도). 운영 요청에는 실리지 않는다 */
export type ComponentsParams = { msdsId?: string; product?: "single" | "unknown" };

export const componentKeys = {
  all: ["components"] as const,
  list: (doc: string, validation: string, params: ComponentsParams = {}) =>
    [...componentKeys.all, doc, validation, params] as const,
};

function demoComponents(product: ComponentsParams["product"]): ComponentsResponse {
  if (product === "single") return DEMO_COMPONENTS_SINGLE;
  if (product === "unknown") return DEMO_COMPONENTS_UNKNOWN;
  return DEMO_COMPONENTS_MIXTURE;
}

/** API-14. 성분별 요약 */
export const componentsQuery = (doc: string, validation: string, params: ComponentsParams = {}) =>
  queryOptions({
    queryKey: componentKeys.list(doc, validation, params),
    queryFn: ({ signal }) => {
      if (process.env.NODE_ENV !== "production" && doc === DEMO_DOC_ID) return demoComponents(params.product);
      const query: Record<string, string> = {};
      if (params.msdsId) query.msds_id = params.msdsId;
      return requestJson(
        componentsResponseSchema,
        `/api/v1/documents/${encodeURIComponent(doc)}/validations/${encodeURIComponent(validation)}/components`,
        { query, signal },
      );
    },
  });
