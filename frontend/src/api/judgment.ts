/*
 * 판정 API(B2, /api/judgments)의 화면 쪽 입구. 계약: docs/superpowers/specs/contracts/3-consistency·5-api.
 * 화면이 읽는 칸만 확인한다. 나머지 칸은 버리므로 B2가 칸을 더해도 화면은 깨지지 않는다.
 * 서버가 아직 없으면 경로가 404 라 isJudgmentApiMissing 으로 "연결 전"을 가려낸다. 경로가 생기면 고칠 곳이 없다.
 */
import { queryOptions } from "@tanstack/react-query";
import { z } from "zod";
import { ApiContractError, ApiRequestError, isPermanentError, requestJson } from "./client";

const POLL_MS = 2_000;

export const VERDICTS = ["일치", "불일치", "경계", "근거부족", "경고", "참고", "범위 외"] as const;
export const REVIEW_ACTIONS = ["불일치 확정", "예외 승인", "확인", "의견", "되돌리기"] as const;

const evidenceSchema = z.object({
  field: z.string(),
  page: z.number().nullable(),
  source_text: z.string().nullable().optional(),
});

const sideSchema = z.object({
  present: z.boolean(),
  source: z.string().nullable().optional(),
  evidence: z.array(evidenceSchema).optional(),
  effective_from: z.string().nullable().optional(),
});

export const findingSchema = z.object({
  id: z.string().regex(/^m\d+\/(F2|F2L|F15|F15DG|FPT):\S+$/),
  section: z.enum(["2", "15"]),
  kind: z.enum(["class", "label", "regulation", "dangerous_goods", "product_type"]),
  item: z.string(),
  comp: z.object({ comp_ref: z.string(), cas: z.string().nullable(), name: z.string().nullable() }).nullable(),
  msds: sideSchema,
  expected: sideSchema,
  verdict: z.enum(VERDICTS),
  type: z.enum(["과소분류", "규제 누락", "형태·세부 표기", "기준 불일치", "구버전", "표시 요소 불일치", "과대분류", "과기재", "내부 불일치", "화평법 항목 누락"]).nullable(),
  severity: z.enum(["높음", "중간", "낮음"]).nullable(),
  needs_explanation: z.boolean(),
  label: z.string().min(1),
  method: z.string().min(1),
  out_of_scope_reason: z.enum(["해당 없음", "대조만", "구버전 제외", "해외 규제"]).nullable(),
  law_label: z.enum(["산안법", "화관법", "화평법", "위험물법", "폐기물법", "POPs법", "기타 국내", "해외"]).nullable(),
});

const explanationSchema = z.discriminatedUnion("status", [
  z.object({ status: z.literal("작성 중") }),
  z.object({
    status: z.literal("완료"),
    by: z.enum(["llm", "template"]),
    checked: z.boolean(),
    summary: z.string(),
    reasons: z.array(z.string()),
    basis: z.array(z.string()),
  }),
]);

const reviewStateSchema = z.object({
  status: z.enum(["미검토", "불일치 확정", "예외 승인", "확인"]),
  comment: z.string().nullable(),
  reviewer: z.string().nullable(),
  at: z.string().nullable(),
  history_count: z.number(),
  stale: z.boolean(),
  /** 이 줄의 마지막 처리 번호. 처리할 때 그대로 돌려보내 다른 검토자의 처리를 모르고 덮지 않게 한다 */
  last_event_id: z.number().nullable().optional(),
});

const displaySchema = z.object({
  msds: z.string(),
  expected: z.string(),
  component: z.string().nullable(),
  basis_lines: z.array(z.string()),
  calc_lines: z.array(z.string()),
  source_pages: z.array(z.object({ section: z.number(), page: z.number() })),
});

/** TO21 수치 묶음(Q). 화면이 함량을 적는 데 쓰는 칸만 본다 */
const quantitySchema = z.object({
  raw: z.string().nullable().optional(),
  value: z.number().nullable().optional(),
  lower_op: z.string().nullable().optional(),
  lower: z.number().nullable().optional(),
  upper_op: z.string().nullable().optional(),
  upper: z.number().nullable().optional(),
  unit: z.string().nullable().optional(),
});

