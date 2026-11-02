/*
 * 2항·15항 판정 화면용 고정 데이터 (개발용): 25번 황산 KZ-A-S004.
 * 문서 번호가 "demo" 일 때만 findings.ts 가 이 값을 돌려준다.
 */
import { DEMO_VALIDATION_ID } from "@/lib/demo";
import { ApiRequestError } from "./client";
import { PRODUCT_GROUP_ID, type FindingDetail, type FindingsResponse, type FindingSummary, type SourceRef, type Verdict } from "./findings-schemas";

const EXTRACTION_ID = "ext_demo";
const MSDS_ID = "msds_a";

const ref = (page_no: number): SourceRef => ({ page_no, bbox: null, input_path: `pages/${page_no}.png` });

type Row = {
  item: string;
  msds: string;
  expected: string;
  method: string;
  verdict: Verdict;
  severity: FindingSummary["severity"];
  /** 2항 p.4 처럼 근거로 보여 줄 쪽 */
  pages: number[];
  rule: { id: string; version: string };
  inputs: string[];
  thresholds?: string[];
  explanation?: string;
};

const ROWS: Row[] = [
  {
    item: "급성 독성(흡입)",
    msds: "구분2 (증기)",
    expected: "구분2 (분진·미스트)",
    method: "ATEmix 계산",
    verdict: "mismatch",
    severity: "medium",
    pages: [4, 9],
    rule: { id: "ATE-INHAL-MIST", version: "1" },
    inputs: [
      "황산 93~98% · 0.375 mg/L (미스트) · 11항 3단계",
      "물 2~7% · 무독성 제외 · 5단계",
      "상한 98%: 100 / (98 / 0.375) = 0.383",
      "하한 93%: 100 / (93 / 0.375) = 0.403",
      "→ 분진·미스트 구분2 (확정)",
    ],
    thresholds: ["0.05 < ATEmix ≤ 0.5 → 구분2"],
    explanation:
      '주성분 황산의 흡입 독성값은 미스트(LC50 0.375 mg/L)입니다. 계산한 ATEmix 0.383~0.403 mg/L는 미스트 구분2 범위인데, MSDS 2항은 "증기" 구분2로 적었습니다. 11항도 증기 범위로 기재했습니다.',
  },
  {
    item: "금속부식성",
    msds: "구분1",
    expected: "— (제품 시험자료 없음)",
    method: "9항 시험값",
    verdict: "insufficient_evidence",
    severity: null,
    pages: [4],
    rule: { id: "METAL-CORR-TEST", version: "1" },
    inputs: ["9항 시험값: 제품 시험자료 없음"],
    explanation: "혼합물 시험자료가 없어 판정할 수 없습니다. 판정을 빼지 않고 근거부족으로 표시해 검토자에게 넘깁니다.",
  },
  {
    item: "만성 수생환경",
    msds: "구분3",
    expected: "— (기준정보 없음)",
    method: "M-factor 가산",
    verdict: "insufficient_evidence",
    severity: null,
    pages: [4],
    rule: { id: "AQUATIC-CHRONIC-SUM", version: "1" },
    inputs: ["황산: 기준정보에 수생 분류 없음", "물: 기준정보에 수생 분류 없음"],
    explanation: "황산과 물 모두 기준정보에 수생 분류가 없어, MSDS 구분3의 근거를 확인해야 합니다.",
  },
  {
    item: "표시 요소",
    msds: "H318 기재",
    expected: "H314와 중복",
    method: "별표2 매핑",
    verdict: "warning",
    severity: "low",
    pages: [4],
    rule: { id: "LABEL-H-DUP", version: "1" },
    inputs: ["피부 부식성/자극성 구분1 → H314", "심한 눈 손상성/자극성 구분1 → H318", "MSDS 2항: H314, H318 모두 기재"],
    explanation:
      "피부 부식성 구분1이면 H314가 나오고, 이때 눈 손상 H318은 함께 적지 않습니다. MSDS는 둘 다 적어 중복입니다.",
  },
  {
    item: "급성 독성(경구)",
    msds: "미기재",
    expected: "분류안됨 (ATEmix > 2,000)",
    method: "ATEmix 계산",
    verdict: "match",
    severity: null,
    pages: [],
    rule: { id: "ATE-ORAL", version: "1" },
    inputs: ["MSDS 2항: 미기재", "기준: 분류안됨 (ATEmix > 2,000)"],
  },
  {
    item: "피부 부식성/자극성",
    msds: "구분1",
    expected: "구분1",
    method: "가산 (Σ구분1 ≥ 5%)",
    verdict: "match",
    severity: null,
    pages: [],
    rule: { id: "SKIN-CORR-SUM", version: "1" },
    inputs: ["MSDS 2항: 구분1", "기준: 구분1"],
  },
  {
    item: "심한 눈 손상성/자극성",
    msds: "구분1",
    expected: "구분1",
    method: "가산 (≥ 3%)",
    verdict: "match",
    severity: null,
    pages: [],
    rule: { id: "EYE-DAMAGE-SUM", version: "1" },
    inputs: ["MSDS 2항: 구분1", "기준: 구분1"],
  },
  {
    item: "발암성",
    msds: "구분1A",
    expected: "구분1A",
    method: "한계농도 0.1%",
    verdict: "match",
    severity: null,
    pages: [],
    rule: { id: "CARC-LIMIT", version: "1" },
    inputs: ["MSDS 2항: 구분1A", "기준: 구분1A"],
  },
  {
    item: "특정표적장기(1회)",
    msds: "구분1",
    expected: "구분1",
    method: "한계농도 10%",
    verdict: "match",
    severity: null,
    pages: [],
    rule: { id: "STOT-SE-LIMIT", version: "1" },
    inputs: ["MSDS 2항: 구분1", "기준: 구분1"],
  },
];

