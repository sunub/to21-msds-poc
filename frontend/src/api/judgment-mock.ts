/*
 * 개발 서버 전용 판정 API 대역. 값은 모두 가상이다 (TO21·HTODB 값을 넣지 않는다, D-47).
 * 계약 전체 모양을 돌려주고 judgment.ts 의 같은 zod 로 확인하므로, 진짜 서버로 바꿔도 화면 코드는 그대로다.
 *
 * 켜기: 주소에 ?judgmentMock=<상황> (탭을 옮겨도 유지). 끄기: ?judgmentMock=off
 * 상황: ready · none · running · failed · rerun · writing · stale · clean · empty · conflict · savefail · bad · multi
 *       성분별 요약: ready(혼합물, 성분 2) · single(단일물질) · nocomp(판정에 성분 요약 칸이 아직 없음)
 *       이력만 다른 상황: nolog(추출값 이력 없음) · nohistory(판정 이력 없음) · logfail(추출값 이력 500) · nofield(이력 0건) · many(추출값 이력 250건) · badlog(이력 모양 위반)
 */
import { ApiRequestError } from "./client";

const KEY = "msds.judgmentMock";

export function mockScenario(): string | null {
  if (typeof window === "undefined") return null;
  const param = new URLSearchParams(window.location.search).get("judgmentMock");
  try {
    if (param === "off") window.sessionStorage.removeItem(KEY);
    else if (param) window.sessionStorage.setItem(KEY, param);
    return window.sessionStorage.getItem(KEY);
  } catch {
    return param === "off" ? null : param;
  }
}

export const mockActive = () => mockScenario() !== null;

type Row = {
  key: string;
  law: string;
  lawLabel: string;
  code: string;
  label: string;
  comp: 0 | 1 | null;
  verdict: string;
  type?: string;
  severity?: string;
  scope?: string;
  msds: string;
  expected: string;
  page?: number;
  source?: string;
  basis?: string[];
  summary?: string;
  by?: "llm" | "template";
};

const COMPONENTS = [
  { comp_ref: "1", cas: "0000-00-1", name: "가상물질 A", text: "가상물질 A (93~98)" },
  { comp_ref: "2", cas: "0000-00-2", name: "가상물질 B", text: "가상물질 B (2~7)" },
];

