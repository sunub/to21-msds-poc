/*
 * 성분별 요약 화면이 쓰는 모델. 서버 응답이 아니다: 계약에는 성분 요약 API 가 따로 없고,
 * 판정(judgment_view)의 consistency.results[].components[] (성분별 판단 요약)와 finding 에서 api/adapt/components.ts 가 이 모양을 만든다.
 * 신뢰도(reliability)·기준 분류·ATE·15항 해당 수·ATE 수집 순서 문장(notes)은 서버 값을 그대로 쓴다.
 */
import { z } from "zod";

const count = z.int().nonnegative();
const pageNo = z.int().positive();

/** 단일물질, 혼합물, 판별 못 함. unknown 이면 화면이 자동으로 정하지 않고 사용자 지정을 안내한다 */
export const productTypeSchema = z.enum(["single", "mixture", "unknown"]);
export type ProductType = z.infer<typeof productTypeSchema>;

/** 함량. 수치는 원문이 부등호나 범위가 아니면 null 일 수 있다 */
export const concentrationSchema = z.object({
  raw_text: z.string(),
  min: z.number().nullable(),
  max: z.number().nullable(),
  operator: z.string().nullable(),
  unit: z.string().nullable(),
});
export type Concentration = z.infer<typeof concentrationSchema>;

export const classificationSchema = z.object({
  source: z.string(),
  name: z.string(),
  classification: z.string(),
  version: z.string().nullable(),
  basis: z.string(),
});
export type Classification = z.infer<typeof classificationSchema>;

/** 표의 "사용 ATE (단계)" 칸 한 줄 (서버의 ate[] 를 읽기 좋게 이은 문장) */
export const usedAteSchema = z.object({
  applicable: z.boolean(),
  reason: z.string(),
});
export type UsedAte = z.infer<typeof usedAteSchema>;

export const legalFindingRefSchema = z.object({ finding_id: z.string(), label: z.string() });

export const confidenceSchema = z.object({
  /** 서버가 계산한 값. 아직 계산하지 못했으면 null */
  level: z.enum(["high", "medium", "low"]).nullable(),
  reason: z.string(),
});
export type Confidence = z.infer<typeof confidenceSchema>;

export const componentLimitationSchema = z.object({
  kind: z.enum(["insufficient", "borderline"]),
  reason: z.string(),
  finding_id: z.string().nullable(),
});
export type ComponentLimitation = z.infer<typeof componentLimitationSchema>;

export const targetLinkSchema = z.object({
  section: z.union([z.literal(2), z.literal(15)]),
  finding_id: z.string(),
});
export type TargetLink = z.infer<typeof targetLinkSchema>;

export const componentSummarySchema = z.object({
  component_id: z.string(),
  msds_id: z.string(),
  name: z.string(),
  cas_no: z.string().nullable(),
  concentration: concentrationSchema,
  classifications: z.array(classificationSchema),
  /** 성분 상세에 보일 ATE 수집 순서·가정 문장 (서버 notes). 단일물질은 비어 있다 */
  notes: z.array(z.string()),
  used_ate: usedAteSchema,
  legal_findings: z.array(legalFindingRefSchema),
  /** 15항 해당 판정 수 (서버가 센 값) */
  regulation_hits: count,
  confidence: confidenceSchema,
  limitations: z.array(componentLimitationSchema),
  target_links: z.array(targetLinkSchema),
  /** 명세에 없는 필드 (위 주석 참고) */
  source_refs: z.array(z.object({ section: count, page_no: pageNo })).default([]),
});
export type ComponentSummary = z.infer<typeof componentSummarySchema>;

export const componentsResponseSchema = z.object({
  msds_id: z.string(),
  product_type: productTypeSchema,
  items: z.array(componentSummarySchema),
  selected_component_id: z.string().nullable(),
  limitations: z.array(z.record(z.string(), z.unknown())),
  confidence_rule_version: z.string().nullable(),
});
export type ComponentsResponse = z.infer<typeof componentsResponseSchema>;