const idOf = (n: number) => `fnd_demo_${n + 1}`;

const toSummary = (r: Row, n: number): FindingSummary => ({
  finding_id: idOf(n),
  validation_id: DEMO_VALIDATION_ID,
  msds_id: MSDS_ID,
  section: 2,
  item: r.item,
  law: null,
  component_id: null,
  msds_value: { text: r.msds },
  expected_value: { text: r.expected },
  method: r.method,
  verdict: r.verdict,
  severity: r.severity,
  review_state: "unreviewed",
  opinion_count: 0,
  trace_id: `trc_demo_${n + 1}`,
  source_refs: r.pages.map(ref),
});

const SUMMARIES = ROWS.map(toSummary);

const toDetail = (r: Row, n: number): FindingDetail => ({
  finding: SUMMARIES[n],
  explanation: r.explanation
    ? { text: r.explanation, source: "template", check_status: "passed", limitations: [] }
    : { text: "", source: "unavailable", check_status: "not_checked", limitations: [] },
  trace: {
    trace_id: SUMMARIES[n].trace_id,
    rule: r.rule,
    inputs: r.inputs,
    thresholds: r.thresholds ?? [],
    assumptions: [],
  },
  evidence: SUMMARIES[n].source_refs,
  review: { state: "unreviewed", opinions: [] },
  law_effective_date: null,
  msds_revision_date: null,
  reference_date: "2026-11-02",
});

const DETAILS = ROWS.map(toDetail);

const DEMO_FINDINGS: FindingsResponse = {
  validation_id: DEMO_VALIDATION_ID,
  extraction_id: EXTRACTION_ID,
  review_revision: 1,
  items: SUMMARIES,
  page: 1,
  page_size: 20,
  total: SUMMARIES.length,
  counts: { mismatch: 1, borderline: 0, insufficient_evidence: 2, warning: 1, match: 5, outdated: 0 },
  excluded_counts: { not_applicable: 0, excluded: 0 },
  groups: [],
};

/* ── 15항 법적 규제 ─────────────────────────────────────── */

const COMP_H2SO4 = "comp_h2so4";
type Row15 = {
  law: string;
  item: string;
  msds: string;
  expected: string;
  verdict: Verdict;
  severity: FindingSummary["severity"];
  component_id: string | null;
  inputs: string[];
  explanation?: string;
  law_effective_date?: string;
};

const METHOD_15 = "규제DB 조회 (as_of 기준)";

const ROWS_15: Row15[] = [
  {
    law: "화관법",
    item: "유독물질",
    msds: "해당 (10% 이상)",
    expected: "개정 법령의 세분 표기 필요 · 시행일 2025-01-01",
    verdict: "outdated",
    severity: "medium",
    component_id: COMP_H2SO4,
    inputs: ["황산 93~98% ≥ 10% → 해당", "규제DB 개정 시행일: 2025-01-01", "→ 구버전 (개정 전 표기 기준 판정)"],
    explanation:
      "화관법 유독물질 고시가 2025-01-01에 개정되어 세분 표기가 필요합니다. MSDS 15항은 개정 전 표기로, 구버전 기준 판정입니다.",
    law_effective_date: "2025-01-01",
  },
  { law: "산안법", item: "작업환경측정 대상", msds: "해당 (1% 이상)", expected: "해당 (≥ 1%)", verdict: "match", severity: null, component_id: COMP_H2SO4, inputs: ["황산 93~98% ≥ 1% → 해당"] },
  { law: "산안법", item: "특수건강진단 대상", msds: "해당 (1% 이상)", expected: "해당 (≥ 1%)", verdict: "match", severity: null, component_id: COMP_H2SO4, inputs: ["황산 93~98% ≥ 1% → 해당"] },
  { law: "산안법", item: "공정안전보고서 대상", msds: "해당 (20% 이상)", expected: "해당 (≥ 20%)", verdict: "match", severity: null, component_id: COMP_H2SO4, inputs: ["황산 93~98% ≥ 20% → 해당"] },
  { law: "산안법", item: "허용기준 설정물질", msds: "해당", expected: "해당", verdict: "match", severity: null, component_id: COMP_H2SO4, inputs: ["황산: 허용기준 설정물질 → 해당"] },
  { law: "화관법", item: "사고대비물질", msds: "해당 (10% 이상)", expected: "해당 (≥ 10%)", verdict: "match", severity: null, component_id: COMP_H2SO4, inputs: ["황산 93~98% ≥ 10% → 해당"] },
  { law: "화관법", item: "배출량조사 대상", msds: "해당 (1% 이상)", expected: "해당 (≥ 1%)", verdict: "match", severity: null, component_id: COMP_H2SO4, inputs: ["황산 93~98% ≥ 1% → 해당"] },
  { law: "화평법", item: "등록대상기존화학물질", msds: "해당", expected: "해당", verdict: "match", severity: null, component_id: COMP_H2SO4, inputs: ["황산: 등록대상기존화학물질 → 해당"] },
  { law: "위험물법", item: "위험물", msds: "해당없음", expected: "비해당 (인화점 없음)", verdict: "match", severity: null, component_id: null, inputs: ["제품: 인화점 없음 → 비해당"] },
];

