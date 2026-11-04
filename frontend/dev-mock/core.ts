/*
 * 판정 API(계약 5-api, consistency/2)를 서버 대신 흉내 내는 모듈 (개발용): 25번 황산 KZ-A-S004.
 * 두 곳이 같은 코드를 쓴다 (같은 내용을 두 번 쓰지 않는다).
 *   - 브라우저의 데모 문서: judgments.ts 가 이 모듈의 demo* 함수를 부른다 (상태는 sessionStorage)
 *   - 임시 서버(dev-mock/judgment-server.mjs): 같은 핵심 함수를 부른다 (상태는 서버 메모리)
 * 값은 계약 모양이다: label·method·law_label·reason·display·components 는 서버가 주는 값이라 이 모듈이 만들어 낸다
 * (backend judge/display.py 의 표기 규칙을 따른다). 화면은 그 값을 그대로 쓴다.
 *
 * 데모 문서 (job_id 는 계약상 U-날짜-순번 이지만 개발용으로 demo 계열 이름도 받는다)
 *   demo            기본 (혼합물, 처리 전)
 *   demo-states     새 상태: 설명 작성 중 1건(8초 뒤 완료), 판정이 바뀐(stale) 검토 1건, 더 새 넘김 기록(pending_handoff)
 *   demo-conflict   읽어 간 판정(버전 1)이 낡는다: 첫 검토·저장 요청은 409, 다시 읽으면 버전 2
 *   demo-savefail   저장이 500 으로 실패한다
 *   demo-pdffail    PDF 리포트가 422(글이 빠진 PDF)로 거절된다
 *   demo-single     단일물질(수소) / demo-unknown  단일·혼합을 판별하지 못함
 *   demo-none       아직 판정이 없다: status 는 판정 없음, 판정·저장 개요는 404 (넘김을 보내면 3초 뒤 첫 판정)
 * 상태가 바뀌는 일(판정 중 → 판정 있음, 설명 작성 중 → 완료)은 시각으로 정한다: 모든 호출이 먼저 tick() 으로 지금 상태를 맞춘다.
 */
import type {
  ExplanationEntry,
  FindingDisplay,
  HistoryEntry,
  JudgmentBatchItem,
  JudgmentStatus,
  JudgmentView,
  ReportRequest,
  ReviewEvent,
  ReviewEventRequest,
  ReviewState,
  SaveOverview,
  SaveRequest,
  Snapshot,
  VersionListItem,
} from "./contract/api";
import type { Consistency, ConsistencyComponent, Finding, MsdsResult, Trace } from "./contract/consistency";

export type DemoVariant = "single" | "unknown" | undefined;

const JOB = "U-20261102-025";
const COMP_H2SO4 = { comp_ref: "1", cas: "7664-93-9", name: "황산" };
const COMP_H2 = { comp_ref: "1", cas: "1333-74-0", name: "수소" };
const KNOWLEDGE = { provider: "reference", version: "ref-2026.10", rules: "r0.3", logic: "to21_v6@6" } as const;

type Ev = { field: string; page: number | null; source_text?: string | null };

const q = (raw: string, lower: number, unit = "%") => ({ raw, lower, lower_op: ">=" as const, unit, status: "값있음" as const });
const range = (lo: number, hi: number) => ({
  raw: `${lo}~${hi}`,
  lower: lo,
  lower_op: ">=" as const,
  upper: hi,
  upper_op: "<=" as const,
  unit: "%",
  status: "값있음" as const,
});

/** 판정 엔진이 주는 trace 중 이 데모가 채우는 칸 (나머지는 build 가 채운다) */
type SpecTrace = {
  kind: Trace["kind"];
  rule: Trace["rule"];
  steps: { step: string }[];
  class_code?: string | null;
  form?: Trace["form"];
  result?: Trace["result"];
  inputs?: Record<string, unknown>[];
  calc?: Record<string, unknown>;
  thresholds?: Record<string, unknown>[];
  assumptions?: { id: string; text: string }[];
  basis_lines?: string[];
  calc_lines?: string[];
};

type Spec = {
  id: string;
  section: "2" | "15";
  kind: Finding["kind"];
  item: string;
  comp: Finding["comp"];
  msds: Finding["msds"];
  expected: Finding["expected"];
  verdict: Finding["verdict"];
  type?: Finding["type"];
  severity?: Finding["severity"];
  rule?: string | null;
  causes?: Finding["causes"];
  trace?: SpecTrace;
  explain?: string;
  /** 엔진이 적은 판정 이유 (없으면 계산 과정의 마지막 줄) */
  reason?: string;
  /** 범위 외 판정의 이유 */
  outOfScope?: "해당 없음" | "대조만";
};

const cls = (code: string, id: string, comp: Finding["comp"], msds: Partial<Finding["msds"]>, expected: Partial<Finding["expected"]>, rest: Partial<Spec> = {}): Spec => ({
  id: `m0/F2:${code}:${id}`,
  section: "2",
  kind: "class",
  item: code,
  comp,
  msds: { present: true, ...msds },
  expected: { present: true, status: "확정", ...expected },
  verdict: "일치",
  ...rest,
});

const reg = (law: string, code: string, comp: Finding["comp"], msdsApp: Finding["msds"], expApp: Finding["expected"], rest: Partial<Spec> = {}): Spec => ({
  id: `m0/F15:${comp?.cas ?? "MIX"}:${law}.${code}`,
  section: "15",
  kind: "regulation",
  item: `${law}.${code}`,
  comp,
  msds: msdsApp,
  expected: expApp,
  verdict: "일치",
  ...rest,
});

const ev12: Ev[] = [{ field: "regulations[0]", page: 12 }];
const regPair = (threshold: ReturnType<typeof q> | null, label: Ev[] = ev12) => ({
  msds: { present: true, applicable: "해당" as const, threshold, content: range(93, 98), evidence: label },
  // 기준 쪽 기준 농도는 엔진이 정리한 표기(>= 10%), MSDS 쪽은 원문 표기(10% 이상)다 (backend judge/display.py 의 예: 해당 (10% 이상) / 해당 (≥ 10%))
  expected: {
    present: true, applicable: "해당" as const, threshold: threshold ? { ...threshold, raw: `>= ${threshold.lower}%` } : null,
    content: range(93, 98), status: "확정" as const, source: "규제DB",
  },
});