/* ── 성분별 요약 (3-consistency component_summary·limitations). 2항 판정 몇 줄도 함께 둔다 (제약사항이 가리킬 판정) ── */
type HazardRow = {
  code: string;
  form: string | null;
  label: string;
  verdict: string;
  /** finding_id 의 내용 키가 F2:<코드>:<형태> 가 아닐 때 (표시 요소 등) */
  key?: string;
  kind?: "class" | "label";
  method?: string;
  type?: string;
  severity?: string;
  scope?: string;
  msds?: string;
  expected?: string;
  pages?: { section: number; page: number }[];
  source?: string;
  basis?: string[];
  calc?: string[];
  summary?: string;
  by?: "llm" | "template";
};
const P2 = { section: 2, page: 1 };
const hazardMatch = (code: string, label: string): HazardRow => ({
  code, form: null, label, verdict: "일치", method: "가산·한계농도", msds: "구분 1", expected: "구분 1", pages: [P2], basis: ["MSDS 기재와 계산 결과가 같음"],
});
const hazardNote = (code: string, label: string, verdict: string, scope: string | undefined, reason: string): HazardRow => ({
  code, form: null, label, verdict, scope, method: "판정하지 않음", msds: "기재 없음", expected: `— (${scope ?? verdict})`, basis: [reason],
});
/* 앞의 세 줄은 limitationsFor 가 자리로 가리킨다. 순서를 바꾸지 않는다 */
const HAZARD_MIX: HazardRow[] = [
  {
    code: "PH_METAL_CORR", form: null, label: "금속부식성", verdict: "근거부족", method: "9항 시험값", msds: "구분 1", expected: "— (제품 시험자료 없음)", pages: [P2],
    basis: ["9항에 금속 부식 시험값 없음", "판정에 필요한 값이 없어 판단하지 않음"], by: "template", summary: "금속부식성 판정에 필요한 제품 시험값이 없어 판단하지 않았습니다.",
  },
  {
    code: "ENV_AQ_CHRONIC", form: null, label: "만성 수생환경", verdict: "근거부족", method: "M계수 가산", msds: "구분 3", expected: "— (기준정보 없음)", pages: [P2, { section: 12, page: 2 }],
    basis: ["가상물질 A·B 모두 기준정보에 수생 분류 없음"], by: "template", summary: "성분의 수생 분류 기준정보가 없어 판단하지 않았습니다.",
  },
  {
    code: "HH_ACUTE_INHAL", form: "분진·미스트", label: "급성 독성 (흡입)", verdict: "불일치", type: "형태·세부 표기", severity: "중간", method: "ATEmix 계산",
    msds: "구분 2 (증기)", expected: "구분 2 (분진·미스트)", pages: [P2, { section: 11, page: 2 }], source: "급성 독성(흡입: 증기) : 구분 2",
    basis: ["가상물질 A 93~98% · 0.375 mg/L (분진·미스트) · 11항 3단계"], calc: ["상한 98%: 100 / (98 / 0.375) = 0.383", "하한 93%: 100 / (93 / 0.375) = 0.403", "→ 분진·미스트 구분 2 (확정)"], by: "llm",
    summary: "주성분의 흡입 독성값은 분진·미스트 기준인데, MSDS 2항은 증기로 적었습니다. 구분은 같고 형태 표기가 다릅니다.",
  },
  {
    code: "HH_SKIN_CORR", form: null, label: "피부 부식성/자극성", verdict: "불일치", type: "과소분류", severity: "높음", method: "가산·한계농도", msds: "구분 2", expected: "구분 1", pages: [P2],
    source: "피부 부식성/자극성 : 구분 2", basis: ["가상물질 A 93~98% · 기준 분류 구분 1", "구분 1 성분 합계 ≥ 5% → 구분 1"], calc: ["구분 1 성분 합계: 하한 93 · 상한 98"], by: "llm",
    summary: "가상물질 A의 함량이 기준 5%를 넘어 구분 1로 계산했습니다. MSDS 2항은 구분 2로 적어 실제보다 낮게 분류했습니다.",
  },
  {
    code: "SIGNAL", key: "F2L:SIGNAL", kind: "label", form: null, label: "표시 요소 (신호어)", verdict: "불일치", type: "표시 요소 불일치", severity: "낮음", method: "별표2 매핑", msds: "경고", expected: "위험", pages: [P2],
    source: "신호어 : 경고", basis: ["분류에서 도출: 위험", "MSDS 기재: 경고"], by: "template", summary: "2항 분류로 보면 신호어는 위험인데 MSDS는 경고로 적었습니다.",
  },
  {
    code: "HH_REPRO", form: null, label: "생식독성", verdict: "경계", method: "가산·한계농도", msds: "구분 2", expected: "구분 1B~2 (함량에 따라 다름)", pages: [P2],
    basis: ["가상물질 B 2~7%, 함량 범위가 기준에 걸침"], calc: ["하한 2% → 구분 2", "상한 7% → 구분 1B"], by: "llm", summary: "성분 함량 범위가 기준에 걸쳐 구분을 하나로 정할 수 없습니다.",
  },
  hazardMatch("HH_EYE_DMG", "심한 눈 손상성/자극성"),
  hazardMatch("HH_CARCINOGEN", "발암성"),
  hazardMatch("HH_STOT_SE", "특정 표적장기 독성 (1회)"),
  hazardNote("PH_FLAM_GAS", "인화성 가스", "범위 외", "해당 없음", "제품 성상이 액체라 이 항목은 판정 대상이 아님"),
  hazardNote("PH_AEROSOL", "에어로졸", "범위 외", "해당 없음", "제품 성상이 액체라 이 항목은 판정 대상이 아님"),
  hazardNote("PH_EXPLOSIVE", "폭발성 물질", "범위 외", "대조만", "판정하지 않고 MSDS 기재와 성분 분류를 나란히 두는 항목"),
  hazardNote("ENV_OZONE", "오존층 유해성", "참고", undefined, "국내 고시 밖 구분이라 참고로만 보여 줌"),
];
const needsExplanation = (verdict: string) => ["불일치", "경계", "근거부족"].includes(verdict);
const HAZARD_SINGLE: HazardRow[] = [{ code: "PH_FLAM_GAS", form: null, label: "인화성 가스", verdict: "일치" }];
const hazardId = (h: HazardRow, m: number) => `m${m}/${h.key ?? `F2:${h.code}:${h.form ?? "-"}`}`;

