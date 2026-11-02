/*
 * 성분별 요약 API 계약: 명세서 API-14 (GET /api/v1/documents/{doc}/validations/{validation}/components?msds_id=).
 * findings-schemas.ts 와 같은 방식이다. 타입은 스키마에서 z.infer 로 뽑고, 이름은 서버가 보내는 그대로(snake_case) 둔다.
 *
 * 명세 미확정, 서버 확정 후 맞출 것 (우리가 임의로 정한 모양):
 *  - classifications 원소: {source, name, classification, version, basis}. name 은 위험 분류 이름(예: "피부"), classification 은 구분(예: "1"),
 *    source 는 출처(예: "KR02 환경부"), basis 는 기준(예: "TO21 분류기준")으로 보고 쓴다.
 *  - ate_steps 원소: {step, label, input, adopted, value, unit, excluded_reason}. 화면은 6단계를 순서대로 그린다.
 *  - used_ate.reason 은 표의 "사용 ATE (단계)" 칸에 그대로 보여 줄 한 줄 설명으로 보고 쓴다.
 *  - concentration.operator 는 ">=" "<=" 외의 값이면 raw_text 를 그대로 보여 준다.
 *  - source_refs (명세에 없는 필드): 성분이 나온 원문 항·쪽. 원문 칸의 이동 쪽에 쓴다.
 *  - 응답 맨 위 limitations 는 모양을 정하지 않아 객체 목록으로만 받는다.
 * 신뢰도(confidence)는 서버가 계산한 값만 보여 준다. 프론트에서 다시 계산하지 않는다.
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

export const ateStepSchema = z.object({
  /** 1~6. 독성DB 수치, 분류 구분 → 환산값, MSDS 11항 수치, 부등호 값만 있음, 무독성 성분, 자료 없음 */
  step: pageNo,
  label: z.string(),
  /** 값을 가져온 근거 설명 (예: "미스트, 4hr") */
  input: z.string().nullable(),
  adopted: z.boolean(),
  value: z.number().nullable(),
  unit: z.string().nullable(),
  /** 채택하지 않은 이유 (예: "없음", "해당 없음") */
  excluded_reason: z.string().nullable(),
});
export type AteStep = z.infer<typeof ateStepSchema>;

export const usedAteSchema = z.object({
  applicable: z.boolean(),
  reason: z.string(),
  value: z.number().nullable().optional(),
  unit: z.string().nullable().optional(),
  step: pageNo.nullable().optional(),
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
  /** 혼합물만 단계가 온다. 단일물질은 빈 배열 */
  ate_steps: z.array(ateStepSchema),
  used_ate: usedAteSchema,
  legal_findings: z.array(legalFindingRefSchema),
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