function mixtureSpecs(): Spec[] {
  const matchTrace = (rule: string, basis: string, kind: Trace["kind"], step: string): Spec["trace"] => ({ kind, rule: { id: rule, basis }, steps: [{ step }] });
  const R = (code: string, th: ReturnType<typeof q> | null, step: string, extra: Partial<Spec> = {}): Spec => {
    const [law, item] = code.split(".");
    const p = regPair(th);
    return reg(law, item, COMP_H2SO4, p.msds, p.expected, { rule: "REG-DB-LOOKUP", trace: matchTrace("REG-DB-LOOKUP", "규제DB 조회 (as_of 기준)", "regulation_check", step), ...extra });
  };
  return [
    cls("HH_ACUTE_INHAL", "분진·미스트", null,
      { category: "2", route_form: "증기", evidence: [{ field: "hazard.classes[3]", page: 4, source_text: "급성 독성(흡입: 증기) : 구분 2" }] },
      { category: "2", route_form: "분진·미스트", source: "MSDS 11항", evidence: [{ field: "toxicity.acute[0]", page: 9 }] },
      {
        verdict: "불일치", type: "형태·세부 표기", severity: "중간", rule: "ATE-INHAL-MIST", causes: ["FORM_DIFF"], reason: "구분은 같고 형태만 다름",
        explain: "주성분 황산의 흡입 독성값은 미스트(LC50 0.375 mg/L)입니다. 계산한 ATEmix 0.383~0.403 mg/L는 미스트 구분2 범위인데, MSDS 2항은 \"증기\" 구분2로 적었습니다. 11항도 증기 범위로 기재했습니다.",
        trace: {
          kind: "mixture_calc", class_code: "HH_ACUTE_INHAL", form: "분진·미스트", result: { low: "2", high: "2", status: "확정" },
          rule: { id: "ATE-INHAL-MIST", basis: "ATEmix 계산" },
          inputs: [
            { cas: "7664-93-9", name: "황산", content: { low: 93, high: 98 }, value: { type: "LC50", op: "=", v: 0.375, unit: "mg/L", hours: 4, form: "분진·미스트" }, ate_used: 0.375, source: "MSDS 11항", step: 3, excluded: null },
            { cas: "7732-18-5", name: "물", content: { low: 2, high: 7 }, ate_used: null, source: null, step: 5, excluded: "무독성 제외" },
          ],
          calc: { atemix_low: 0.383, atemix_high: 0.403 },
          thresholds: [{ category: "구분2", range: "0.05 < ATEmix ≤ 0.5" }],
          steps: [
            { step: "황산 93~98% · 0.375 mg/L (미스트) · 11항 3단계" },
            { step: "물 2~7% · 무독성 제외 · 5단계" },
            { step: "상한 98%: 100 / (98 / 0.375) = 0.383" },
            { step: "하한 93%: 100 / (93 / 0.375) = 0.403" },
            { step: "→ 분진·미스트 구분2 (확정)" },
          ],
        },
      }),
    cls("PH_METAL_CORR", "-", null,
      { category: "1", evidence: [{ field: "hazard.classes[6]", page: 4 }] },
      { present: false, low: null, high: null, status: "근거부족" },
      {
        verdict: "근거부족", rule: "METAL-CORR-TEST", reason: "혼합물 시험자료가 없음",
        explain: "혼합물 시험자료가 없어 판정할 수 없습니다. 판정을 빼지 않고 근거부족으로 표시해 검토자에게 넘깁니다.",
        trace: { kind: "reference_lookup", rule: { id: "METAL-CORR-TEST", basis: "9항 시험값" }, steps: [{ step: "9항 시험값: 제품 시험자료 없음" }] },
      }),
    cls("ENV_AQ_CHRONIC", "-", null,
      { category: "3", evidence: [{ field: "hazard.classes[7]", page: 4 }] },
      { present: false, low: null, high: null, status: "근거부족" },
      {
        verdict: "근거부족", rule: "AQUATIC-CHRONIC-SUM", reason: "기준정보에 수생 분류가 없음",
        explain: "황산과 물 모두 기준정보에 수생 분류가 없어, MSDS 구분3의 근거를 확인해야 합니다.",
        trace: { kind: "reference_lookup", rule: { id: "AQUATIC-CHRONIC-SUM", basis: "M-factor 가산" }, steps: [{ step: "황산: 기준정보에 수생 분류 없음" }, { step: "물: 기준정보에 수생 분류 없음" }] },
      }),
    {
      id: "m0/F2L:H:H318", section: "2", kind: "label", item: "H318", comp: null,
      msds: { present: true, code: "H318", evidence: [{ field: "hazard.h_statements[1]", page: 4 }] },
      expected: { present: false, code: null, status: "확정" },
      verdict: "경고", type: "표시 요소 불일치", severity: "낮음", rule: "LABEL-H-DUP", reason: "H314와 중복 (피부 부식성 구분1이면 H318은 함께 적지 않음)",
      explain: "피부 부식성 구분1이면 H314가 나오고, 이때 눈 손상 H318은 함께 적지 않습니다. MSDS는 둘 다 적어 중복입니다.",
      trace: { kind: "label_check", rule: { id: "LABEL-H-DUP", basis: "별표2 매핑" }, steps: [{ step: "피부 부식성/자극성 구분1 → H314" }, { step: "심한 눈 손상성/자극성 구분1 → H318" }, { step: "MSDS 2항: H314, H318 모두 기재" }] },
    },
    cls("HH_ACUTE_ORAL", "-", null, { present: false }, { present: false }, {
      rule: "ATE-ORAL",
      trace: {
        kind: "mixture_calc", class_code: "HH_ACUTE_ORAL", rule: { id: "ATE-ORAL", basis: "ATEmix 계산" },
        inputs: [{ cas: "7664-93-9", name: "황산", ate_used: null, source: "MSDS 11항", step: null, excluded: "11항" }],
        steps: [{ step: "MSDS 2항: 미기재" }, { step: "기준: 분류안됨" }],
      },
    }),
    cls("HH_REPRO", "-", null, { present: false }, { present: false }, { verdict: "범위 외", outOfScope: "해당 없음", reason: "혼합물 시험자료가 없어 이 항목은 판정 범위에서 뺌" }),
    cls("HH_ACUTE_DERMAL", "-", null, { present: true, category: "5" }, { present: false }, { verdict: "범위 외", outOfScope: "대조만", reason: "구분5는 대조만 함" }),
    cls("HH_SKIN_CORR", "-", COMP_H2SO4, { category: "1" }, { category: "1", source: "TO21 분류기준" }, { rule: "SKIN-CORR-SUM", trace: matchTrace("SKIN-CORR-SUM", "가산 (Σ구분1 ≥ 5%)", "reference_lookup", "MSDS 2항: 구분1 / 기준: 구분1") }),
    cls("HH_EYE_DMG", "-", COMP_H2SO4, { category: "1" }, { category: "1", source: "TO21 분류기준" }, { rule: "EYE-DAMAGE-SUM", trace: matchTrace("EYE-DAMAGE-SUM", "가산 (≥ 3%)", "reference_lookup", "MSDS 2항: 구분1 / 기준: 구분1") }),
    cls("HH_CARCINOGEN", "-", COMP_H2SO4, { category: "1A" }, { category: "1A", source: "TO21 분류기준" }, { rule: "CARC-LIMIT", trace: matchTrace("CARC-LIMIT", "한계농도 0.1%", "reference_lookup", "MSDS 2항: 구분1A / 기준: 구분1A") }),
    cls("HH_STOT_SE", "-", COMP_H2SO4, { category: "1" }, { category: "1", source: "TO21 분류기준" }, { rule: "STOT-SE-LIMIT", trace: matchTrace("STOT-SE-LIMIT", "한계농도 10%", "reference_lookup", "MSDS 2항: 구분1 / 기준: 구분1") }),

    R("CCA.CCA_TOXIC", q("10% 이상", 10), "황산 93~98% ≥ 10% → 해당", {
      verdict: "불일치", type: "구버전", severity: "중간",
      explain: "화관법 유독물질 고시가 2025-01-01에 개정되어 세분 표기가 필요합니다. MSDS 15항은 개정 전 표기로, 구버전 기준 판정입니다.",
      trace: {
        kind: "regulation_check", rule: { id: "REG-DB-LOOKUP", basis: "규제DB 조회 (as_of 기준)" },
        steps: [{ step: "황산 93~98% ≥ 10% → 해당" }, { step: "규제DB 개정 시행일: 2025-01-01" }, { step: "→ 구버전 (개정 전 표기 기준 판정)" }],
      },
    }),
    R("OSH.OSH_MEASURE", q("1% 이상", 1), "황산 93~98% ≥ 1% → 해당"),
    R("OSH.OSH_HEALTH_EXAM", q("1% 이상", 1), "황산 93~98% ≥ 1% → 해당"),
    R("OSH.OSH_PSM", q("20% 이상", 20), "황산 93~98% ≥ 20% → 해당"),
    R("OSH.OSH_PERMISSIBLE", null, "황산: 허용기준 설정물질 → 해당"),
    R("CCA.CCA_ACCIDENT", q("10% 이상", 10), "황산 93~98% ≥ 10% → 해당"),
    R("CCA.CCA_EMISSION", q("1% 이상", 1), "황산 93~98% ≥ 1% → 해당"),
    R("KREACH.KREACH_REG_EXIST", null, "황산: 등록대상기존화학물질 → 해당"),
    {
      id: "m0/F15DG:MIX", section: "15", kind: "dangerous_goods", item: "DG", comp: null,
      msds: { present: true, dg: { class: null, item: null, water_soluble: null, grade: null }, evidence: ev12 },
      expected: { present: true, dg: { class: null, item: null, water_soluble: null, grade: null }, status: "확정" },
      verdict: "일치", rule: "REG-DB-LOOKUP",
      trace: matchTrace("REG-DB-LOOKUP", "규제DB 조회 (as_of 기준)", "dg_check", "제품: 인화점 없음 → 비해당"),
    },
    {
      id: "m0/FPT:TYPE", section: "2", kind: "product_type", item: "TYPE", comp: null,
      msds: { present: true, product_type: "혼합물" },
      expected: { present: true, product_type: "혼합물", status: "확정" },
      verdict: "일치", rule: null,
    },
  ];
}