const routeFormSchema = z.enum(["가스", "증기", "분진·미스트"]).nullable();

/** 성분별 판단 요약 한 줄 (3-consistency component_summary). 단일물질이면 한 줄 */
export const componentSummarySchema = z.object({
  comp_ref: z.string(),
  name: z.string().nullable(),
  cas: z.string().nullable(),
  content: quantitySchema.nullable(),
  reference_classes: z.array(
    z.object({ class_code: z.string(), category: z.string(), route_form: routeFormSchema, source: z.string() }),
  ),
  ate: z.array(
    z.object({
      route: z.enum(["oral", "dermal", "inhal"]),
      value: z.number().nullable(),
      unit: z.string().nullable(),
      form: routeFormSchema,
      source: z.string().nullable(),
      step: z.number().int().nullable(),
      excluded: z.string().nullable(),
    }),
  ),
  regulation_hits: z.number().int().min(0),
  reliability: z.enum(["높음", "보통", "낮음"]),
  notes: z.array(z.string()),
});

/** 제약사항·검토 필요 (3-consistency msds_result.limitations) */
export const limitationSchema = z.object({ finding_id: z.string().nullable(), text: z.string() });

export const judgmentStatusSchema = z.object({
  job_id: z.string(),
  state: z.enum(["판정 없음", "판정 중", "판정 있음", "판정 실패"]),
  latest_version: z.number().nullable(),
  pending_handoff: z.number().nullable(),
  explanations: z.object({ done: z.number(), total: z.number() }),
  saved_snapshot: z.number().nullable(),
  error: z.string().nullable().optional(),
});

export const judgmentViewSchema = z
  .object({
    job_id: z.string(),
    version: z.number(),
    is_latest: z.boolean(),
    handoff_seq: z.number(),
    judged_at: z.string(),
    consistency: z.object({
      as_of: z.string(),
      knowledge: z.object({ provider: z.string(), version: z.string() }),
      results: z
        .array(
          z.object({
            msds_index: z.number(),
            msds_revision_date: z.string().nullable(),
            product_type: z.object({ value: z.string() }),
            findings: z.array(findingSchema),
            // 계약에서는 필수지만 판정 API가 아직 채우는 중이라 없어도 받는다. 없으면 성분별 요약 탭만 "요약 없음"이 된다
            components: z.array(componentSummarySchema).optional(),
            limitations: z.array(limitationSchema).optional(),
          }),
        )
        .min(1),
    }),
    explanations: z.record(z.string(), explanationSchema),
    reviews: z.record(z.string(), reviewStateSchema),
    display: z.record(z.string(), displaySchema),
  })
  .superRefine((view, ctx) => {
    // 표에 찍을 문장이 없는 판정이 하나라도 있으면 일부만 그리지 않고 계약 위반으로 본다
    for (const result of view.consistency.results) {
      for (const finding of result.findings) {
        if (!view.display[finding.id]) {
          ctx.addIssue({ code: "custom", path: ["display", finding.id], message: "표시 문장이 없습니다" });
        }
      }
    }
  });

export const reviewEventSchema = z.object({ event_id: z.number(), finding_id: z.string(), action: z.enum(REVIEW_ACTIONS) });
export const toJudgmentResponseSchema = z.object({ job_id: z.string(), handoff_seq: z.number() });

