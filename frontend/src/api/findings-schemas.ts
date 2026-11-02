/*
 * 2항 판정(검증 결과) API 계약: 명세서 API-12·API-13 응답 모양.
 * schemas.ts 와 같은 방식이다. 타입은 스키마에서 z.infer 로 뽑고, 이름은 서버가 보내는 그대로(snake_case) 둔다.
 */
import { z } from "zod";

const count = z.int().nonnegative();
const pageNo = z.int().positive();
/** 기준일 YYYY-MM-DD */
const day = z.iso.date();

/* ── 공통 값 ─────────────────────────────────────────────── */

/** 일치·불일치·경계·근거부족·경고·구버전·해당 없음·비교 제외 (명세서 용어) */
export const verdictSchema = z.enum([
  "match",
  "mismatch",
  "borderline",
  "insufficient_evidence",
  "warning",
  "outdated",
  "not_applicable",
  "excluded",
]);
export type Verdict = z.infer<typeof verdictSchema>;

export const severitySchema = z.enum(["high", "medium", "low"]).nullable();
export type Severity = z.infer<typeof severitySchema>;

/** 미검토·확정·예외 승인·의견만 남김 (명세서 용어) */
export const reviewStateSchema = z.enum(["unreviewed", "confirmed", "exception_approved", "opinion"]);
export type ReviewState = z.infer<typeof reviewStateSchema>;

/** 원문 근거 한 곳. bbox 는 아직 항상 null */
export const sourceRefSchema = z.object({
  page_no: pageNo,
  bbox: z.null(),
  input_path: z.string(),
});
export type SourceRef = z.infer<typeof sourceRefSchema>;

const valueText = z.object({ text: z.string() });

/** 15항 판정 중 성분에 걸리지 않는 제품 단위 판정의 묶음 번호 (판정의 component_id 는 null 로 오고, 묶음은 이 값으로 온다) */
export const PRODUCT_GROUP_ID = "product";

/* ── API-12 GET .../validations/{validation_id}/findings ── */

export const findingSummarySchema = z.object({
  finding_id: z.string(),
  validation_id: z.string(),
  msds_id: z.string(),
  /** 판정 대상 항: 2(유해성·위험성) 또는 15(법적 규제) */
  section: z.union([z.literal(2), z.literal(15)]),
  item: z.string(),
  law: z.string().nullable(),
  component_id: z.string().nullable(),
  msds_value: valueText,
  expected_value: valueText,
  method: z.string(),
  verdict: verdictSchema,
  severity: severitySchema,
  review_state: reviewStateSchema,
  opinion_count: count,
  trace_id: z.string(),
  source_refs: z.array(sourceRefSchema),
});
export type FindingSummary = z.infer<typeof findingSummarySchema>;

export const findingsResponseSchema = z.object({
  validation_id: z.string(),
  extraction_id: z.string(),
  review_revision: count,
  items: z.array(findingSummarySchema),
  page: z.int().positive(),
  page_size: z.int().positive(),
  total: count,
  /** 판정(verdict)별 건수 */
  counts: z.record(z.string(), count),
  /** 판정에서 빠진 건수 (not_applicable·excluded) */
  excluded_counts: z.record(z.string(), count),
  groups: z.array(
    z.object({
      component_id: z.string(),
      title: z.string(),
      total: count,
      matching_count: count,
    }),
  ),
});
export type FindingsResponse = z.infer<typeof findingsResponseSchema>;

/* ── API-13 GET .../findings/{finding_id} ────────────────── */

export const explanationSchema = z.object({
  text: z.string(),
  source: z.enum(["ai", "template", "unavailable"]),
  check_status: z.enum(["passed", "failed", "not_checked"]),
  limitations: z.array(z.string()),
});
export type Explanation = z.infer<typeof explanationSchema>;

/** 판정에 쓴 규칙과 계산 과정 */
export const traceSchema = z.object({
  trace_id: z.string(),
  rule: z.object({ id: z.string(), version: z.string() }),
  /** 계산 과정 줄들 */
  inputs: z.array(z.string()),
  thresholds: z.array(z.string()),
  assumptions: z.array(z.string()),
});
export type Trace = z.infer<typeof traceSchema>;

export const findingDetailSchema = z.object({
  finding: findingSummarySchema,
  explanation: explanationSchema,
  trace: traceSchema.nullable(),
  evidence: z.array(sourceRefSchema),
  review: z.object({ state: reviewStateSchema, opinions: z.array(z.string()) }),
  law_effective_date: day.nullable(),
  msds_revision_date: day.nullable(),
  reference_date: day,
});
export type FindingDetail = z.infer<typeof findingDetailSchema>;