function singleSpecs(): Spec[] {
  const src = "KR02 환경부, KR03 고용노동부";
  const regH2 = (item: string, th: ReturnType<typeof q> | null): Spec =>
    reg("OSH", item, COMP_H2, { present: true, applicable: "해당", threshold: th, content: q("99.99 이상", 99.99), evidence: ev12 }, { present: true, applicable: "해당", threshold: th ? { ...th, raw: `>= ${th.lower}%` } : null, status: "확정" }, { rule: "REG-DB-LOOKUP", trace: { kind: "regulation_check", rule: { id: "REG-DB-LOOKUP", basis: "규제DB 조회 (as_of 기준)" }, steps: [{ step: "수소: 해당" }] } });
  return [
    cls("PH_FLAM_GAS", "-", COMP_H2, { category: "1", evidence: [{ field: "hazard.classes[0]", page: 4 }] }, { category: "1", source: src }),
    cls("PH_PRESS_GAS", "-", COMP_H2, { category: null }, { category: null, source: src }),
    regH2("OSH_MEASURE", q("1% 이상", 1)),
    regH2("OSH_HEALTH_EXAM", q("1% 이상", 1)),
    {
      id: "m0/F15DG:1333-74-0", section: "15", kind: "dangerous_goods", item: "DG", comp: COMP_H2,
      msds: { present: true, dg: { class: "가스", item: "수소", water_soluble: null, grade: null }, evidence: ev12 },
      expected: { present: true, dg: { class: "가스", item: "수소", water_soluble: null, grade: null }, status: "확정" },
      verdict: "일치", rule: "REG-DB-LOOKUP",
      trace: { kind: "dg_check", rule: { id: "REG-DB-LOOKUP", basis: "규제DB 조회 (as_of 기준)" }, steps: [{ step: "수소: 위험물" }] },
    },
    {
      id: "m0/FPT:TYPE", section: "2", kind: "product_type", item: "TYPE", comp: null,
      msds: { present: true, product_type: "단일물질" }, expected: { present: true, product_type: "단일물질", status: "확정" },
      verdict: "일치", rule: null,
    },
  ];
}

/** "작성 중" 설명을 보여 주는 데모 항목 (demo-states) */
const WRITING_ID = "m0/F2:HH_SKIN_SENS:-";
const writingSpec = (): Spec =>
  cls("HH_SKIN_SENS", "-", null, { category: "1" }, { category: "1", low: "1", high: "1B", status: "경계" }, {
    verdict: "경계", rule: "SENS-RANGE", causes: ["RANGE_EDGE"],
    trace: { kind: "mixture_calc", class_code: "HH_SKIN_SENS", rule: { id: "SENS-RANGE", basis: "함량 범위 계산" }, steps: [{ step: "함량 범위 93~98%에서 구분이 1과 1B로 갈림" }] },
  });

/** 판정이 바뀐(stale) 검토를 보여 주는 데모 항목 (demo-states): 이미 확정했는데 판정 값이 바뀜 */
const STALE_ID = "m0/F2:PH_METAL_CORR:-";

/* ── 서버가 붙이는 값: label · method · law_label · reason · display · components ──────────
 * 실제 서버에서는 B1(판정 엔진)과 judge/display.py 가 만드는 값이다. 화면은 이 값을 그대로 쓴다. */

const CLASS_LABEL: Record<string, string> = {
  HH_ACUTE_ORAL: "급성독성물질(경구)",
  HH_ACUTE_DERMAL: "급성독성물질(경피)",
  HH_ACUTE_INHAL: "급성독성물질(흡입)",
  HH_SKIN_CORR: "피부 부식성/자극성",
  HH_EYE_DMG: "심한 눈 손상성/자극성",
  HH_SKIN_SENS: "피부 과민성",
  HH_REPRO: "생식독성",
  HH_CARCINOGEN: "발암성",
  HH_STOT_SE: "특정표적장기 독성(1회 노출)",
  ENV_AQ_CHRONIC: "수생환경 유해성(만성)",
  PH_METAL_CORR: "금속부식성 물질",
  PH_FLAM_GAS: "인화성 가스",
  PH_PRESS_GAS: "고압가스",
};
const REG_LABEL: Record<string, string> = {
  OSH_MEASURE: "작업환경측정 대상물질",
  OSH_HEALTH_EXAM: "특수건강진단 대상물질",
  OSH_PSM: "공정안전보고서 제출 대상",
  OSH_PERMISSIBLE: "허용기준 설정물질",
  CCA_TOXIC: "유독물질",
  CCA_ACCIDENT: "사고대비물질",
  CCA_EMISSION: "배출량조사 대상",
  KREACH_REG_EXIST: "등록대상기존화학물질",
};
const LAW_LABEL: Record<string, NonNullable<Finding["law_label"]>> = { OSH: "산안법", CCA: "화관법", KREACH: "화평법", DG: "위험물법" };