const SUMMARIES_15: FindingSummary[] = ROWS_15.map((r, n) => ({
  finding_id: `fnd_demo_15_${n + 1}`,
  validation_id: DEMO_VALIDATION_ID,
  msds_id: MSDS_ID,
  section: 15,
  item: r.item,
  law: r.law,
  component_id: r.component_id,
  msds_value: { text: r.msds },
  expected_value: { text: r.expected },
  method: METHOD_15,
  verdict: r.verdict,
  severity: r.severity,
  review_state: "unreviewed",
  opinion_count: 0,
  trace_id: `trc_demo_15_${n + 1}`,
  source_refs: [ref(12)],
}));

const DETAILS_15: FindingDetail[] = ROWS_15.map((r, n) => ({
  finding: SUMMARIES_15[n],
  explanation: r.explanation
    ? { text: r.explanation, source: "template", check_status: "passed", limitations: [] }
    : { text: "", source: "unavailable", check_status: "not_checked", limitations: [] },
  trace: {
    trace_id: SUMMARIES_15[n].trace_id,
    rule: { id: "REG-DB-LOOKUP", version: "1" },
    inputs: r.inputs,
    thresholds: [],
    assumptions: [],
  },
  evidence: SUMMARIES_15[n].source_refs,
  review: { state: "unreviewed", opinions: [] },
  law_effective_date: r.law_effective_date ?? null,
  msds_revision_date: null,
  reference_date: "2026-11-02",
}));

export const DEMO_FINDINGS_15: FindingsResponse = {
  validation_id: DEMO_VALIDATION_ID,
  extraction_id: EXTRACTION_ID,
  review_revision: 1,
  items: SUMMARIES_15,
  page: 1,
  page_size: 20,
  total: SUMMARIES_15.length,
  counts: { outdated: 1, match: 8, mismatch: 0, borderline: 0, insufficient_evidence: 0, warning: 0 },
  excluded_counts: { not_applicable: 0, excluded: 0 },
  groups: [
    { component_id: COMP_H2SO4, title: "황산 (93~98%)", total: 8, matching_count: 7 },
    { component_id: PRODUCT_GROUP_ID, title: "제품", total: 1, matching_count: 1 },
  ],
};

/** 없는 번호면 null */
const demoFindingDetail = (findingId: string): FindingDetail | null =>
  [...DETAILS, ...DETAILS_15].find((d) => d.finding.finding_id === findingId) ?? null;

/* ── findings.ts 가 demo 문서에서 부르는 진입점 ─────────────── */

type DemoParams = { verdict?: Verdict; section?: 2 | 15 };

/** 항(section)에 맞는 고정 응답. 항을 안 정하면 2항과 15항을 합친다 (counts 는 합산) */
function demoBase(section?: 2 | 15): FindingsResponse {
  if (section === 2) return DEMO_FINDINGS;
  if (section === 15) return DEMO_FINDINGS_15;
  const counts = { ...DEMO_FINDINGS.counts };
  for (const [k, n] of Object.entries(DEMO_FINDINGS_15.counts)) counts[k] = (counts[k] ?? 0) + n;
  const items = [...DEMO_FINDINGS.items, ...DEMO_FINDINGS_15.items];
  return { ...DEMO_FINDINGS, items, total: items.length, counts, groups: [...DEMO_FINDINGS.groups, ...DEMO_FINDINGS_15.groups] };
}

/** 걸러진 목록. total 은 거른 개수다 (counts·groups 는 항 기준 전체, 거르기 전 그대로) */
export function demoFindingsResponse(params: DemoParams): FindingsResponse {
  const base = demoBase(params.section);
  const items = base.items.filter((f) => !params.verdict || f.verdict === params.verdict);
  return { ...base, items, total: items.length };
}

/** 없는 번호면 404 */
export function demoFindingDetailOrThrow(findingId: string): FindingDetail {
  const detail = demoFindingDetail(findingId);
  if (!detail) throw new ApiRequestError(404, "http_404", "판정을 찾을 수 없습니다.");
  return detail;
}
