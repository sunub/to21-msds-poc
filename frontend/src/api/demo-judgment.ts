/*
 * 판정 API(계약 5-api)의 데모 응답 (개발용): 25번 황산 KZ-A-S004.
 * 서버가 없을 때 judgments.ts 가 이 모듈을 대신 쓴다. 값은 계약 모양(judgment_view, status, versions, snapshot)이고,
 * 화면은 api/adapt 의 변환 계층을 거쳐 이전과 같은 모습으로 나온다.
 *
 * 데모 문서
 *   ?doc=demo           기본 (혼합물, 처리 전)
 *   ?doc=demo-states    새 상태: 설명 작성 중 1건, 판정이 바뀐(stale) 검토 1건, 더 새 넘김 기록(pending_handoff)
 *   ?doc=demo-conflict  검토·저장 요청이 409 로 막힌다 (더 새 판정 버전이 있다)
 * 검토·저장은 sessionStorage 에 남아 새로고침해도 이어진다 (서버를 흉내 낸다).
 */
import { ApiRequestError } from "./client";
import type {
  ExplanationEntry,
  JudgmentStatus,
  JudgmentView,
  ReviewEvent,
  ReviewEventRequest,
  ReviewState,
  SaveRequest,
  Snapshot,
  VersionListItem,
} from "./contract/api";
import type { Consistency, Finding, MsdsResult, Trace } from "./contract/consistency";
import type { DemoVariant } from "./judgments";