const labelOf = (s: Spec) =>
  s.kind === "class"
    ? (CLASS_LABEL[s.item] ?? s.item)
    : s.kind === "label"
      ? `표시 요소 ${s.item}`
      : s.kind === "regulation"
        ? (REG_LABEL[s.item.split(".")[1]] ?? s.item)
        : s.kind === "dangerous_goods"
          ? "위험물"
          : "단일·혼합 판별";

const catText = (category: string | null | undefined) => (category == null || category === "" ? "기재 없음" : /^\d/.test(category) ? `구분 ${category}` : category);
const withForm = (text: string, form: string | null | undefined) => (form ? `${text} (${form})` : text);
const applicableText = (value: string | null | undefined, threshold: { raw?: string | null } | null | undefined) => {
  if (!value) return "기재 없음";
  const raw = threshold?.raw;
  return raw ? `${value} (${raw.replace(">=", "≥").replace("<=", "≤")})` : value;
};

function classExpected(e: Finding["expected"]): string {
  if (e.low == null && e.category == null) {
    if (!("low" in e)) return "비교하지 않음";
    return e.status === "근거부족" ? "판단 못 함" : "없음";
  }
  if (e.low == null) return catText(e.category);
  return e.low === e.high ? catText(e.low) : `${catText(e.low)}~${catText(e.high)}`;
}

function textsOf(f: Finding): [string, string] {
  const { msds, expected: exp } = f;
  if (f.kind === "class") return [withForm(msds.present ? catText(msds.category) : "기재 없음", msds.route_form), withForm(classExpected(exp), exp.route_form)];
  if (f.kind === "label") return [msds.code ? `${msds.code} 기재` : "기재 없음", exp.code ?? "해당 없음"];
  if (f.kind === "product_type") return [msds.product_type ?? "기재 없음", exp.product_type ?? "판단 못 함"];
  let expected = applicableText(exp.applicable, exp.threshold);
  if (!exp.present) expected = f.verdict === "참고" || f.verdict === "범위 외" ? "비교하지 않음" : "기준 없음";
  if (f.kind === "dangerous_goods" && exp.dg?.item && exp.applicable) expected = `${exp.applicable} (${exp.dg.item})`;
  return [applicableText(msds.applicable, msds.threshold), expected];
}

const EVIDENCE_SECTION: Record<string, number> = { hazard: 2, components: 3, composition: 3, physchem: 9, toxicity: 11, ecotox: 12, transport: 14, regulations: 15, dangerous_goods: 15 };

