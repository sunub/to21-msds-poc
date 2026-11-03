/*
 * 판정 변환 계층: 계약의 judgment_view → 판정 화면이 쓰는 모델(FindingsResponse, FindingDetail).
 * 항목 이름(label)·법령(law_label)·판정 방법(method)·표시 문장(display.msds·expected·basis_lines·calc_lines·source_pages)은
 * 서버가 준 값을 그대로 쓴다. 여기서는 모양만 옮긴다.
 * 한 PDF에 MSDS 가 여러 건이면 첫 건(results[0])만 보여 준다.
 */
import { ApiRequestError } from "../client";
import type { JudgmentView } from "../contract/api";
import type { Finding, MsdsResult } from "../contract/consistency";
import type { FindingDetail, FindingsResponse, FindingSummary, SourceRef, Verdict } from "../findings-schemas";
import { PRODUCT_GROUP_ID } from "../findings-schemas";
import { screenReview, screenSeverity, screenVerdict } from "./maps";

export type FindingsParams = { verdict?: Verdict; section?: 2 | 15 };

/** 화면이 보여 주는 판정 (단일·혼합 판별은 판정 표의 행이 아니라 성분 요약의 제품 유형으로만 쓴다) */
const shown = (f: Finding) => f.kind !== "product_type";

export const resultOf = (view: JudgmentView): MsdsResult => view.consistency.results[0];

/** 원문 근거: 서버가 정한 쪽 목록 (첫 번째가 기본으로 열린다). 이름은 "2항"처럼 항 번호 */
function sourceRefs(view: JudgmentView, f: Finding): SourceRef[] {
  return (view.display[f.id]?.source_pages ?? []).map((p) => ({ page_no: p.page, bbox: null, input_path: `${p.section}항` }));
}

function toSummary(view: JudgmentView, r: MsdsResult, f: Finding): FindingSummary {
  const review = screenReview(view.reviews[f.id]);
  const d = view.display[f.id];
  return {
    finding_id: f.id,
    validation_id: String(view.version),
    msds_id: `m${r.msds_index}`,
    section: f.section === "2" ? 2 : 15,
    item: f.label,
    law: f.law_label,
    component_id: f.comp?.comp_ref ?? null,
    msds_value: { text: d?.msds ?? "-" },
    expected_value: { text: d?.expected ?? "-" },
    method: f.method,
    verdict: screenVerdict(f),
    severity: screenSeverity(f.severity),
    review_state: review.state,
    opinion_count: review.historyCount,
    review_stale: review.stale,
    review_event_id: review.lastEventId,
    trace_id: f.trace_id ?? "",
    source_refs: sourceRefs(view, f),
  };
}

/** 성분 묶음 머리줄 이름: 서버가 준 "황산 (93~98)" */
function groupTitle(view: JudgmentView, r: MsdsResult, compRef: string) {
  const mine = r.findings.filter((x) => x.comp?.comp_ref === compRef);
  const withComponent = mine.map((x) => view.display[x.id]?.component).find((t) => t && t !== "제품");
  return withComponent ?? mine[0]?.comp?.name ?? compRef;
}

/** 판정 목록. section 을 정하면 그 항만, verdict 를 정하면 그 판정만 (counts·groups 는 거르기 전 항 기준) */
export function adaptFindings(view: JudgmentView, params: FindingsParams = {}): FindingsResponse {
  const r = resultOf(view);
  const all = r.findings.filter(shown).map((f) => toSummary(view, r, f));
  const bySection = all.filter((f) => !params.section || f.section === params.section);
  const items = bySection.filter((f) => !params.verdict || f.verdict === params.verdict);

  const counts: Record<string, number> = {};
  for (const f of bySection) counts[f.verdict] = (counts[f.verdict] ?? 0) + 1;

  const groupIds = [...new Set(bySection.map((f) => f.component_id ?? PRODUCT_GROUP_ID))];
  const groups = groupIds
    .sort((a, b) => (a === PRODUCT_GROUP_ID ? 1 : b === PRODUCT_GROUP_ID ? -1 : a.localeCompare(b, "en", { numeric: true })))
    .map((id) => {
      const inGroup = bySection.filter((f) => (f.component_id ?? PRODUCT_GROUP_ID) === id);
      return {
        component_id: id,
        title: id === PRODUCT_GROUP_ID ? "제품" : groupTitle(view, r, id),
        total: inGroup.length,
        matching_count: inGroup.filter((f) => f.verdict === "match").length,
      };
    });

  return {
    validation_id: String(view.version),
    extraction_id: `h${view.handoff_seq}`,
    review_revision: view.version,
    items,
    page: 1,
    page_size: Math.max(20, items.length),
    total: items.length,
    counts,
    excluded_counts: { not_applicable: counts.not_applicable ?? 0, excluded: counts.excluded ?? 0 },
    groups,
  };
}

