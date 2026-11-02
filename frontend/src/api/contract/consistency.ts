/*
 * 계약 3-consistency.schema.json (약속 ③ 판정 결과) 을 zod 로 옮긴 것.
 * 계약과 한 글자도 다르지 않게 옮긴다. 계약에 없는 필드는 만들지 않는다.
 */
import { z } from "zod";
import * as c from "./common";

/** 한쪽(MSDS 기재 또는 검증 결과)의 값. kind 에 따라 쓰는 칸이 다르다 */
const sideShape = {
  present: z.boolean(),
  /** class: 구분 (1, 1A, 2 …) */
  category: z.string().nullable().optional(),
  route_form: c.routeForm.optional(),
  /** label: H코드·그림문자 코드·신호어 */
  code: z.string().nullable().optional(),
  /** regulation: 해당 여부 */
  applicable: c.applicable.nullable().optional(),
  /** regulation: 기준 농도 (TO21 Q 구조) */
  threshold: c.Q.nullable().optional(),
  /** regulation·class: 판정에 쓴 성분 함량 (TO21 Q 구조) */
  content: c.Q.nullable().optional(),
  /** dangerous_goods: 류·품명·수용성·등급 */
  dg: z
    .strictObject({
      class: z.string().nullable().optional(),
      item: z.string().nullable().optional(),
      water_soluble: z.boolean().nullable().optional(),
      grade: z.string().nullable().optional(),
    })
    .nullable()
    .optional(),
  product_type: z.enum(["단일물질", "혼합물", "불명확"]).nullable().optional(),
  /** expected 쪽: 기준정보 출처 (예: KR02 환경부, TO21 독성DB, MSDS 11항) */
  source: z.string().nullable().optional(),
  evidence: z.array(c.evidenceRef).optional(),
};

/** MSDS 기재값. 없으면 present=false */
export const msdsSide = z.strictObject(sideShape);

/** 엔진의 검증 결과. 함량 범위로 갈리면 low·high 가 다르고 status=경계 */
export const expectedSide = z.strictObject({
  ...sideShape,
  status: z.enum(["확정", "경계", "근거부족"]),
  low: z.string().nullable().optional(),
  high: z.string().nullable().optional(),
});

const traceId = z.string().regex(/^T-\d{4,}$/);

export const finding = z.strictObject({
  id: c.findingId,
  section: z.enum(["2", "15"]),
  /** class = 2항 유해성 분류 / label = 2항 표시 요소 / regulation = 15항 규제 / dangerous_goods = 15항 위험물 / product_type = 단일·혼합 판별 */
  kind: z.enum(["class", "label", "regulation", "dangerous_goods", "product_type"]),
  /** class: class_code / label: H코드·그림문자 코드·SIGNAL / regulation: law.item_code / dangerous_goods: DG / product_type: TYPE */
  item: z.string(),
  /** 성분 단위 판정이면 그 성분. 제품 전체면 null */
  comp: z
    .strictObject({
      /** 추출스키마 comp_ref (성분 seq 또는 MIX) */
      comp_ref: z.string(),
      cas: z.string().nullable(),
      name: z.string().nullable(),
    })
    .nullable(),
  msds: msdsSide,
  expected: expectedSide,
  verdict: c.verdict,
  type: c.mismatchType,
  severity: c.severity,
  /** 적용 규칙 ID (규칙표 v0.3 rule_id). 없으면 null */
  rule: z.string().nullable(),
  causes: z.array(c.causeCode),
  trace_id: traceId.nullable(),
  /** verdict 가 불일치·경계·근거부족이면 true. B2는 이것만 설명을 만든다 */
  needs_explanation: z.boolean(),
});