function hazardFinding(h: HazardRow, m: number) {
  return {
    id: hazardId(h, m),
    section: "2",
    kind: h.kind ?? "class",
    item: h.code,
    comp: null,
    msds: {
      ...emptyQ(),
      present: h.msds ? h.msds !== "기재 없음" : h.verdict === "일치",
      evidence: h.source ? [{ field: "hazard.classes[0].raw", page: h.pages?.[0]?.page ?? 1, source_text: h.source }] : [],
    },
    expected: { ...emptyQ(), status: h.verdict === "근거부족" ? "근거부족" : h.verdict === "경계" ? "경계" : "확정", low: null, high: null, source: "가상 분류기준" },
    verdict: h.verdict,
    type: h.type ?? null,
    severity: h.severity ?? null,
    rule: null,
    causes: [],
    trace_id: null,
    needs_explanation: needsExplanation(h.verdict),
    label: h.label,
    method: h.method ?? "혼합물 계산",
    out_of_scope_reason: h.scope ?? null,
    law_label: null,
  };
}

const noAte = (step: number, excluded: string) =>
  (["oral", "dermal", "inhal"] as const).map((route) => ({ route, value: null, unit: null, form: null, source: null, step, excluded }));

const SUMMARY_MIX = [
  {
    comp_ref: "1", name: "가상물질 A", cas: "0000-00-1",
    content: { raw: "93~98", value: null, lower_op: ">=", lower: 93, upper_op: "<=", upper: 98, unit: "%" },
    reference_classes: [
      { class_code: "HH_SKIN_CORR", category: "1", route_form: null, source: "가상 분류기준" },
      { class_code: "HH_EYE_DMG", category: "1", route_form: null, source: "가상 분류기준" },
      { class_code: "HH_CARCINOGEN", category: "1A", route_form: null, source: "가상 분류기준" },
      { class_code: "HH_STOT_SE", category: "1", route_form: null, source: "가상 분류기준" },
    ],
    ate: [
      { route: "oral", value: null, unit: null, form: null, source: null, step: 6, excluded: "11항 자료 없음" },
      { route: "inhal", value: 0.375, unit: "mg/L", form: "분진·미스트", source: "MSDS 11항", step: 3, excluded: null },
    ],
    regulation_hits: 8,
    reliability: "보통",
    notes: ["독성DB 수치와 분류 환산값이 없어 MSDS 11항 값을 썼습니다 (3단계)."],
  },
  {
    comp_ref: "2", name: "가상물질 B", cas: "0000-00-2",
    content: { raw: "2~7", value: null, lower_op: ">=", lower: 2, upper_op: "<=", upper: 7, unit: "%" },
    reference_classes: [],
    ate: noAte(5, "무독성"),
    regulation_hits: 6,
    reliability: "높음",
    notes: ["무독성 성분이라 급성 독성 계산에서 뺐습니다 (5단계)."],
  },
];

const SUMMARY_SINGLE = [
  {
    comp_ref: "1", name: "가상물질 A", cas: "0000-00-1",
    content: { raw: "99.9 이상", value: null, lower_op: ">=", lower: 99.9, upper_op: null, upper: null, unit: "%" },
    reference_classes: ["KR02 환경부", "KR03 고용노동부"].flatMap((source) => [
      { class_code: "PH_FLAM_GAS", category: "1", route_form: null, source },
      { class_code: "PH_PRESS_GAS", category: "압축가스", route_form: null, source },
    ]),
    ate: [],
    regulation_hits: 8,
    reliability: "높음",
    notes: [],
  },
];

function limitationsFor(m: number) {
  return [
    { finding_id: hazardId(HAZARD_MIX[0], m), text: "혼합물 시험자료가 없어 판정할 수 없습니다." },
    { finding_id: hazardId(HAZARD_MIX[1], m), text: "가상물질 A·B 모두 기준정보에 수생 분류가 없습니다. MSDS 구분 3의 근거를 확인해야 합니다." },
    { finding_id: hazardId(HAZARD_MIX[2], m), text: "기준정보 DB 값이 없어 MSDS 11항 값으로 계산했습니다. 자료 신뢰도 보통." },
    { finding_id: `m${m}/F15DG:MIX`, text: "제4류 판정에 필요한 인화점 값이 없습니다." },
  ];
}

