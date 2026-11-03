/*
 * 성분별 요약 변환: 계약의 consistency.results[].components[] (성분별 판단 요약)를 화면 모델로 옮긴다.
 * 이름·CAS·함량·기준 분류(reference_classes)·사용 ATE(ate)·15항 해당 수(regulation_hits)·자료 신뢰도(reliability)·ATE 수집 순서 문장(notes)은
 * 서버 값을 그대로 쓴다. 이 파일이 직접 만드는 것은 아래 셋뿐이다.
 *  - 기준 분류 칩의 이름: 서버가 class_code 별 이름을 따로 주지 않아, 같은 판정 결과의 finding.label 을 찾아 쓴다 (없으면 class_code)
 *  - 표의 사용 ATE 한 줄: 서버의 ate[] 를 문장으로 잇는다
 *  - 판정으로 가는 연결: 이 성분이 들어간 판정(finding)의 번호
 */
import type { ComponentsResponse, ComponentSummary } from "../components-schemas";
import type { JudgmentView } from "../contract/api";
import type { Finding, ConsistencyComponent, MsdsResult } from "../contract/consistency";
import { PRODUCT_TYPE, screenVerdict } from "./maps";
import { resultOf } from "./findings";

const RELIABILITY = { 높음: "high", 보통: "medium", 낮음: "low" } as const;
const ROUTE = { oral: "경구", dermal: "경피", inhal: "흡입" } as const;

/** 서버 함량(Q)을 화면 함량 모양으로: 원문(raw)은 서버가 준 그대로 */
function concentration(q: ConsistencyComponent["content"]): ComponentSummary["concentration"] {
  if (!q) return { raw_text: "", min: null, max: null, operator: null, unit: null };
  const min = q.lower ?? q.value ?? null;
  const max = q.upper ?? q.value ?? null;
  return {
    raw_text: q.raw ?? "",
    min,
    max,
    operator: min !== null && max === null ? ">=" : min === null && max !== null ? "<=" : null,
    unit: q.unit ?? null,
  };
}

/** 사용 ATE 한 줄: "경구 제외(11항) · 흡입 0.375 mg/L 분진·미스트 (MSDS 11항, 3단계)" */
function usedAte(c: ConsistencyComponent, mixture: boolean): ComponentSummary["used_ate"] {
  if (!mixture) return { applicable: false, reason: "해당 없음 (단일물질은 계산하지 않음)" };
  const parts = c.ate.map((a) => {
    const route = ROUTE[a.route];
    if (a.excluded) return `${route} 제외${a.source ? `(${a.excluded})` : ` · ${a.excluded}`}${a.step ? ` (${a.step}단계)` : ""}`;
    const value = a.value !== null ? ` ${a.value}${a.unit ? ` ${a.unit}` : ""}${a.form ? ` ${a.form}` : ""}` : "";
    const origin = [a.source?.replace(/^MSDS\s*/, ""), a.step ? `${a.step}단계` : null].filter(Boolean).join(", ");
    return `${route}${value}${origin ? ` (${origin})` : ""}`;
  });
  return parts.length ? { applicable: true, reason: parts.join(" · ") } : { applicable: false, reason: "-" };
}

const isOfComp = (f: Finding, c: ConsistencyComponent) => f.comp?.comp_ref === c.comp_ref;

export function adaptComponents(view: JudgmentView): ComponentsResponse {
  const r: MsdsResult = resultOf(view);
  const productType = PRODUCT_TYPE[r.product_type.value];
  const mixture = productType === "mixture";
  const labelOf = (code: string) => r.findings.find((f) => f.kind === "class" && f.item === code)?.label ?? code;
  const findingById = new Map(r.findings.map((f) => [f.id, f]));

  const items: ComponentSummary[] = (productType === "unknown" ? [] : r.components).map((c, idx) => {
    const mine = r.findings.filter((f) => isOfComp(f, c));
    // 이 성분의 흡입 독성처럼 성분 없이 제품 단위로 나온 판정도, 계산 과정(trace)에 이 성분이 들어 있으면 이 성분의 판정으로 본다
    const viaTrace = r.findings.filter((f) => !f.comp && f.trace_id && r.traces[f.trace_id]?.inputs.some((i) => c.cas !== null && i.cas === c.cas));
    const related = [...mine, ...viaTrace];

    const legal = mine
      .filter((f) => (f.kind === "regulation" && f.expected.applicable === "해당") || (f.kind === "dangerous_goods" && !!f.expected.dg?.item))
      .map((f) => ({ finding_id: f.id, label: f.label }));
    const target = mixture ? viaTrace.filter((f) => f.kind === "class").slice(0, 1).map((f) => ({ section: 2 as const, finding_id: f.id })) : [];

    // 제약사항: 성분에 걸린 판정의 사유. 판정 없이 제품 전체에 걸린 사유는 첫 성분에 붙인다
    const limitations = r.limitations
      .filter((l) => {
        const f = l.finding_id ? findingById.get(l.finding_id) : undefined;
        return f?.comp ? isOfComp(f, c) : idx === 0;
      })
      .map((l) => {
        const f = l.finding_id ? findingById.get(l.finding_id) : undefined;
        const kind: "insufficient" | "borderline" = f && screenVerdict(f) === "borderline" ? "borderline" : "insufficient";
        return { kind, reason: l.text, finding_id: l.finding_id };
      });

    // 근거 쪽: 서버가 정한 쪽 중 성분표(3항)·독성(11항) 쪽을 쓴다. 없으면 이 성분에 걸린 판정의 쪽
    const pages = (sections: number[] | null) => {
      const seen = new Map<number, { section: number; page_no: number }>();
      for (const f of related) {
        for (const p of view.display[f.id]?.source_pages ?? []) {
          if (!sections || sections.includes(p.section)) seen.set(p.page, { section: p.section, page_no: p.page });
        }
      }
      return [...seen.values()].sort((a, b) => a.page_no - b.page_no);
    };
    const sourceRefs = pages([3, 11]).length ? pages([3, 11]) : pages(null);

    return {
      component_id: c.comp_ref,
      msds_id: `m${r.msds_index}`,
      name: c.name ?? c.cas ?? c.comp_ref,
      cas_no: c.cas,
      concentration: concentration(c.content),
      classifications: c.reference_classes.map((x) => ({
        source: x.source,
        name: labelOf(x.class_code),
        classification: x.category,
        version: null,
        basis: x.source,
      })),
      notes: c.notes,
      used_ate: usedAte(c, mixture),
      legal_findings: legal,
      // 15항 해당 수는 서버가 센 값(regulation_hits)을 그대로 보인다: legal_findings 는 연결용 목록이다
      regulation_hits: c.regulation_hits,
      // 자료 신뢰도는 서버 값. 사유는 서버가 따로 주지 않아 ATE 수집 순서 문장(notes)을 쓴다
      confidence: { level: RELIABILITY[c.reliability], reason: c.notes.join(" · ") },
      limitations,
      target_links: target,
      source_refs: sourceRefs,
    };
  });

  return {
    msds_id: `m${r.msds_index}`,
    product_type: productType,
    items,
    selected_component_id: items[0]?.component_id ?? null,
    limitations: [],
    confidence_rule_version: null,
  };
}
