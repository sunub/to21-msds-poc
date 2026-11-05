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
  /** regulation: 규제 시행일 (화면 2.4 '시행 2025-01-01'). 구버전 판정은 설계서 v0.4 D-09가 PoC 제외라 PoC에서는 null 이 기본 (contracts/6-screens.md 미결 1) */
  effective_from: c.date.nullable().optional(),
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
  /** 항목 이름 (화면 표의 '유해성 항목'·'규제 항목'). 예: 급성 독성 (흡입), 유독물질. B1이 규칙표 class_map·reg_map 에서 붙인다 */
  label: z.string().min(1),
  /** 판정 방법 (화면 2.3 '판정 방법' 열). 예: ATEmix 계산, 기준 분류 비교, 9항 시험값, M-factor 가산, 별표2 매핑, 규제DB 대조, 인화점 판정 */
  method: z.string().min(1),
  out_of_scope_reason: c.outOfScopeReason,
  /** 15항이면 법령 표시 이름, 2항이면 null */
  law_label: c.lawLabel.nullable(),
  /** 엔진이 적은 판정 이유 원문. 화면 '판정 근거'의 첫 줄 */
  reason: z.string(),
});

/**
 * 판정 근거 (설계서 v0.4 trace 반환 규격). 계산이 없는 판정(단순 조회·비교)은 steps 만 채운다.
 * 계산 종류마다 칸이 달라 inputs·thresholds 의 칸을 강제하지 않는다 (additionalProperties: true)
 */
export const trace = z.looseObject({
  kind: z.enum(["mixture_calc", "reference_lookup", "regulation_check", "label_check", "dg_check", "product_type"]),
  class_code: c.classCode.nullable().optional(),
  form: c.routeForm.optional(),
  result: z
    .looseObject({
      low: z.unknown(),
      high: z.unknown(),
      status: z.enum(["확정", "경계", "근거부족"]),
    })
    .optional(),
  rule: z.strictObject({
    id: z.string(),
    /** 예: 고시 별표1 */
    basis: z.string(),
    formula: z.string().nullable().optional(),
  }),
  inputs: z.array(z.record(z.string(), z.unknown())),
  /** 계산값 (합계·ATEmix·미상 % 등). 계산마다 칸이 달라 자유 형식 */
  calc: z.record(z.string(), z.unknown()).nullable().optional(),
  thresholds: z.array(z.record(z.string(), z.unknown())),
  /** 가정값과 결정 ID (예: id D-07, text M=1 가정). 설계서 v0.4 미결사항의 가정도 여기에 남긴다 */
  assumptions: z.array(z.strictObject({ id: z.string(), text: z.string() })),
  knowledge_version: z.string(),
  /** 사람이 읽는 계산 순서 (설계서 v0.4 설명 요청 예시의 trace 배열). 설명 요청에 그대로 들어간다 */
  steps: z.array(z.looseObject({ step: z.string() })),
  /** 원인 코드별 문장 (설명 요청에 그대로 들어간다) */
  cause_texts: z.array(z.strictObject({ code: c.causeCode, text: z.string() })).optional(),
  /** 화면 '판단 근거' 줄의 재료 */
  basis_lines: z.array(z.string()).optional(),
  /** 화면 '계산 과정' 줄의 재료 */
  calc_lines: z.array(z.string()).optional(),
});

/** findings 의 verdict 별 개수 */
export const summary = z.strictObject({
  일치: z.int().min(0),
  불일치: z.int().min(0),
  경계: z.int().min(0),
  근거부족: z.int().min(0),
  참고: z.int().min(0),
  "범위 외": z.int().min(0),
  경고: z.int().min(0),
});

/** 성분별 판단 요약 (설계서 v0.4 화면 예시 ④, 화면 '성분별 요약' 탭). 단일물질이면 한 줄 */
export const componentSummary = z.strictObject({
  comp_ref: z.string(),
  name: z.string().nullable(),
  cas: z.string().nullable(),
  /** 함량 (TO21 Q) */
  content: c.Q.nullable(),
  /** 기준 분류 (출처별). 예: 피부1 (KR02 환경부) */
  reference_classes: z.array(
    z.strictObject({ class_code: c.classCode, category: z.string(), route_form: c.routeForm, source: z.string() }),
  ),
  /** 사용 ATE (경로별, 몇 단계에서 가져왔는지). 제외면 excluded */
  ate: z.array(
    z.strictObject({
      route: z.enum(["oral", "dermal", "inhal"]),
      value: z.number().nullable(),
      unit: z.string().nullable(),
      form: c.routeForm,
      source: z.string().nullable(),
      step: z.int().nullable(),
      excluded: z.string().nullable(),
    }),
  ),
  /** 15항 해당 판정 수 */
  regulation_hits: z.int().min(0),
  /** 자료 신뢰도 (화면 ④ 자료 열) */
  reliability: z.enum(["높음", "보통", "낮음"]),
  /** 성분 상세에 보일 ATE 수집 순서·가정 문장 */
  notes: z.array(z.string()),
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
  /** 성분별 판단 요약 (설계서 v0.4 화면 예시 ④, 화면 성분별 요약 탭). 단일물질이면 한 줄 */
  components: z.array(componentSummary),
});

/** judge(extraction, as_of, provider) -> 이 JSON. 상태가 없고 DB에 쓰지 않는다 */
export const consistency = z.strictObject({
  contract: z.literal("consistency/2"),
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
export type ConsistencyComponent = z.infer<typeof componentSummary>;