const TODO: Row[] = [
  {
    key: "accident", law: "CCA", lawLabel: "화관법", code: "CCA_ACCIDENT", label: "사고대비물질", comp: 0,
    verdict: "불일치", type: "규제 누락", severity: "높음", msds: "기재 없음", expected: "해당 (≥ 10%)",
    basis: ["가상물질 A 93~98% ≥ 10% → 해당", "MSDS 15항에 해당 행 없음 → 규제 누락"], by: "llm",
    summary: "MSDS 15항에 사고대비물질 항목이 없습니다. 가상물질 A의 함량이 기준 10% 이상이라 규제 대상으로 판단했습니다.",
  },
  {
    key: "managed", law: "OSH", lawLabel: "산안법", code: "OSH_MANAGED", label: "관리대상유해물질", comp: 0,
    verdict: "불일치", type: "기준 불일치", severity: "중간", msds: "해당 (1% 이상)", expected: "해당 (≥ 0.1%)", page: 1,
    source: "관리대상유해물질 : 해당 (1% 이상)", basis: ["MSDS 기준 1% ≠ 규제DB 기준 0.1%", "해당 여부 같음 → 기준 불일치"], by: "template",
    summary: "해당 여부는 같지만 기준 농도가 다릅니다. MSDS는 1% 이상, 규제DB는 0.1% 이상입니다.",
  },
  {
    key: "existing", law: "KREACH", lawLabel: "화평법", code: "KREACH_EXIST", label: "등록대상기존화학물질", comp: 1,
    verdict: "경계", msds: "비해당", expected: "경계 (함량이 기준에 걸침)", page: 1,
    source: "화학물질의 등록 및 평가 등에 관한 법률 : 비해당", basis: ["하한 2% < 5% → 비해당", "상한 7% ≥ 5% → 해당", "→ 경계"], by: "llm",
    summary: "함량 범위 2~7%가 기준 5%에 걸쳐 있어 단정할 수 없습니다.",
  },
  {
    key: "dg", law: "DG", lawLabel: "위험물법", code: "DG", label: "위험물", comp: null,
    verdict: "근거부족", msds: "자료없음", expected: "판단 근거 없음", page: 1,
    basis: ["9항 인화점 값 없음", "제4류 판정에 필요한 값이 없어 판단하지 않음"], by: "template",
    summary: "제4류 판정에 필요한 인화점 값이 없어 판단하지 않았습니다.",
  },
];

const match = (comp: 0 | 1, i: number, lawLabel: string, law: string, label: string): Row => ({
  key: `m${comp}${i}`, law, lawLabel, code: `${law}_ITEM${i}`, label, comp, verdict: "일치", msds: "해당", expected: "해당", page: 1,
});
const MATCHES = (["작업환경측정 대상", "특수건강진단 대상", "허용기준 설정물질", "유독물질", "배출량조사 대상", "기존화학물질"] as const).flatMap(
  (label, i) => {
    const [lawLabel, law] = i < 3 ? ["산안법", "OSH"] : i < 5 ? ["화관법", "CCA"] : ["화평법", "KREACH"];
    return [match(0, i, lawLabel, law, label), match(1, i, lawLabel, law, label)];
  },
);
const NOTES: Row[] = [
  {
    key: "old", law: "CCA", lawLabel: "화관법", code: "CCA_ACUTE", label: "인체급성유해성물질", comp: 0, verdict: "참고", type: "구버전",
    msds: "유독물질로 기재", expected: "개정 표기 확인 · 시행 2025-01-01", basis: ["시행일 자료가 없어 PoC 판정에서 제외 (D-09)"],
  },
  {
    key: "status", law: "KREACH", lawLabel: "화평법", code: "KREACH_STATUS", label: "지위 정보", comp: 1, verdict: "범위 외", scope: "대조만",
    msds: "기재", expected: "대조만 함", basis: ["규제 해당 여부를 정하는 항목이 아니라 대조만 함"],
  },
];

function emptyQ() {
  return { present: true, category: null, route_form: null, code: null, applicable: null, threshold: null, content: null, dg: null, product_type: null, source: null, evidence: [], effective_from: null };
}

