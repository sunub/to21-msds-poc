/*
 * 계약 common.schema.json 의 공용 정의를 zod 로 옮긴 것 (contracts/common.schema.json).
 * 계약과 한 글자도 다르지 않게 옮긴다. 계약에 없는 필드는 만들지 않는다.
 * 계약 상태: 승인 전 (contracts/README.md 맨 위). 계약을 바꾸면 이 파일도 같이 바꾼다.
 *
 * extraction_v06(추출스키마 v0.6 문서 전체)은 화면이 쓰지 않아 옮기지 않았다.
 * Q 는 계약이 TO21 추출스키마 v0.6 의 $defs/Q 를 $ref 하므로, 그 정의(to21/v0.6, D-47 파일은 저장소에 올리지 않음)의 모양만 옮겼다.
 */
import { z } from "zod";

/** 작업 번호. A가 업로드 때 만든다. 지금 service/store.py의 U-<날짜>-<순번> */
export const jobId = z.string().regex(/^U-\d{8}-\d{3,}$/);

/** 한 PDF 안의 MSDS 순번 (추출스키마 msds[] 의 자리, 0부터) */
export const msdsIndex = z.int().min(0);

/** msds 한 건 기준 칸 경로. 추출스키마 evidence[].field 와 같은 표기. 예: components[0].content */
export const fieldPath = z.string().min(1);

export const date = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);

/** ISO 8601, +09:00 (추출스키마 doc.extraction.extracted_at 과 같은 표기) */
export const datetime = z.iso.datetime({ offset: true });

export const sha256 = z.string().regex(/^[0-9a-f]{64}$/);

/** 검토자 이름. 화면이 브라우저에 둔 이름을 그대로 보낸다 (frontend/src/lib/reviewer.ts, 인증 없음) */
export const reviewer = z.string().min(1).max(50);

/** 추출스키마 doc.text_layer 와 같은 값 */
export const textLayer = z.enum(["정상", "글꼴깨짐", "없음", "혼합"]).nullable();

/** TO21 수치 객체 (추출스키마 v0.6 $defs/Q) */
export const Q = z.strictObject({
  raw: z.string().nullable(),
  approx: z.boolean().nullable().optional(),
  value: z.number().nullable().optional(),
  lower_op: z.enum([">", ">="]).nullable().optional(),
  lower: z.number().nullable().optional(),
  upper_op: z.enum(["<", "<="]).nullable().optional(),
  upper: z.number().nullable().optional(),
  unit: z.string().nullable().optional(),
  dp: z.int().nullable().optional(),
  status: z.enum(["값있음", "자료없음", "해당없음", "미기재", "판독불가", "마스킹"]).nullable(),
  note: z.string().nullable().optional(),
});

/** 추출스키마 v0.6 hazard.classes[].class_code 와 같은 코드 */
export const classCode = z.enum([
  "PH_EXPLOSIVE", "PH_FLAM_GAS", "PH_AEROSOL", "PH_OXID_GAS", "PH_PRESS_GAS", "PH_FLAM_LIQ", "PH_FLAM_SOL",
  "PH_SELF_REACT", "PH_PYRO_LIQ", "PH_PYRO_SOL", "PH_SELF_HEAT", "PH_WATER_REACT", "PH_OXID_LIQ", "PH_OXID_SOL",
  "PH_ORG_PEROX", "PH_METAL_CORR", "PH_DESENS_EXPL", "HH_ACUTE_ORAL", "HH_ACUTE_DERMAL", "HH_ACUTE_INHAL",
  "HH_SKIN_CORR", "HH_EYE_DMG", "HH_RESP_SENS", "HH_SKIN_SENS", "HH_MUTAGEN", "HH_CARCINOGEN", "HH_REPRO",
  "HH_STOT_SE", "HH_STOT_RE", "HH_ASPIRATION", "ENV_AQ_ACUTE", "ENV_AQ_CHRONIC", "ENV_OZONE", "ETC_UNMAPPED",
]);

/** 추출스키마 v0.6 hazard.classes[].route_form */
export const routeForm = z.enum(["가스", "증기", "분진·미스트"]).nullable();

/** 추출스키마 v0.6 regulations[].law. 판정 대상은 INTL(해외) 제외 */
export const law = z.enum(["OSH", "KREACH", "CCA", "DG", "WASTE", "POPS", "KR_ETC", "INTL"]);

/** 추출스키마 v0.6 regulations[].applicable 값 + 엔진의 경계 */
export const applicable = z.enum(["해당", "비해당", "자료없음", "미기재", "경계"]);

/** 판정 항목 ID. 판정 버전이 바뀌어도 같은 항목이면 같다. 판정 검토 이력을 잇는 키. 규칙은 contracts/README.md 3절 */
export const findingId = z.string().regex(/^m\d+\/(F2|F2L|F15|F15DG|FPT):[^\s]+$/);

/** 판정. 앞의 4가지가 설계서 v0.4 판정 체계. 참고(D-18 구분5 등)와 범위 외(검증 범위 밖 항목)는 화면 표시용 */
export const verdict = z.enum(["일치", "불일치", "경계", "근거부족", "참고", "범위 외"]);

/** 불일치 유형 (설계서 v0.4 판정 체계와 심각도) */
export const mismatchType = z
  .enum(["과소분류", "규제 누락", "형태·세부 표기", "기준 불일치", "구버전", "표시 요소 불일치", "과대분류", "과기재"])
  .nullable();

export const severity = z.enum(["높음", "중간", "낮음"]).nullable();

/** 차이 원인 코드 (설계서 v0.4 trace 반환 규격, 엔진이 붙임) */
export const causeCode = z.enum([
  "CAT_LOWER", "CAT_HIGHER", "MAIN_COMPONENT", "FORM_DIFF", "RANGE_EDGE", "ATE_VALUE_DIFF", "SOURCE_DIFF", "ASSUMED",
]);

/** 어떤 지식·규칙으로 판정했나 (설계서 v0.4 지식 교체와 버전 관리 기록 필드) */
export const knowledge = z.strictObject({
  /** 지식 제공자. reference(HTODB) | to21(API) */
  provider: z.enum(["reference", "to21"]),
  /** 지식 버전. HTODB 적재 차수 등. 예: ref-2026.10 */
  version: z.string().min(1),
  /** 규칙표 버전. 예: r0.3 */
  rules: z.string().min(1),
  /** 분류 로직 id (ghsclass ClassificationLogic.id). 예: to21_v6@6 */
  logic: z.string().min(1),
});

/** 원문 근거 한 줄. 추출스키마 v0.6 msds[].evidence[] 에서 가져온다 */
export const evidenceRef = z.strictObject({
  field: fieldPath,
  page: z.int().min(1).nullable(),
  source_text: z.string().nullable().optional(),
});