/** 판정 근거 (설계서 v0.4 trace 반환 규격). 계산이 없는 판정(단순 조회·비교)은 steps 만 채운다 */
export const trace = z.strictObject({
  kind: z.enum(["mixture_calc", "reference_lookup", "regulation_check", "label_check", "dg_check", "product_type"]),
  class_code: c.classCode.nullable().optional(),
  form: c.routeForm.optional(),
  result: z
    .strictObject({
      low: z.string().nullable(),
      high: z.string().nullable(),
      status: z.enum(["확정", "경계", "근거부족"]),
    })
    .optional(),
  rule: z.strictObject({
    id: z.string(),
    /** 예: 고시 별표1 */
    basis: z.string(),
    formula: z.string().nullable().optional(),
  }),
  inputs: z.array(
    z.strictObject({
      cas: z.string().nullable(),
      name: z.string().nullable(),
      content: z
        .strictObject({ low: z.number().nullable().optional(), high: z.number().nullable().optional() })
        .optional(),
      value: z
        .strictObject({
          /** LD50·LC50·L(E)C50·NOEC 등 */
          type: z.string().optional(),
          op: z.enum(["=", ">", ">=", "<", "<="]).optional(),
          v: z.number().optional(),
          unit: z.string().optional(),
          hours: z.number().nullable().optional(),
          form: c.routeForm.optional(),
        })
        .optional(),
      ate_used: z.number().nullable().optional(),
      source: z.string().nullable().optional(),
      /** ATE 수집 단계 (설계서 v0.4 성분별 ATE 수집 순서) */
      step: z.int().nullable().optional(),
      /** 기여도 0~1 */
      share: z.number().min(0).max(1).nullable().optional(),
      flags: z.array(z.string()).optional(),
      /** 계산에서 뺀 이유 (예: 무독성, 한계농도 미만) */
      excluded: z.string().nullable().optional(),
    }),
  ),
  /** 계산값 (합계·ATEmix·미상 % 등). 계산마다 칸이 달라 자유 형식 */
  calc: z.record(z.string(), z.unknown()).nullable().optional(),
  thresholds: z.array(z.strictObject({ category: z.string(), range: z.string() })),
  /** 가정값과 결정 ID (예: id D-07, text M=1 가정). 설계서 v0.4 미결사항의 가정도 여기에 남긴다 */
  assumptions: z.array(z.strictObject({ id: z.string(), text: z.string() })),
  knowledge_version: z.string(),
  /** 사람이 읽는 계산 순서 (설계서 v0.4 설명 요청 예시의 trace 배열). 설명 요청에 그대로 들어간다 */
  steps: z.array(z.looseObject({ step: z.string() })),
});

/** findings 의 verdict 별 개수 */
export const summary = z.strictObject({
  일치: z.int().min(0),
  불일치: z.int().min(0),
  경계: z.int().min(0),
  근거부족: z.int().min(0),
  참고: z.int().min(0),
  "범위 외": z.int().min(0),
});

export const msdsResult = z.strictObject({
  msds_index: c.msdsIndex,
  /** meta.last_revision_date, 없으면 first_issue_date (설계서 v0.4 입력 데이터 매핑) */
  msds_revision_date: c.date.nullable(),
  product_type: z.strictObject({ value: z.enum(["단일물질", "혼합물", "불명확"]), basis: z.string() }),
  summary,
  /** finding.id 오름차순으로 정렬 (같은 입력이면 같은 순서) */
  findings: z.array(finding),
  /** trace_id → trace */
  traces: z.record(traceId, trace),
  /** 제약사항·검토 필요 문장 (설계서 v0.4 구성성분별 판단 요약의 제약사항). 근거부족·경계·가정 사유를 모은다 */
  limitations: z.array(z.strictObject({ finding_id: c.findingId.nullable(), text: z.string() })),
});

/** judge(extraction, as_of, provider) -> 이 JSON. 상태가 없고 DB에 쓰지 않는다 */
export const consistency = z.strictObject({
  contract: z.literal("consistency/1"),
  /** extraction.doc.doc_id 그대로 */
  doc_id: z.string(),
  as_of: c.date,
  engine_version: z.string().regex(/^\d+\.\d+\.\d+$/),
  knowledge: c.knowledge,
  results: z.array(msdsResult).min(1),
});

export type Consistency = z.infer<typeof consistency>;
export type MsdsResult = z.infer<typeof msdsResult>;
export type Finding = z.infer<typeof finding>;
export type Trace = z.infer<typeof trace>;
export type Side = z.infer<typeof msdsSide>;