function finding(r: Row, msdsIndex: number) {
  const comp = r.comp === null ? null : COMPONENTS[r.comp];
  return {
    id: `m${msdsIndex}/${r.law === "DG" ? "F15DG" : "F15"}:${r.law === "DG" ? "MIX" : `${comp?.cas}:${r.law}.${r.code}`}`,
    section: "15",
    kind: r.law === "DG" ? "dangerous_goods" : "regulation",
    item: r.law === "DG" ? "DG" : `${r.law}.${r.code}`,
    comp: comp ? { comp_ref: comp.comp_ref, cas: comp.cas, name: comp.name } : null,
    msds: {
      ...emptyQ(),
      present: r.msds !== "기재 없음",
      evidence: r.source ? [{ field: "regulations[0].applicable", page: r.page ?? 1, source_text: r.source }] : [],
    },
    expected: { ...emptyQ(), status: r.verdict === "경계" ? "경계" : r.verdict === "근거부족" ? "근거부족" : "확정", low: null, high: null, source: "가상 규제DB", effective_from: r.type === "구버전" ? "2025-01-01" : null },
    verdict: r.verdict,
    type: r.type ?? null,
    severity: r.severity ?? null,
    rule: null,
    causes: [],
    trace_id: null,
    needs_explanation: ["불일치", "경계", "근거부족"].includes(r.verdict),
    label: r.label,
    method: "규제DB 대조",
    out_of_scope_reason: r.scope ?? null,
    law_label: r.lawLabel,
  };
}

/* ── 상태 ── */
const reviews = new Map<string, unknown>();
let startedAt = 0;
let startedFor = "";
let nextEvent = 1;
let handedOff = false;

function elapsedMs(scenario: string) {
  if (startedFor !== scenario) {
    startedFor = scenario;
    startedAt = Date.now();
    handedOff = false;
    reviews.clear();
    judgmentLog.length = 0;
  }
  return Date.now() - startedAt;
}

function rowsFor(scenario: string) {
  if (scenario === "empty") return [];
  if (scenario === "clean") return MATCHES;
  const all = [...TODO, ...MATCHES, ...NOTES];
  return scenario === "single" ? all.filter((r) => r.comp !== 1) : all;
}

function view(id: string, version: number, scenario: string) {
  const rows = rowsFor(scenario);
  const writing = scenario === "writing" && elapsedMs(scenario) < 6_000;
  const indexes = scenario === "multi" ? [0, 1] : [0];
  const single = scenario === "single";
  const noTodo = scenario === "empty" || scenario === "clean";
  const hazards = scenario === "empty" ? [] : scenario === "clean" ? HAZARD_MIX.filter((h) => h.verdict === "일치") : single ? HAZARD_SINGLE : HAZARD_MIX;
  const results = indexes.map((m) => {
    const findings = [...hazards.map((h) => hazardFinding(h, m)), ...rows.map((r) => finding(r, m))];
    const summary = scenario === "nocomp" ? {} : {
      components: single ? SUMMARY_SINGLE : SUMMARY_MIX,
      limitations: single || noTodo ? [] : limitationsFor(m),
    };
    return {
      msds_index: m,
      msds_revision_date: "2022-01-01",
      product_type: { value: single ? "단일물질" : "혼합물", basis: "가상" },
      summary: { 일치: 0, 불일치: 0, 경계: 0, 근거부족: 0, 경고: 0, 참고: 0, "범위 외": 0 },
      findings,
      traces: {},
      ...summary,
    };
  });
  const display: Record<string, unknown> = {};
  const explanations: Record<string, unknown> = {};
  for (const m of indexes) {
    for (const h of hazards) {
      display[hazardId(h, m)] = {
        msds: h.msds ?? (h.verdict === "일치" ? "기재" : "기재 없음"),
        expected: h.expected ?? (h.verdict === "근거부족" ? "판단 근거 없음" : "기재"),
        component: "제품",
        basis_lines: h.basis ?? [],
        calc_lines: h.calc ?? [],
        source_pages: h.pages ?? [],
      };
      if (needsExplanation(h.verdict)) {
        explanations[hazardId(h, m)] = writing
          ? { status: "작성 중" }
          : { status: "완료", by: h.by ?? "template", checked: true, summary: h.summary ?? "", reasons: [], basis: [] };
      }
    }
    for (const r of rows) {
      const fid = finding(r, m).id;
      display[fid] = {
        msds: r.msds,
        expected: version > 1 && r.key === "existing" ? "해당 (≥ 5%)" : r.expected,
        component: r.comp === null ? "제품" : single ? "가상물질 A (99.9 이상)" : COMPONENTS[r.comp].text,
        basis_lines: r.basis ?? [],
        calc_lines: [],
        source_pages: r.page ? [{ section: 15, page: r.page }] : [],
      };
      if (["불일치", "경계", "근거부족"].includes(r.verdict)) {
        explanations[fid] = writing
          ? { status: "작성 중" }
          : { status: "완료", by: r.by ?? "template", checked: true, summary: r.summary ?? "", reasons: [], basis: [] };
      }
    }
  }
  if (scenario === "bad") delete display[finding(TODO[0], 0).id];
  const seeded: Record<string, unknown> =
    scenario === "stale"
      ? { [finding(TODO[0], 0).id]: { status: "예외 승인", comment: "가상 사유", reviewer: "가상 검토자", at: "2026-11-03T09:00:00+09:00", history_count: 1, stale: true } }
      : {};
  return {
    job_id: id,
    version,
    is_latest: true,
    handoff_seq: version,
    judged_at: "2026-11-03T09:00:00+09:00",
    consistency: {
      contract: "consistency/2",
      doc_id: id,
      as_of: "2026-11-03",
      engine_version: "0.1.0",
      knowledge: { provider: "reference", version: "가상-2026.10", rules: "r0.3", logic: "가상" },
      results,
    },
    explanations,
    reviews: { ...seeded, ...Object.fromEntries(reviews) },
    field_status: [],
    display,
  };
}