export type Finding = z.infer<typeof findingSchema>;
export type ComponentSummary = z.infer<typeof componentSummarySchema>;
export type Limitation = z.infer<typeof limitationSchema>;
export type MsdsResult = JudgmentView["consistency"]["results"][number];
export type FindingDisplay = z.infer<typeof displaySchema>;
export type ReviewState = z.infer<typeof reviewStateSchema>;
export type Explanation = z.infer<typeof explanationSchema>;
export type JudgmentStatus = z.infer<typeof judgmentStatusSchema>;
export type JudgmentView = z.infer<typeof judgmentViewSchema>;
export type ReviewAction = (typeof REVIEW_ACTIONS)[number];
export type ReviewEventRequest = {
  finding_id: string;
  action: ReviewAction;
  comment: string | null;
  reviewer: string;
  seen_version: number;
  /** 화면이 본 마지막 처리 번호. 기록이 없는 줄은 null */
  seen_event_id: number | null;
};

/** 개발 서버에서 ?judgmentMock=<상황> 을 켜면 대역이 답한다. 제품 빌드에는 대역 코드가 들어가지 않는다 */
export async function call<S extends z.ZodType>(schema: S, path: string, init?: RequestInit): Promise<z.infer<S>> {
  if (process.env.NODE_ENV === "development") {
    const mock = await import("./judgment-mock");
    if (mock.mockActive()) {
      const parsed = schema.safeParse(await mock.mockResponse(path, init));
      if (!parsed.success) throw new ApiContractError(path, parsed.error.issues);
      return parsed.data;
    }
  }
  return requestJson(schema, path, init);
}

/** 경로 자체가 없는 404. 없는 작업 번호의 404 는 서버가 문장을 주므로 구분된다 */
export function isJudgmentApiMissing(error: unknown) {
  return error instanceof ApiRequestError && error.status === 404 && (error.message === "Not Found" || error.code === "unknown");
}

/** 그 사이 새 판정이 생겼거나 다른 검토자가 먼저 처리해 서버가 처리를 거절함. 까닭은 서버 문장에 있다 */
export const isVersionConflict = (error: unknown): error is ApiRequestError =>
  error instanceof ApiRequestError && error.status === 409;

const job = (id: string) => `/api/judgments/${encodeURIComponent(id)}`;
const send = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const judgmentKeys = {
  all: (id: string) => ["judgments", id] as const,
  status: (id: string) => [...judgmentKeys.all(id), "status"] as const,
  view: (id: string, version: number) => [...judgmentKeys.all(id), "view", version] as const,
};

/** 판정 중이거나, 다시 판정할 넘김 기록이 있거나, 설명을 쓰는 동안에만 다시 묻는다 */
export const judgmentStatusQuery = (id: string) =>
  queryOptions({
    queryKey: judgmentKeys.status(id),
    queryFn: ({ signal }) => call(judgmentStatusSchema, `${job(id)}/status`, { signal }),
    staleTime: 0,
    refetchInterval: (query) => {
      if (isPermanentError(query.state.error)) return false;
      const s = query.state.data;
      if (!s) return false;
      return s.state === "판정 중" || s.pending_handoff !== null || s.explanations.done < s.explanations.total ? POLL_MS : false;
    },
  });

/** 버전을 키에 넣는다. 새 버전이 생겨도 읽던 표가 저절로 바뀌지 않는다. 설명을 쓰는 동안에는 같은 버전을 다시 받는다 */
export const judgmentViewQuery = (id: string, version: number) =>
  queryOptions({
    queryKey: judgmentKeys.view(id, version),
    queryFn: ({ signal }) => call(judgmentViewSchema, `${job(id)}?version=${version}`, { signal }),
    refetchInterval: (query) => {
      if (isPermanentError(query.state.error)) return false;
      const pending = Object.values(query.state.data?.explanations ?? {}).some((e) => e.status === "작성 중");
      return pending ? POLL_MS : false;
    },
  });


export const postJudgmentReview = (id: string, body: ReviewEventRequest) =>
  call(reviewEventSchema, `${job(id)}/reviews`, send(body));

/** A2 경로. 추출값을 판정으로 넘겨 넘김 기록을 만든다 */
export const postToJudgment = (id: string, reviewer: string) =>
  call(toJudgmentResponseSchema, `/api/documents/${encodeURIComponent(id)}/to-judgment`, send({ reviewer }));