function pagesOf(f: Finding) {
  const pages = new Map<string, { section: number; page: number }>();
  for (const e of f.msds.evidence ?? []) {
    const section = EVIDENCE_SECTION[e.field.split(/[.[]/)[0]];
    if (section && e.page) pages.set(`${section}:${e.page}`, { section, page: e.page });
  }
  // 판정한 항이 먼저 나와야 한다 (화면은 첫 번째를 기본으로 연다)
  return [...pages.values()].sort((a, b) => Number(String(a.section) !== f.section) - Number(String(b.section) !== f.section) || a.section - b.section || a.page - b.page);
}

function displayOf(f: Finding, trace: Trace | undefined): FindingDisplay {
  const [msds, expected] = textsOf(f);
  let component: string | null = null;
  if (f.section === "15") {
    const raw = String(f.expected.content?.raw ?? "").replace("%", "").trim();
    const name = f.comp?.name ?? f.comp?.cas ?? f.comp?.comp_ref;
    component = !f.comp ? "제품" : raw ? `${name} (${raw})` : String(name);
  }
  const basis = [...(trace?.basis_lines ?? [])];
  if (f.reason && !basis.includes(f.reason)) basis.unshift(f.reason);
  return { msds, expected, component, basis_lines: basis, calc_lines: [...(trace?.calc_lines ?? [])], source_pages: pagesOf(f) };
}

/** 성분별 판단 요약 (consistency.results[].components) */
function componentsOf(findings: Finding[], product: MsdsResult["product_type"]["value"]): ConsistencyComponent[] {
  if (product === "불명확") return [];
  const hits = (cas: string | null) => findings.filter((f) => f.kind === "regulation" && f.comp?.cas === cas && f.expected.applicable === "해당").length;
  const refs = (cas: string | null): ConsistencyComponent["reference_classes"] =>
    findings
      .filter((f) => f.kind === "class" && f.comp?.cas === cas && f.expected.category)
      .sort((a, b) => ["HH_SKIN_CORR", "HH_EYE_DMG", "HH_CARCINOGEN", "HH_STOT_SE"].indexOf(a.item) - ["HH_SKIN_CORR", "HH_EYE_DMG", "HH_CARCINOGEN", "HH_STOT_SE"].indexOf(b.item))
      .flatMap((f) =>
        (f.expected.source ?? "TO21 분류기준").split(",").map((source) => ({ class_code: f.item as ConsistencyComponent["reference_classes"][number]["class_code"], category: String(f.expected.category), route_form: null, source: source.trim() })),
      );
  if (product === "단일물질") {
    return [{ comp_ref: "1", name: "수소", cas: "1333-74-0", content: q("99.99 이상", 99.99), reference_classes: refs("1333-74-0"), ate: [], regulation_hits: hits("1333-74-0"), reliability: "높음", notes: [] }];
  }
  return [
    {
      comp_ref: "1", name: "황산", cas: "7664-93-9", content: range(93, 98), reference_classes: refs("7664-93-9"),
      ate: [
        { route: "oral", value: null, unit: null, form: null, source: "MSDS 11항", step: null, excluded: "11항" },
        { route: "inhal", value: 0.375, unit: "mg/L", form: "분진·미스트", source: "MSDS 11항", step: 3, excluded: null },
      ],
      regulation_hits: hits("7664-93-9"), reliability: "보통",
      notes: ["1단계 독성DB 수치: 없음", "2단계 분류 구분 → 환산값: 없음", "3단계 MSDS 11항 수치: 0.375 mg/L (분진·미스트, 4hr) 사용"],
    },
    {
      comp_ref: "2", name: "물", cas: "7732-18-5", content: range(2, 7), reference_classes: [],
      ate: [{ route: "inhal", value: null, unit: null, form: null, source: null, step: 5, excluded: "무독성" }],
      regulation_hits: 0, reliability: "높음", notes: ["5단계 무독성 성분: 계산에서 제외"],
    },
  ];
}

function build(specs: Spec[], opts: { productType: "단일물질" | "혼합물" | "불명확"; limitations: MsdsResult["limitations"] }): { consistency: Consistency; display: Record<string, FindingDisplay> } {
  const sorted = [...specs].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  const traces: MsdsResult["traces"] = {};
  let n = 0;
  const findings: Finding[] = sorted.map((s) => {
    const traceId = s.trace ? `T-${String(++n).padStart(4, "0")}` : null;
    if (s.trace && traceId) {
      const t = { thresholds: [], assumptions: [], inputs: [], knowledge_version: KNOWLEDGE.version, ...s.trace } as Trace;
      const calc = t.kind === "mixture_calc";
      t.basis_lines ??= calc ? ((t.thresholds as { category: string; range: string }[]).map((x) => `${x.category}: ${x.range}`)) : t.steps.map((x) => x.step);
      t.calc_lines ??= calc ? t.steps.map((x) => x.step) : [];
      traces[traceId] = t;
    }
    // 성분에 걸린 판정은 성분표 쪽(혼합물 3쪽, 단일물질 2쪽)을 근거로 단다 (성분별 요약 탭의 원문 이동용)
    const msds = s.comp ? { ...s.msds, evidence: [...(s.msds.evidence ?? []), { field: "components[0].name", page: opts.productType === "단일물질" ? 2 : 3 }] } : s.msds;
    const lastStep = s.trace?.steps[s.trace.steps.length - 1]?.step;
    return {
      id: s.id, section: s.section, kind: s.kind, item: s.item, comp: s.comp, msds, expected: s.expected,
      verdict: s.verdict, type: s.type ?? null, severity: s.severity ?? null, rule: s.rule ?? null, causes: s.causes ?? [],
      trace_id: traceId, needs_explanation: ["불일치", "경계", "근거부족"].includes(s.verdict),
      label: labelOf(s),
      method: s.trace?.rule.basis ?? (s.kind === "regulation" ? "규제DB 대조" : "기준 분류 비교"),
      out_of_scope_reason: s.outOfScope ?? null,
      law_label: s.section === "15" ? (LAW_LABEL[s.item.split(".")[0]] ?? (s.kind === "dangerous_goods" ? "위험물법" : "기타 국내")) : null,
      reason: s.reason ?? lastStep ?? "MSDS 기재와 검증 결과가 같음",
    };
  });
  const summary = { 일치: 0, 불일치: 0, 경계: 0, 근거부족: 0, 경고: 0, 참고: 0, "범위 외": 0 };
  for (const f of findings) summary[f.verdict] += 1;
  const display = Object.fromEntries(findings.map((f) => [f.id, displayOf(f, f.trace_id ? traces[f.trace_id] : undefined)]));
  return {
    consistency: {
      contract: "consistency/2", doc_id: "KZ-A-S004", as_of: "2026-11-02", engine_version: "0.1.0", knowledge: KNOWLEDGE,
      results: [{
        msds_index: 0, msds_revision_date: "2022-06-29",
        product_type: { value: opts.productType, basis: opts.productType === "불명확" ? "성분 정보를 읽지 못함" : "성분표 기준" },
        summary, findings, traces, limitations: opts.limitations, components: componentsOf(findings, opts.productType),
      }],
    },
    display,
  };
}

const template = (text: string): ExplanationEntry => ({ status: "완료", by: "template", checked: true, summary: text, reasons: [], basis: [] });

/** saved = 저장본이 있고 미검토·미검수 칸이 없어 등급이 골드, jfail = 판정이 실패함 (목록 시험용) */
export type Scenario = "plain" | "states" | "conflict" | "savefail" | "pdffail" | "single" | "unknown" | "none" | "saved" | "jfail";
/** 목록 시험용 고정 작업 번호 (docs.ts 의 목록과 짝) */
const FIXED: Record<string, Scenario> = { "U-20261103-001": "saved", "U-20261103-002": "none", "U-20261103-006": "jfail" };
export const scenarioOf = (job: string): Scenario =>
  FIXED[job] ? FIXED[job] : job.startsWith("demo-states") ? "states" : job.startsWith("demo-conflict") ? "conflict" : job.startsWith("demo-savefail") ? "savefail" : job.startsWith("demo-pdffail") ? "pdffail" : job.startsWith("demo-single") ? "single" : job.startsWith("demo-unknown") ? "unknown" : job.startsWith("demo-none") ? "none" : "plain";

/** 상황별 기본 판정 한 벌 (검토·버전은 아직 없다) */
function viewFor(scen: Scenario, variantArg: DemoVariant) {
  // 단일물질·판별 불가는 화면의 &product= 로도, demo-single·demo-unknown 문서 번호로도 고른다
  const variant: DemoVariant = variantArg ?? (scen === "single" ? "single" : scen === "unknown" ? "unknown" : undefined);
  const states = scen === "states";
  const single = variant === "single";
  const specs = single ? singleSpecs() : [...mixtureSpecs(), ...(states ? [writingSpec()] : [])];
  const explainText = new Map(specs.filter((s) => s.explain).map((s) => [s.id, s.explain as string]));
  const { consistency, display } = build(specs, {
    productType: single ? "단일물질" : variant === "unknown" ? "불명확" : "혼합물",
    limitations: single
      ? []
      : [
          { finding_id: "m0/F2:PH_METAL_CORR:-", text: "혼합물 시험자료가 없어 판정할 수 없습니다." },
          { finding_id: "m0/F2:ENV_AQ_CHRONIC:-", text: "황산·물 모두 기준정보에 수생 분류가 없습니다. MSDS 구분3의 근거를 확인해야 합니다." },
        ],
  });
  const explanations: Record<string, ExplanationEntry> = {};
  for (const f of consistency.results[0].findings) {
    if (f.needs_explanation) explanations[f.id] = f.id === WRITING_ID ? { status: "작성 중" } : template(explainText.get(f.id) ?? "");
  }
  return {
    consistency, display, explanations,
    judged_at: "2026-11-02T10:00:00+09:00",
    field_status: states ? ([{ msds_index: 0, field: "hazard.classes[3]", status: "확인함" }, { msds_index: 0, field: "toxicity.acute[0]", status: "수정됨" }] as JudgmentView["field_status"]) : [],
  };
}

/* ── 서버 상태 흉내 (검토·저장·넘김) ─────────────────────────────────────── */

export class FakeHttpError extends Error {
  constructor(
    readonly status: number,
    readonly body: unknown,
  ) {
    super(typeof body === "object" && body && "detail" in body && typeof body.detail === "string" ? body.detail : `HTTP ${status}`);
  }
}
const fail = (status: number, detail: unknown) => new FakeHttpError(status, { detail });

type StoredEvent = ReviewEvent & { sha: string };
export type Store = {
  scen: Scenario;
  latest: number;
  /** 가장 최근 넘김 번호 */
  handoff: number;
  /** 아직 판정하지 않은 넘김 번호 (판정 중) */
  pending: number | null;
  /** pending 이 끝나는 시각 (ms). null 이면 계속 판정 중 */
  judgeAt: number | null;
  startedAt: number;
  /** 버전 2 를 판정한 시각과 넘김 번호 */
  v2At: number | null;
  v2Handoff: number;
  armConflict: boolean;
  events: StoredEvent[];
  snapshots: Snapshot[];
  /** 판정이 실패했다면 서버가 상태에 싣는 이유 (jfail) */
  failed?: string;
};

const WRITING_MS = 8000;
const JUDGE_MS = 3000;
const FIELDS_TOTAL = 120;
const NEEDS_REVIEW = ["불일치", "경계", "근거부족", "경고"];
const JUDGED = ["일치", "불일치", "경계", "근거부족", "경고"];
/** 확인은 일치 쪽, 확정·승인은 일치가 아닌 쪽에만 쓴다 (5-api review_event_request). 의견·되돌리기는 어디든 된다 */
const ACTION_VERDICTS: Record<string, string[]> = { 확인: ["일치", "참고", "범위 외"], "불일치 확정": NEEDS_REVIEW, "예외 승인": NEEDS_REVIEW };
/** 버전 2 에서 바뀌는 판정: 금속부식성 근거부족 → 경계 (stale 시험용) */
const CHANGED_ID = "m0/F2:PH_METAL_CORR:-";

const kst = (ms: number) => `${new Date(ms + 9 * 3600_000).toISOString().slice(0, 19)}+09:00`;

export function newStore(job: string, now = Date.now()): Store {
  const scen = scenarioOf(job);
  const states = scen === "states";
  const jfail = scen === "jfail";
  const none = scen === "none" || jfail;
  const st: Store = {
    scen, latest: none ? 0 : 1, handoff: jfail ? 1 : none ? 0 : states ? 2 : 1, pending: states ? 2 : jfail ? 1 : null, judgeAt: null, startedAt: now, v2At: null, v2Handoff: 2,
    armConflict: scen === "conflict", events: [], snapshots: [],
  };
  if (jfail) st.failed = "판정 중 내부 오류 (KnowledgeUnavailable). 서버 기록을 확인하세요";
  if (scen === "saved") {
    // 이미 저장한 문서: 최신 저장본이 지금의 판정을 그대로 담고 미검토·미검수 칸이 없다 (등급 골드)
    st.snapshots.push({
      contract: "snapshot/1", job_id: job, snapshot_no: 2, handoff_seq: 1, version: 1, last_review_event_id: null,
      counts: { findings: 19, 미검토: 0, "불일치 확정": 0, "예외 승인": 0, 확인: 0, "미검수 칸": 0 },
      saved_by: "김검수", saved_at: "2026-11-03T09:10:00+09:00", note: null,
    });
  }
  if (states) {
    // 이미 확정했는데 그 뒤 판정 값이 바뀐 항목 (stale) 과 거기에 남긴 의견
    st.events.push(
      { event_id: 1, job_id: JOB, finding_id: STALE_ID, action: "불일치 확정", comment: "시험자료 확인 예정", reviewer: "김검수", at: "2026-11-02T10:30:00+09:00", version: 1, verdict_seen: "근거부족", sha: "이전 판정" },
      { event_id: 2, job_id: JOB, finding_id: STALE_ID, action: "의견", comment: "판정이 바뀌면 다시 보겠음", reviewer: "김검수", at: "2026-11-02T10:40:00+09:00", version: 1, verdict_seen: "근거부족", sha: "이전 판정" },
    );
  }
  return st;
}

/** 시각에 따라 바뀌는 상태를 지금에 맞춘다 */
function tick(st: Store, now: number) {
  if (st.pending !== null && st.judgeAt !== null && now >= st.judgeAt) {
    st.latest += 1;
    if (st.latest >= 2) {
      st.v2At = st.judgeAt;
      st.v2Handoff = st.pending;
    }
    st.pending = null;
    st.judgeAt = null;
    st.startedAt = 0; // 새 판정의 설명은 처음부터 완료
  }
}

const fingerprint = (f: Finding) => {
  const strip = (side: object) => Object.fromEntries(Object.entries(side).filter(([k]) => k !== "evidence"));
  return JSON.stringify([f.verdict, strip(f.msds), strip(f.expected)]);
};

/** 판정 한 벌 (버전별). 검토 상태는 이벤트로 계산한다 */
export function viewOf(job: string, st: Store, version?: number, variant?: DemoVariant, now = Date.now()): JudgmentView {
  tick(st, now);
  const v = version ?? st.latest;
  if (st.latest === 0 || !Number.isInteger(v) || v < 1 || v > st.latest) throw fail(404, `판정이 없음: ${job}${version ? ` 버전 ${version}` : ""}`);
  const base = viewFor(st.scen, variant);
  const r = base.consistency.results[0];
  if (v >= 2) {
    const f = r.findings.find((x) => x.id === CHANGED_ID);
    if (f && f.verdict === "근거부족") {
      f.verdict = "경계";
      r.summary["근거부족"] -= 1;
      r.summary["경계"] += 1;
      base.display[CHANGED_ID] = displayOf(f, f.trace_id ? r.traces[f.trace_id] : undefined);
    }
  }
  if (st.startedAt !== 0 && now - st.startedAt > WRITING_MS) {
    for (const [id, e] of Object.entries(base.explanations)) {
      if (e.status === "작성 중") base.explanations[id] = template("작성한 설명입니다.");
    }
  }
  return {
    job_id: /^U-/.test(job) ? job : JOB, version: v, is_latest: v === st.latest, handoff_seq: v === 1 ? 1 : st.v2Handoff,
    judged_at: v === 1 ? base.judged_at : kst(st.v2At ?? now), consistency: base.consistency,
    explanations: base.explanations, reviews: reviewStates(st, r.findings), field_status: base.field_status, display: base.display,
  };
}

/** 이벤트로 항목별 현재 검토 상태를 계산한다 (backend judge/service.py _review_states) */
function reviewStates(st: Store, findings: Finding[]): Record<string, ReviewState> {
  const current = new Map(findings.map((f) => [f.id, fingerprint(f)]));
  const out: Record<string, ReviewState & { sha: string | null }> = {};
  for (const e of st.events) {
    const s = (out[e.finding_id] ??= { status: "미검토", comment: null, reviewer: null, at: null, history_count: 0, stale: false, last_event_id: e.event_id, sha: null });
    s.history_count += 1;
    s.last_event_id = e.event_id;
    if (e.action === "되돌리기") Object.assign(s, { status: "미검토", comment: null, reviewer: e.reviewer, at: e.at, sha: null });
    else if (e.action === "의견") {
      // 처리 상태와 stale 을 바꾸지 않는다. 처리한 항목은 승인 사유·처리자도 지우지 않는다
      if (s.status === "미검토") Object.assign(s, { comment: e.comment, reviewer: e.reviewer, at: e.at });
    } else Object.assign(s, { status: e.action as ReviewState["status"], comment: e.comment, reviewer: e.reviewer, at: e.at, sha: e.sha });
  }
  return Object.fromEntries(
    Object.entries(out).map(([id, s]) => {
      const { sha, ...rest } = s;
      return [id, { ...rest, stale: s.status !== "미검토" && sha !== current.get(id) }];
    }),
  );
}

function counts(st: Store, view: JudgmentView) {
  const findings = view.consistency.results[0].findings;
  const unresolved: string[] = [];
  const byStatus: Record<string, number> = {};
  for (const f of findings) {
    const s = view.reviews[f.id];
    const status = s?.status ?? "미검토";
    if (NEEDS_REVIEW.includes(f.verdict) && (status === "미검토" || s?.stale)) unresolved.push(f.id);
    else if (status !== "미검토" && !s?.stale) byStatus[status] = (byStatus[status] ?? 0) + 1;
  }
  const marks = new Map(view.field_status.map((m) => [`${m.msds_index}|${m.field}`, m.status]));
  const statuses = [...marks.values()];
  const asIs = Math.max(FIELDS_TOTAL - marks.size, 0);
  const values = {
    state: (marks.size === 0 ? "미검수" : asIs === 0 ? "완료" : "일부") as SaveOverview["values"]["state"],
    model_as_is: asIs, confirmed: statuses.filter((x) => x === "확인함").length, edited: statuses.filter((x) => x === "수정됨").length, fields_total: FIELDS_TOTAL,
  };
  return { unresolved, byStatus, values, findings };
}

const countBy = (findings: Finding[]) =>
  ({ 일치: 0, 불일치: 0, 경계: 0, 근거부족: 0, 경고: 0, 참고: 0, "범위 외": 0, ...Object.fromEntries(["일치", "불일치", "경계", "근거부족", "경고", "참고", "범위 외"].map((v) => [v, findings.filter((f) => f.verdict === v).length])) }) as SaveOverview["verdicts"]["total"];

export function statusOf(job: string, st: Store, now = Date.now()): JudgmentStatus {
  tick(st, now);
  if (st.latest === 0) {
    // 판정이 아직 없다: 넘김도 없으면 판정 없음, 넘겼으면 판정 중 (서버는 모르는 작업에도 404 가 아니라 판정 없음으로 답한다)
    return { job_id: /^U-/.test(job) ? job : JOB, state: st.failed ? "판정 실패" : st.pending !== null ? "판정 중" : "판정 없음", latest_version: null, pending_handoff: st.pending, explanations: { done: 0, total: 0 }, saved_snapshot: null, error: st.failed ?? null, unreviewed: 0 };
  }
  const view = viewOf(job, st, undefined, undefined, now);
  const exps = Object.values(view.explanations);
  return {
    job_id: view.job_id, state: st.pending !== null ? "판정 중" : "판정 있음", latest_version: st.latest, pending_handoff: st.pending,
    explanations: { done: exps.filter((e) => e.status === "완료").length, total: exps.length },
    saved_snapshot: st.snapshots[0]?.snapshot_no ?? null, error: null, unreviewed: counts(st, view).unresolved.length,
  };
}

export function versionsOf(job: string, st: Store, now = Date.now()): VersionListItem[] {
  tick(st, now);
  if (st.latest === 0) throw fail(404, `판정이 없음: ${job}`);
  const list: VersionListItem[] = [];
  for (let n = st.latest; n >= 1; n -= 1) {
    const v = viewOf(job, st, n, undefined, now);
    list.push({ version: n, handoff_seq: v.handoff_seq, judged_at: v.judged_at, summary: v.consistency.results[0].summary, changed_findings: n >= 2 ? [CHANGED_ID] : [] });
  }
  return list;
}

/** 옛 화면을 보고 확정하거나, 고친 값을 판정하기 전에 저장해 추출값과 판정이 어긋나는 일을 막는다 */
function checkCurrent(st: Store, seenVersion: number) {
  if (st.pending !== null) throw fail(409, { message: `넘김 기록 ${st.pending}을 아직 판정하지 않음`, latest_version: st.latest, pending_handoff: st.pending });
  if (seenVersion !== st.latest) throw fail(409, { message: `최신 판정 버전은 ${st.latest}`, latest_version: st.latest, pending_handoff: null });
}

/** demo-conflict: 화면이 버전 1 을 읽은 뒤 더 새 판정(버전 2)이 생긴 것으로 한다. 첫 쓰기 요청 때 일어난다 */
function armConflict(st: Store, now: number) {
  if (!st.armConflict) return;
  st.armConflict = false;
  st.latest = 2;
  st.v2At = now;
  st.handoff = 2;
  st.v2Handoff = 2;
}

export function postReviewTo(job: string, st: Store, req: ReviewEventRequest, now = Date.now()): ReviewEvent {
  tick(st, now);
  if (st.latest === 0) throw fail(404, `판정이 없음: ${job}`);
  armConflict(st, now);
  checkCurrent(st, req.seen_version);
  const view = viewOf(job, st, undefined, undefined, now);
  const f = view.consistency.results[0].findings.find((x) => x.id === req.finding_id);
  if (!f) throw fail(404, `이 판정 버전에 없는 항목: ${req.finding_id}`);
  if (!(ACTION_VERDICTS[req.action] ?? ["일치", "불일치", "경계", "근거부족", "경고", "참고", "범위 외"]).includes(f.verdict)) throw fail(422, `${f.verdict} 판정에는 '${req.action}'을 쓸 수 없음`);
  if ((req.action === "예외 승인" || req.action === "의견") && !(req.comment ?? "").trim()) throw fail(422, `${req.action}에는 의견이 필요합니다`);
  if (req.seen_event_id !== undefined) {
    const last = [...st.events].reverse().find((e) => e.finding_id === req.finding_id)?.event_id ?? null;
    if (last !== req.seen_event_id) throw fail(409, { message: `다른 검토자가 먼저 처리함 (이벤트 ${last})`, latest_version: st.latest, pending_handoff: null });
  }
  const event: StoredEvent = {
    event_id: (st.events[st.events.length - 1]?.event_id ?? 0) + 1, job_id: view.job_id, finding_id: req.finding_id, action: req.action,
    comment: req.comment?.trim() || null, reviewer: req.reviewer, at: kst(now), version: st.latest, verdict_seen: f.verdict, sha: fingerprint(f),
  };
  st.events.push(event);
  const { sha, ...out } = event;
  void sha;
  return out;
}

export function postSnapshotTo(job: string, st: Store, req: SaveRequest, now = Date.now()): Snapshot {
  tick(st, now);
  if (st.latest === 0) throw fail(404, `판정이 없음: ${job}`);
  if (st.scen === "savefail") throw fail(500, "서버가 저장을 마치지 못했습니다.");
  armConflict(st, now);
  checkCurrent(st, req.seen_version);
  const view = viewOf(job, st, undefined, undefined, now);
  const c = counts(st, view);
  const snap: Snapshot = {
    contract: "snapshot/1", job_id: view.job_id, snapshot_no: st.snapshots.length + 1, handoff_seq: view.handoff_seq, version: view.version,
    last_review_event_id: st.events[st.events.length - 1]?.event_id ?? null,
    counts: {
      findings: c.findings.filter((f) => JUDGED.includes(f.verdict)).length, 미검토: c.unresolved.length, "불일치 확정": c.byStatus["불일치 확정"] ?? 0,
      "예외 승인": c.byStatus["예외 승인"] ?? 0, 확인: c.byStatus["확인"] ?? 0, "미검수 칸": c.values.model_as_is,
    },
    saved_by: req.reviewer, saved_at: kst(now), note: req.note ?? null,
  };
  st.snapshots.unshift(snap);
  return snap;
}

/** A2: 추출값 확인을 마치고 판정으로 넘긴다. 3초 뒤 새 판정 버전이 생긴다 */
export function toJudgmentTo(job: string, st: Store, now = Date.now()) {
  tick(st, now);
  st.handoff += 1;
  st.pending = st.handoff;
  st.judgeAt = now + JUDGE_MS;
  return { job_id: /^U-/.test(job) ? job : JOB, handoff_seq: st.handoff };
}

/** 서버 구현의 넘김 응답 (POST /api/documents/{id}/handoffs, 201): 화면은 job_id·handoff_seq 만 쓴다 */
export function handoffTo(job: string, st: Store, now = Date.now()) {
  const base = toJudgmentTo(job, st, now);
  return { ...base, as_of: "2026-11-02", extraction_sha256: "0".repeat(64), validator: { version: "v0.6", errors: 0, warnings: 0 } };
}

export function historyOf(job: string, st: Store, now = Date.now()): HistoryEntry[] {
  if (st.latest === 0) return [];
  const view = viewOf(job, st, undefined, undefined, now);
  const byId = new Map(view.consistency.results[0].findings.map((f) => [f.id, f]));
  const current = new Set(byId.keys());
  const rows: [number, number, HistoryEntry][] = st.events.map((e) => {
    const f = byId.get(e.finding_id);
    return [Date.parse(e.at), e.event_id, { at: e.at, reviewer: e.reviewer, area: f?.section === "15" ? "15항" : "2항", target: f?.label ?? e.finding_id, action: e.action, detail: e.verdict_seen, comment: e.comment, ref: { finding_id: e.finding_id, version: e.version, in_latest: current.has(e.finding_id) } }];
  });
  for (const s of st.snapshots) rows.push([Date.parse(s.saved_at), (s.last_review_event_id ?? 0) + 0.5, { at: s.saved_at, reviewer: s.saved_by, area: "저장", target: `저장본 ${s.snapshot_no}`, action: "저장", detail: `판정 버전 ${s.version}`, comment: s.note, ref: { snapshot_no: s.snapshot_no } }]);
  return rows.sort((a, b) => b[0] - a[0] || b[1] - a[1]).map((r) => r[2]);
}

/** A2: 추출값 검수 기록 (GET /api/documents/{id}/review/log) */
export function reviewLogOf(): HistoryEntry[] {
  return [
    { at: "2026-11-02T09:50:00+09:00", reviewer: "김검수", area: "추출값", target: "3항 · 황산 함유량", action: "수정", detail: "93~98 → 95~98", comment: null, ref: { msds_index: 0, path: "components[0].content" } },
    { at: "2026-11-02T09:45:00+09:00", reviewer: "김검수", area: "추출값", target: "2항 · 신호어", action: "확인함", detail: null, comment: null, ref: { msds_index: 0, path: "hazard.signal_word" } },
  ];
}

export function saveOverviewOf(job: string, st: Store, now = Date.now()): SaveOverview {
  const view = viewOf(job, st, undefined, undefined, now);
  const c = counts(st, view);
  const findings = c.findings;
  return {
    job_id: view.job_id, version: view.version, handoff_seq: view.handoff_seq,
    verdicts: { total: countBy(findings), by_section: { "2": countBy(findings.filter((f) => f.section === "2")), "15": countBy(findings.filter((f) => f.section === "15")) } },
    reviews: { 미검토: c.unresolved.length, "불일치 확정": c.byStatus["불일치 확정"] ?? 0, "예외 승인": c.byStatus["예외 승인"] ?? 0, 확인: c.byStatus["확인"] ?? 0, unreviewed_ids: c.unresolved },
    values: c.values, snapshots: st.snapshots,
  };
}

export function summaryItemOf(job: string, st: Store, now = Date.now()): JudgmentBatchItem {
  const s = statusOf(job, st, now);
  if (st.latest === 0) return { job_id: s.job_id, state: s.state, latest_version: null, unreviewed: 0, saved_snapshot: null, saved_at: null, data_grade: "실버" };
  const view = viewOf(job, st, undefined, undefined, now);
  const last = st.snapshots[0];
  const c = counts(st, view);
  // 골드 = 최신 저장본이 지금의 값·판정·검토 기록을 그대로 담고 미검토·미검수 칸이 없음
  const current = !!last && last.version === view.version && last.handoff_seq === view.handoff_seq && last.last_review_event_id === (st.events[st.events.length - 1]?.event_id ?? null);
  return {
    job_id: view.job_id, state: s.state, latest_version: s.latest_version, unreviewed: s.unreviewed, saved_snapshot: s.saved_snapshot, saved_at: last?.saved_at ?? null,
    data_grade: current && last.counts.미검토 === 0 && last.counts["미검수 칸"] === 0 && c.values.fields_total > 0 ? "골드" : "실버",
  };
}

const escapeHtml = (s: string) => s.replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[ch] ?? ch);