const EXPLANATION_TOTAL = TODO.length + HAZARD_MIX.filter((h) => needsExplanation(h.verdict)).length;

function status(id: string, scenario: string) {
  const elapsed = elapsedMs(scenario);
  const base = { job_id: id, latest_version: 1, pending_handoff: null as number | null, explanations: { done: EXPLANATION_TOTAL, total: EXPLANATION_TOTAL }, saved_snapshot: null, error: null as string | null };
  if (scenario === "none") {
    if (!handedOff) return { ...base, state: "판정 없음", latest_version: null };
    return elapsed < 3_000 ? { ...base, state: "판정 중", latest_version: null } : { ...base, state: "판정 있음" };
  }
  if (scenario === "running") return elapsed < 5_000 ? { ...base, state: "판정 중", latest_version: null } : { ...base, state: "판정 있음" };
  if (scenario === "failed") return { ...base, state: "판정 실패", latest_version: null, error: "가상 오류: 성분 함량을 읽지 못했습니다" };
  if (scenario === "rerun") return elapsed < 6_000 ? { ...base, state: "판정 있음", pending_handoff: 2 } : { ...base, state: "판정 있음", latest_version: 2 };
  if (scenario === "writing") return { ...base, state: "판정 있음", explanations: { done: elapsed < 6_000 ? 0 : EXPLANATION_TOTAL, total: EXPLANATION_TOTAL } };
  return { ...base, state: "판정 있음" };
}

/* ── 이력 (contracts/5-api history_entry) ── */
const judgmentLog: unknown[] = [];

function valuesHistory(scenario: string) {
  if (scenario === "nofield") return [];
  if (scenario === "many") {
    return Array.from({ length: 250 }, (_, i) => ({
      at: new Date(Date.parse("2026-11-03T08:00:00+09:00") + i * 60_000).toISOString(),
      reviewer: "가상 검토자", area: "추출값", target: `3항 · 가상 칸 ${i + 1}`, action: "확인함", detail: null, comment: null, ref: { msds_index: 0, path: `components[${i}].cas_no` },
    }));
  }
  const rows: unknown[] = [
    { at: "2026-11-03T08:52:00+09:00", reviewer: "가상 검토자", area: "추출값", target: "3항 · 가상물질 A 함유량", action: "수정", detail: "93~98 → 95~98", comment: null, ref: { msds_index: 0, path: "components[0].content.raw" } },
    { at: "2026-11-03T08:41:00+09:00", reviewer: "가상 검토자", area: "추출값", target: "15항", action: "항 확인", detail: null, comment: null, ref: { msds_index: 0, path: "regulations" } },
  ];
  return scenario === "badlog" ? [{ ...(rows[0] as object), area: "모르는 구분" }] : rows;
}

