/*
 * 2항·15항 판정 API 호출과 TanStack Query 설정.
 * documents.ts 와 같은 방식이다. 캐시 키는 findingKeys 한 곳에서 만든다.
 */
import { queryOptions } from "@tanstack/react-query";
import { ApiRequestError, requestJson } from "./client";
import { DEMO_FINDINGS, DEMO_FINDINGS_15, demoFindingDetail } from "./demo-findings";
import {
  findingDetailSchema,
  findingsResponseSchema,
  type FindingDetail,
  type FindingsResponse,
  type Verdict,
} from "./findings-schemas";

/** 개발 중에 문서 번호가 "demo" 이면 백엔드 없이 고정 데이터를 쓴다 */
const DEMO_DOC_ID = "demo";
const isDemo = (doc: string) => process.env.NODE_ENV !== "production" && doc === DEMO_DOC_ID;

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

/** 항(section)에 맞는 고정 응답. 항을 안 정하면 2항과 15항을 합친다 (counts 는 합산) */
function demoBase(section?: 2 | 15): FindingsResponse {
  if (section === 2) return DEMO_FINDINGS;
  if (section === 15) return DEMO_FINDINGS_15;
  const counts = { ...DEMO_FINDINGS.counts };
  for (const [k, n] of Object.entries(DEMO_FINDINGS_15.counts)) counts[k] = (counts[k] ?? 0) + n;
  const items = [...DEMO_FINDINGS.items, ...DEMO_FINDINGS_15.items];
  return { ...DEMO_FINDINGS, items, total: items.length, counts, groups: [...DEMO_FINDINGS.groups, ...DEMO_FINDINGS_15.groups] };
}

/** 걸러진 목록. total 은 거른 개수다 (counts·groups 는 항 기준 전체, 거르기 전 그대로) */
function demoFindings(params: FindingsParams): FindingsResponse {
  const base = demoBase(params.section);
  const items = base.items.filter((f) => !params.verdict || f.verdict === params.verdict);
  return { ...base, items, total: items.length };
}

function demoDetail(findingId: string): FindingDetail {
  const detail = demoFindingDetail(findingId);
  if (!detail) throw new ApiRequestError(404, "http_404", "판정을 찾을 수 없습니다.");
  return detail;
}

/** API-12. 판정 목록 */
export const findingsQuery = (doc: string, validation: string, params: FindingsParams = {}) =>
  queryOptions({
    queryKey: findingKeys.list(doc, validation, params),
    queryFn: ({ signal }) => {
      if (isDemo(doc)) return demoFindings(params);
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
    queryFn: ({ signal }) =>
      isDemo(doc)
        ? demoDetail(findingId)
        : requestJson(
            findingDetailSchema,
            `${validationPath(doc, validation)}/findings/${encodeURIComponent(findingId)}`,
            { signal },
          ),
  });