/** 리포트 파일 (개발용 내용: 판정 표만 담은 간단한 문서). pdffail 은 글이 빠진 PDF 를 흉내 내 422 */
export function reportOf(job: string, st: Store, req: ReportRequest, now = Date.now()): { contentType: string; filename: string; body: string } {
  if (req.format === "pdf" && st.scen === "pdffail") throw fail(422, "PDF에 글이 빠짐, 리포트를 내보내지 않음: '재생성 MSDS 2항 글이 비어 있음'");
  if (req.snapshot_no != null && !st.snapshots.some((s) => s.snapshot_no === req.snapshot_no)) throw fail(404, `저장본이 없음: ${job} ${req.snapshot_no}`);
  const view = viewOf(job, st, undefined, undefined, now);
  const r = view.consistency.results[0];
  // 서버(reports.filename): 제품명_MSDS_검토결과.확장자 (저장본 번호는 파일 이름에 넣지 않는다)
  const base = `${st.scen === "single" ? "수소" : "황산"}_MSDS_검토결과`;
  const include = req.include;
  if (req.format === "json") {
    const body = { contract: "report/1", job_id: view.job_id, snapshot: st.snapshots.find((s) => s.snapshot_no === req.snapshot_no) ?? null, version: view.version, extraction: { doc: { doc_id: r.msds_index === 0 ? "KZ-A-S004" : "" }, msds: [] }, field_status: view.field_status, consistency: view.consistency, reviews: view.reviews, events: st.events.map(({ sha, ...e }) => (void sha, e)) };
    return { contentType: "application/json", filename: `${base}.json`, body: JSON.stringify(body) };
  }
  const rows = r.findings.filter((f) => f.kind !== "product_type" && ((f.section === "2" && (include.findings_2 || req.format === "xlsx")) || (f.section === "15" && (include.findings_15 || req.format === "xlsx"))));
  const tr = rows.map((f) => `<tr><td>${f.section}항</td><td>${escapeHtml(f.label)}</td><td>${escapeHtml(view.display[f.id].msds)}</td><td>${escapeHtml(view.display[f.id].expected)}</td><td>${f.verdict}</td><td>${view.reviews[f.id]?.status ?? "미검토"}</td></tr>`).join("");
  const html = `<!doctype html><html lang="ko"><meta charset="utf-8"><title>${escapeHtml(base)}</title><h1>${escapeHtml(base)}</h1><p>개발용 임시 리포트입니다.</p><table border="1" cellpadding="4"><tr><th>항</th><th>항목</th><th>MSDS 기재</th><th>검증 결과</th><th>판정</th><th>처리</th></tr>${tr}</table>`;
  if (req.format === "html") return { contentType: "text/html; charset=utf-8", filename: `${base}.html`, body: html };
  if (req.format === "xlsx") return { contentType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename: `${base}.xlsx`, body: `개발용 임시 파일입니다 (실제 xlsx 아님)\n${rows.map((f) => [f.section, f.label, view.display[f.id].msds, view.display[f.id].expected, f.verdict].join("\t")).join("\n")}` };
  return { contentType: "application/pdf", filename: `${base}.pdf`, body: "%PDF-1.4\n% 개발용 임시 파일입니다 (실제 PDF 아님)\n" };
}

