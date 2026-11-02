/*
 * 문서 API 호출과 TanStack Query 설정.
 * 화면은 fetch 를 직접 부르지 않고 여기 있는 queryOptions·함수만 쓴다.
 * 캐시 키는 documentKeys 한 곳에서 만든다 (무효화할 때 같은 키를 쓰도록).
 */
import { queryOptions } from "@tanstack/react-query";
import { apiUrl, isPermanentError, requestJson } from "./client";
import { DEMO_ENABLED, isDemoDoc, loadDemo } from "@/lib/demo";
import {
  FINAL_STATUSES,
  createDocumentParamsSchema,
  createDocumentResponseSchema,
  documentDetailSchema,
  documentListResponseSchema,
  healthResponseSchema,
  pageLinesResponseSchema,
  regeneratedResponseSchema,
  resultResponseSchema,
  retryResponseSchema,
  reviewResponseSchema,
  sectionResultResponseSchema,
  type CreateDocumentParams,
  type DocumentFilter,
  type FieldReviewRequest,
  type SectionReviewRequest,
} from "./schemas";

/** 진행 상태를 다시 묻는 간격 */
const PROGRESS_POLL_MS = 2_000;

const doc = (id: string) => `/api/documents/${encodeURIComponent(id)}`;

export const documentKeys = {
  all: ["documents"] as const,
  /** 보기(status)와 상관없이 목록 전부. 올리거나 다시 돌린 뒤 무효화할 때 쓴다 */
  lists: () => [...documentKeys.all, "list"] as const,
  list: (status: DocumentFilter) => [...documentKeys.lists(), status] as const,
  detail: (id: string) => [...documentKeys.all, id] as const,
  lines: (id: string, page: number) => [...documentKeys.detail(id), "lines", page] as const,
  result: (id: string) => [...documentKeys.detail(id), "result"] as const,
  review: (id: string) => [...documentKeys.detail(id), "review"] as const,
  regenerated: (id: string) => [...documentKeys.detail(id), "regenerated"] as const,
  section: (id: string, msdsIndex: number, section: number) =>
    [...documentKeys.detail(id), "section", msdsIndex, section] as const,
};

/* ── 읽기 ───────────────────────────────────────────────── */

/** 모델 태그 확인 */
export const healthQuery = () =>
  queryOptions({
    queryKey: ["health"] as const,
    queryFn: ({ signal }) => requestJson(healthResponseSchema, "/api/health", { signal }),
  });

/** 목록을 다시 묻는 간격 (처리 중인 문서가 있을 때만) */
const LIST_POLL_MS = 5_000;

/** 2. 1.1 목록. 대기·처리 중인 문서가 있으면 단계·진행이 바뀌므로 그동안만 다시 묻는다. */
export const documentListQuery = (status: DocumentFilter = "all") =>
  queryOptions({
    queryKey: documentKeys.list(status),
    queryFn: async ({ signal }) => {
      // 데모 모드에서는 서버가 없어도 목록이 비지 않도록 데모 문서를 앞에 섞는다 (서버 오류는 데모 문서만 보인다)
      const real = await requestJson(documentListResponseSchema, "/api/documents", { query: { status }, signal }).catch((e: unknown) => {
        if (DEMO_ENABLED) return null;
        throw e;
      });
      if (!DEMO_ENABLED) return real!;
      const demo = (await loadDemo.detail()).demoList(status);
      if (!real) return demo;
      const sum = (k: keyof typeof demo.counts) => demo.counts[k] + real.counts[k];
      return { items: [...demo.items, ...real.items], counts: { all: sum("all"), active: sum("active"), done: sum("done"), failed: sum("failed") } };
    },
    refetchInterval: (query) => ((query.state.data?.counts.active ?? 0) > 0 ? LIST_POLL_MS : false),
  });

/**
 * 3. 머리글과 1.2·1.3 진행 상태 (같은 응답). 끝난 상태(done·failed·interrupted)에 이르면 폴링을 멈춘다.
 * 없는 문서(404)처럼 다시 물어도 같은 실패면 멈춘다. 연결이 끊긴 동안은 계속 물어 돌아오면 이어서 보여 준다.
 * 진행 중에는 매번 새로 받아야 하므로 staleTime 을 0 으로 둔다.
 */
