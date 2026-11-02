/*
 * 2항 판정 화면용 고정 데이터 (개발용): 25번 황산 KZ-A-S004.
 * 문서 번호가 "demo" 일 때만 findings.ts 가 이 값을 돌려준다.
 */
import type { FindingDetail, FindingsResponse, FindingSummary, SourceRef, Verdict } from "./findings-schemas";

export const DEMO_VALIDATION_ID = "val_demo";

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
    verdict: "insufficient",
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
    verdict: "insufficient",
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

export const DEMO_FINDINGS: FindingsResponse = {
  validation_id: DEMO_VALIDATION_ID,
  extraction_id: EXTRACTION_ID,
  review_revision: 1,
  items: SUMMARIES,
  page: 1,
  page_size: 20,
  total: SUMMARIES.length,
  counts: { mismatch: 1, borderline: 0, insufficient: 2, warning: 1, match: 5, outdated: 0 },
  excluded_counts: { not_applicable: 0, excluded: 0 },
  groups: [],
};

/** 없는 번호면 null */
export const demoFindingDetail = (findingId: string): FindingDetail | null =>
  DETAILS.find((d) => d.finding.finding_id === findingId) ?? null;