const JOB = "U-20261102-025";
const COMP_H2SO4 = { comp_ref: "1", cas: "7664-93-9", name: "황산" };
const COMP_H2 = { comp_ref: "1", cas: "1333-74-0", name: "수소" };
const KNOWLEDGE = { provider: "to21", version: "ref-2026.10", rules: "r0.3", logic: "to21_v6@6" } as const;

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
  trace?: Omit<Trace, "knowledge_version" | "thresholds" | "assumptions" | "inputs"> & Partial<Pick<Trace, "thresholds" | "assumptions" | "inputs">>;
  explain?: string;
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
  expected: { present: true, applicable: "해당" as const, threshold, content: range(93, 98), status: "확정" as const, source: "규제DB" },
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
        verdict: "불일치", type: "형태·세부 표기", severity: "중간", rule: "ATE-INHAL-MIST", causes: ["FORM_DIFF"],
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
      { present: false, status: "근거부족" },
      {
        verdict: "근거부족", rule: "METAL-CORR-TEST",
        explain: "혼합물 시험자료가 없어 판정할 수 없습니다. 판정을 빼지 않고 근거부족으로 표시해 검토자에게 넘깁니다.",
        trace: { kind: "reference_lookup", rule: { id: "METAL-CORR-TEST", basis: "9항 시험값" }, steps: [{ step: "9항 시험값: 제품 시험자료 없음" }] },
      }),
    cls("ENV_AQ_CHRONIC", "-", null,
      { category: "3", evidence: [{ field: "hazard.classes[7]", page: 4 }] },
      { present: false, status: "근거부족" },
      {
        verdict: "근거부족", rule: "AQUATIC-CHRONIC-SUM",
        explain: "황산과 물 모두 기준정보에 수생 분류가 없어, MSDS 구분3의 근거를 확인해야 합니다.",
        trace: { kind: "reference_lookup", rule: { id: "AQUATIC-CHRONIC-SUM", basis: "M-factor 가산" }, steps: [{ step: "황산: 기준정보에 수생 분류 없음" }, { step: "물: 기준정보에 수생 분류 없음" }] },
      }),
    {
      id: "m0/F2L:H:H318", section: "2", kind: "label", item: "H318", comp: null,
      msds: { present: true, code: "H318", evidence: [{ field: "label.hazard_statements[1]", page: 4 }] },
      expected: { present: false, code: "H318", status: "확정" },
      verdict: "불일치", type: "표시 요소 불일치", severity: "낮음", rule: "LABEL-H-DUP",
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
    reg("OSH", item, COMP_H2, { present: true, applicable: "해당", threshold: th, content: q("99.99 이상", 99.99), evidence: ev12 }, { present: true, applicable: "해당", threshold: th, status: "확정" }, { rule: "REG-DB-LOOKUP", trace: { kind: "regulation_check", rule: { id: "REG-DB-LOOKUP", basis: "규제DB 조회 (as_of 기준)" }, steps: [{ step: "수소: 해당" }] } });
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

function build(specs: Spec[], opts: { productType: "단일물질" | "혼합물" | "불명확"; limitations: MsdsResult["limitations"] }): Consistency {
  const sorted = [...specs].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  const traces: MsdsResult["traces"] = {};
  let n = 0;
  const findings: Finding[] = sorted.map((s) => {
    const withTrace = !!s.trace;
    const traceId = withTrace ? `T-${String(++n).padStart(4, "0")}` : null;
    if (s.trace && traceId) {
      traces[traceId] = { thresholds: [], assumptions: [], inputs: [], knowledge_version: KNOWLEDGE.version, ...s.trace } as Trace;
    }
    // 성분에 걸린 판정은 성분표 쪽(혼합물 3쪽, 단일물질 2쪽)을 근거로 단다 (성분별 요약 탭의 원문 이동용)
    const msds = s.comp
      ? { ...s.msds, evidence: [...(s.msds.evidence ?? []), { field: "components[0].name", page: opts.productType === "단일물질" ? 2 : 3 }] }
      : s.msds;
    return {
      id: s.id, section: s.section, kind: s.kind, item: s.item, comp: s.comp, msds, expected: s.expected,
      verdict: s.verdict, type: s.type ?? null, severity: s.severity ?? null, rule: s.rule ?? null, causes: s.causes ?? [],
      trace_id: traceId, needs_explanation: ["불일치", "경계", "근거부족"].includes(s.verdict),
    };
  });
  const summary = { 일치: 0, 불일치: 0, 경계: 0, 근거부족: 0, 참고: 0, "범위 외": 0 };
  for (const f of findings) summary[f.verdict] += 1;
  return {
    contract: "consistency/1", doc_id: "KZ-A-S004", as_of: "2026-11-02", engine_version: "0.1.0", knowledge: KNOWLEDGE,
    results: [{
      msds_index: 0, msds_revision_date: "2022-06-29", product_type: { value: opts.productType, basis: opts.productType === "불명확" ? "성분 정보를 읽지 못함" : "성분표 기준" },
      summary, findings, traces, limitations: opts.limitations,
    }],
  };
}

const template = (text: string): ExplanationEntry => ({ status: "완료", by: "template", checked: true, summary: text, reasons: [], basis: [] });

/** 판정 한 벌을 만든다. job 은 데모 문서 번호, variant 는 성분 요약의 단일물질·판별 불가 */
function viewFor(job: string, variant: DemoVariant): JudgmentView {
  const states = job === "demo-states";
  const single = variant === "single";
  const specs = single ? singleSpecs() : [...mixtureSpecs(), ...(states ? [writingSpec()] : [])];
  const explainText = new Map(specs.filter((s) => s.explain).map((s) => [s.id, s.explain as string]));
  const consistency = build(specs, {
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
    if (!f.needs_explanation) continue;
    explanations[f.id] = f.id === WRITING_ID ? { status: "작성 중" } : template(explainText.get(f.id) ?? "");
  }
  const reviews: Record<string, ReviewState> = {};
  if (states) {
    reviews[STALE_ID] = { status: "불일치 확정", comment: "시험자료 확인 예정", reviewer: "김검수", at: "2026-11-02T10:30:00+09:00", history_count: 2, stale: true };
  }
  return {
    job_id: JOB, version: 1, is_latest: true, handoff_seq: 1, judged_at: "2026-11-02T10:00:00+09:00",
    consistency, explanations, reviews,
    field_status: states ? [{ msds_index: 0, field: "hazard.classes[3]", status: "확인함" }, { msds_index: 0, field: "toxicity.acute[0]", status: "수정됨" }] : [],
  };
}

/* ── 서버 흉내: 검토·저장은 sessionStorage 에 쌓는다 ───────────── */

type Store = { reviews: Record<string, ReviewState>; events: number; snapshots: number };
const key = (job: string) => `msds.demo-judgment.${job}`;

function readStore(job: string): Store {
  try {
    const raw = window.sessionStorage.getItem(key(job));
    if (raw) return JSON.parse(raw) as Store;
  } catch {
    // 저장소를 못 쓰면 이 호출 안에서만 처리한다
  }
  return { reviews: {}, events: 0, snapshots: 0 };
}

function writeStore(job: string, store: Store) {
  try {
    window.sessionStorage.setItem(key(job), JSON.stringify(store));
  } catch {
    // 저장소를 못 쓰면 남기지 못한다 (새로고침하면 사라짐)
  }
}

export function demoView(job: string, variant?: DemoVariant): JudgmentView {
  const view = viewFor(job, variant);
  return { ...view, reviews: { ...view.reviews, ...readStore(job).reviews } };
}

export function demoStatus(job: string): JudgmentStatus {
  const view = viewFor(job, undefined);
  const explanations = Object.values(view.explanations);
  const states = job === "demo-states";
  return {
    job_id: JOB, state: states ? "판정 중" : "판정 있음", latest_version: 1, pending_handoff: states ? 2 : null,
    explanations: { done: explanations.filter((e) => e.status === "완료").length, total: explanations.length },
    saved_snapshot: readStore(job).snapshots || null, error: null,
  };
}

export function demoVersions(job: string): VersionListItem[] {
  const view = viewFor(job, undefined);
  return [{ version: 1, handoff_seq: 1, judged_at: view.judged_at, summary: view.consistency.results[0].summary, changed_findings: [] }];
}

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** 검토 남기기. demo-conflict 는 늘 409(더 새 판정 버전이 있음) */
export async function demoPostReview(job: string, req: ReviewEventRequest): Promise<ReviewEvent> {
  await delay(120);
  if (job === "demo-conflict") throw new ApiRequestError(409, "http_409", "더 새로운 판정 버전이 있습니다.");
  const store = readStore(job);
  const prev = store.reviews[req.finding_id] ?? viewFor(job, undefined).reviews[req.finding_id];
  const at = `${new Date(Date.now() + 9 * 3600_000).toISOString().slice(0, 19)}+09:00`;
  const status: ReviewState["status"] =
    req.action === "되돌리기" ? "미검토" : req.action === "의견" ? (prev?.status ?? "미검토") : req.action;
  store.events += 1;
  store.reviews[req.finding_id] = {
    status,
    comment: req.action === "되돌리기" ? null : (req.comment ?? prev?.comment ?? null),
    reviewer: req.reviewer,
    at,
    history_count: (prev?.history_count ?? 0) + 1,
    stale: false,
  };
  writeStore(job, store);
  const verdictSeen = viewFor(job, undefined).consistency.results[0].findings.find((f) => f.id === req.finding_id)?.verdict ?? "일치";
  return { event_id: store.events, job_id: JOB, finding_id: req.finding_id, action: req.action, comment: req.comment ?? null, reviewer: req.reviewer, at, version: 1, verdict_seen: verdictSeen };
}

/** 저장. fail 이 true 면 서버 오류. demo-conflict 는 409 */
export async function demoPostSnapshot(job: string, req: SaveRequest, fail: boolean): Promise<Snapshot> {
  await delay(900);
  if (fail) throw new ApiRequestError(500, "http_500", "서버가 저장을 마치지 못했습니다.");
  if (job === "demo-conflict") throw new ApiRequestError(409, "http_409", "더 새로운 판정 버전이 있습니다.");
  const store = readStore(job);
  const view = demoView(job);
  const counts = { findings: 0, 미검토: 0, "불일치 확정": 0, "예외 승인": 0, 확인: 0, "미검수 칸": 0 };
  for (const f of view.consistency.results[0].findings) {
    if (f.kind === "product_type") continue;
    counts.findings += 1;
    const s = view.reviews[f.id]?.status ?? "미검토";
    counts[s] += 1;
  }
  store.snapshots += 1;
  writeStore(job, store);
  const kst = `${new Date(Date.now() + 9 * 3600_000).toISOString().slice(0, 19)}+09:00`;
  return {
    contract: "snapshot/1", job_id: JOB, snapshot_no: store.snapshots, handoff_seq: 1, version: req.seen_version,
    last_review_event_id: store.events || null, counts, saved_by: req.reviewer, saved_at: kst, note: req.note ?? null,
  };
}

export async function demoToJudgment(job: string) {
  await delay(300);
  void job;
  return { job_id: JOB, handoff_seq: 2 };
}