/** 근거 칸들의 사람 검수 상태: 수정된 칸이 있으면 수정됨, 모두 확인했으면 확인함, 아니면 미검수 */
function evidenceStatus(view: JudgmentView, r: MsdsResult, f: Finding): FindingDetail["evidence_status"] {
  const fields = [...new Set([...(f.msds.evidence ?? []), ...(f.expected.evidence ?? [])].map((e) => e.field))];
  if (fields.length === 0) return null;
  const status = fields.map((field) => view.field_status.find((s) => s.msds_index === r.msds_index && s.field === field)?.status);
  if (status.some((s) => s === "수정됨")) return "수정됨";
  return status.every((s) => s === "확인함") ? "확인함" : "미검수";
}

function explanationOf(view: JudgmentView, f: Finding): FindingDetail["explanation"] {
  const e = view.explanations[f.id];
  if (!e) return { text: "", status: "none", reasons: [], source: "unavailable", check_status: "not_checked", limitations: [] };
  if (e.status === "작성 중") {
    return { text: "", status: "writing", reasons: [], source: "unavailable", check_status: "not_checked", limitations: [] };
  }
  return {
    text: e.summary,
    status: "done",
    reasons: e.reasons,
    source: e.by === "llm" ? "ai" : "template",
    check_status: e.checked ? "passed" : "failed",
    limitations: [],
  };
}

/** 판정 한 건의 상세. 없는 번호면 404 */
export function adaptDetail(view: JudgmentView, findingId: string): FindingDetail {
  const r = resultOf(view);
  const f = r.findings.find((x) => x.id === findingId);
  if (!f) throw new ApiRequestError(404, "http_404", "판정을 찾을 수 없습니다.");
  const summary = toSummary(view, r, f);
  const d = view.display[f.id];
  const t = f.trace_id ? r.traces[f.trace_id] : undefined;
  const calcLines = d?.calc_lines ?? [];
  const thresholds = (t?.thresholds ?? []).map((x) => `${String(x.category ?? "")}: ${String(x.range ?? "")}`);
  const assumptions = (t?.assumptions ?? []).map((x) => `${x.id} ${x.text}`);
  const review = screenReview(view.reviews[f.id]);
  return {
    finding: summary,
    explanation: explanationOf(view, f),
    // 판단 근거(basis_lines)와 계산 과정(calc_lines)은 서버가 준 줄 그대로
    basis_lines: d?.basis_lines ?? [],
    trace:
      t && (calcLines.length > 0 || thresholds.length > 0 || assumptions.length > 0)
        ? { trace_id: f.trace_id ?? "", rule: { id: t.rule.id, version: t.knowledge_version }, inputs: calcLines, thresholds, assumptions }
        : null,
    evidence: summary.source_refs,
    review: { state: review.state, opinions: review.opinion ? [review.opinion] : [] },
    evidence_status: evidenceStatus(view, r, f),
    // 규제 시행일(구버전 판정에 보인다). PoC 에서는 비어 있을 수 있다
    law_effective_date: f.expected.effective_from ?? null,
    msds_revision_date: r.msds_revision_date,
    reference_date: view.consistency.as_of,
  };
}