export const documentDetailQuery = (id: string) =>
  queryOptions({
    queryKey: documentKeys.detail(id),
    queryFn: async ({ signal }) =>
      isDemoDoc(id) ? (await loadDemo.detail()).demoDetail(id) : requestJson(documentDetailSchema, doc(id), { signal }),
    staleTime: 0,
    refetchInterval: (query) => {
      if (isPermanentError(query.state.error)) return false;
      const status = query.state.data?.status;
      return status && FINAL_STATUSES.includes(status) ? false : PROGRESS_POLL_MS;
    },
  });

/** 4. 쪽 이미지는 <img src> 로 바로 쓴다. 전처리 전이면 404 라 onError 로 자리 표시를 보여 준다. */
export const pageImageUrl = (id: string, page: number) => apiUrl(`${doc(id)}/pages/${page}/image`);

/** 5. 원문 칸 */
export const pageLinesQuery = (id: string, page: number) =>
  queryOptions({
    queryKey: documentKeys.lines(id, page),
    queryFn: async ({ signal }) =>
      isDemoDoc(id)
        ? (await loadDemo.pages()).demoPageLines(page)
        : requestJson(pageLinesResponseSchema, `${doc(id)}/pages/${page}/lines`, { signal }),
    // 전처리가 끝난 쪽의 원문은 바뀌지 않는다
    staleTime: Infinity,
  });

/** 6. 추출이 끝난 뒤의 결과 (끝나기 전에는 409) */
export const resultQuery = (id: string) =>
  queryOptions({
    queryKey: documentKeys.result(id),
    queryFn: ({ signal }) => requestJson(resultResponseSchema, `${doc(id)}/result`, { signal }),
  });

/** 끝난 문서의 재생성 MSDS. 끝나기 전에는 409 이므로 status 가 done 일 때만 켠다(enabled). */
export const regeneratedQuery = (id: string) =>
  queryOptions({
    queryKey: documentKeys.regenerated(id),
    queryFn: ({ signal }) => requestJson(regeneratedResponseSchema, `${doc(id)}/regenerated`, { signal }),
  });

/**
 * 끝난 항 하나의 값 (추출 중에도 받는다). 안 끝난 항이면 409 이므로
 * 진행 상태의 sections[].status 가 done·failed 인 항에만 켠다(enabled).
 * 다시 돌리면 값이 바뀌므로 staleTime 을 무한으로 두지 않는다.
 */
export const sectionResultQuery = (id: string, msdsIndex: number, section: number) =>
  queryOptions({
    queryKey: documentKeys.section(id, msdsIndex, section),
    queryFn: ({ signal }) =>
      requestJson(sectionResultResponseSchema, `${doc(id)}/sections/${msdsIndex}/${section}`, { signal }),
  });

/** 2.2 항별 칸과 검수 기록. 끝나기 전에는 409 이므로 status 가 done 일 때만 켠다(enabled). */
export const reviewQuery = (id: string) =>
  queryOptions({
    queryKey: documentKeys.review(id),
    queryFn: ({ signal }) => requestJson(reviewResponseSchema, `${doc(id)}/review`, { signal }),
  });

/* ── 쓰기 ───────────────────────────────────────────────── */

/** 1. PDF 올리기. 본문은 PDF 바이트 그대로, filename·as_of 는 쿼리. */
export function createDocument(file: Blob, params: CreateDocumentParams) {
  const { filename, as_of } = createDocumentParamsSchema.parse(params);
  const query: Record<string, string> = as_of ? { filename, as_of } : { filename };
  return requestJson(createDocumentResponseSchema, "/api/documents", {
    method: "POST",
    headers: { "Content-Type": "application/pdf" },
    body: file,
    query,
  });
}

/** 7. 실패·멈춘 문서를 처음부터 다시 (그 밖의 상태면 409) */
export function retryDocument(id: string) {
  return requestJson(retryResponseSchema, `${doc(id)}/retry`, { method: "POST" });
}

const jsonBody = (body: unknown) => ({
  method: "PUT",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

/** 칸 하나 확인·수정·되돌림. 바뀐 뒤의 전체 보기를 돌려준다 */
export function saveFieldReview(id: string, body: FieldReviewRequest) {
  return requestJson(reviewResponseSchema, `${doc(id)}/review/fields`, jsonBody(body));
}

/** 항 하나 확인 완료·취소 */
export function saveSectionReview(id: string, body: SectionReviewRequest) {
  return requestJson(reviewResponseSchema, `${doc(id)}/review/sections`, jsonBody(body));
}