function judgmentHistory(scenario: string) {
  if (scenario === "nofield" || scenario === "none" || scenario === "running") return [...judgmentLog];
  return [
    ...judgmentLog,
    { at: "2026-11-03T09:02:00+09:00", reviewer: "가상 검토자", area: "15항", target: "유독물질", action: "예외 승인", detail: "해당 → 해당 (≥ 10%)", comment: "공급사 확인 후 정정 요청 예정", ref: { finding_id: "m0/F15:0000-00-1:CCA.CCA_TOXIC" } },
    { at: "2026-11-03T08:58:00+09:00", reviewer: "다른 가상 검토자", area: "2항", target: "표시 요소", action: "불일치 확정", detail: null, comment: null, ref: { finding_id: "m0/F2L:SIGNAL" } },
  ];
}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** path 는 judgment.ts 가 만든 경로. 검토 요청은 요청 본문을 받아 상태에 쌓는다 */
export async function mockResponse(path: string, init?: RequestInit): Promise<unknown> {
  const scenario = mockScenario() ?? "ready";
  await wait(200);
  const id = decodeURIComponent((path.split("?")[0].split("/")[3]) ?? "");
  if (path.startsWith("/api/judgments/summary")) {
    const ids = (new URLSearchParams(path.split("?")[1]).get("job_ids") ?? "").split(",").filter(Boolean);
    return ids.map((jobId) => {
      const s = status(jobId, scenario);
      return { job_id: jobId, state: s.state, latest_version: s.latest_version, unreviewed: TODO.length,
               saved_snapshot: s.saved_snapshot, saved_at: null, data_grade: "실버" };
    });
  }
  if (path.endsWith("/to-judgment")) {
    handedOff = true;
    startedAt = Date.now();
    return { job_id: id, handoff_seq: 1 };
  }
  if (path.endsWith("/review/log")) {
    if (scenario === "nolog") throw new ApiRequestError(404, "http_404", "Not Found");
    if (scenario === "logfail") throw new ApiRequestError(500, "http_500", "가상 서버 오류");
    return valuesHistory(scenario);
  }
  if (path.endsWith("/history")) {
    if (scenario === "nohistory") throw new ApiRequestError(404, "http_404", "Not Found");
    return judgmentHistory(scenario);
  }
  if (path.endsWith("/status")) return status(id, scenario);
  if (path.endsWith("/reviews")) {
    await wait(300);
    if (scenario === "conflict") throw new ApiRequestError(409, "http_409", "보던 판정보다 새 판정이 있습니다");
    if (scenario === "savefail") throw new ApiRequestError(500, "http_500", "가상 서버 오류");
    const body = JSON.parse(String(init?.body)) as { finding_id: string; action: string; comment: string | null; reviewer: string };
    const prev = reviews.get(body.finding_id) as { status: string; comment: string | null } | undefined;
    judgmentLog.unshift({
      at: new Date().toISOString(),
      reviewer: body.reviewer,
      area: body.finding_id.includes("/F2") ? "2항" : "15항",
      target: rowsFor(scenario).find((r) => finding(r, 0).id === body.finding_id)?.label ?? HAZARD_MIX.find((h) => hazardId(h, 0) === body.finding_id)?.label ?? body.finding_id,
      action: body.action,
      detail: null,
      comment: body.comment,
      ref: { finding_id: body.finding_id },
    });
    if (body.action === "되돌리기") reviews.delete(body.finding_id);
    else {
      reviews.set(body.finding_id, {
        status: body.action === "의견" ? (prev?.status ?? "미검토") : body.action,
        comment: body.comment ?? prev?.comment ?? null,
        reviewer: body.reviewer,
        at: "2026-11-03T09:10:00+09:00",
        history_count: 1,
        stale: false,
      });
    }
    return { event_id: nextEvent++, job_id: id, finding_id: body.finding_id, action: body.action, comment: body.comment, reviewer: body.reviewer, at: "2026-11-03T09:10:00+09:00", version: 1, verdict_seen: "불일치" };
  }
  const version = new URLSearchParams(path.split("?")[1] ?? "").get("version");
  return view(id, Number(version) || status(id, scenario).latest_version || 1, scenario);
}
