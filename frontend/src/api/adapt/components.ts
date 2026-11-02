/*
 * 성분별 요약 변환: 계약에는 성분 요약 API 가 없어, judgment_view 의 findings + traces + product_type + limitations 에서 만든다.
 *
 * 만들 수 없는 칸 (계약에 값이 없다):
 *  - 자료 신뢰도(confidence): 항상 null → 화면은 "미확인"으로 보인다. 신뢰도에서 나오는 제약사항 카드도 없다.
 *  - 성분 단위 분류가 없는 성분(예: 물)의 기준 분류: 빈 목록 → 표에 "—"
 *  - 분류 출처별 비교는 expected.source 를 쉼표로 나눈 값만 안다 (출처마다 분류가 다른지는 알 수 없다)
 *  - 성분이 trace 입력에만 있고 판정(finding)이 없으면 CAS·이름·함량·ATE 만 있다
 *  - confidence_rule_version: null
 */
import { formatQ } from "@/lib/format-judgment";
import type { ComponentsResponse, ComponentSummary } from "../components-schemas";
import type { JudgmentView } from "../contract/api";
import type { Finding, MsdsResult, Trace } from "../contract/consistency";
import { classCode } from "../contract/common";
import { ACUTE_ROUTE, ATE_STEP_LABELS, CLASS_SHORT, itemName, lawName } from "./labels";
import { PRODUCT_TYPE, screenVerdict } from "./maps";
import { resultOf } from "./findings";

type Comp = { key: string; cas: string | null; name: string; compRef: string | null };

const compKey = (cas: string | null | undefined, name: string | null | undefined) => cas ?? `name:${name ?? ""}`;

/** 판정 항목과 trace 입력에 나온 성분을 모은다 (처음 나온 순서) */
function collectComps(r: MsdsResult): Comp[] {
  const comps = new Map<string, Comp>();
  const add = (cas: string | null, name: string | null, compRef: string | null) => {
    const key = compKey(cas, name);
    const prev = comps.get(key);
    if (prev) {
      if (!prev.compRef && compRef) prev.compRef = compRef;
      return;
    }
    comps.set(key, { key, cas, name: name ?? cas ?? "이름 없음", compRef });
  };
  for (const f of r.findings) if (f.comp) add(f.comp.cas, f.comp.name, f.comp.comp_ref);
  for (const t of Object.values(r.traces)) for (const i of t.inputs) if (i.cas || i.name) add(i.cas, i.name, null);
  return [...comps.values()];
}

const isComp = (f: Finding, c: Comp) => !!f.comp && compKey(f.comp.cas, f.comp.name) === c.key;
const traceOf = (r: MsdsResult, f: Finding): Trace | undefined => (f.trace_id ? r.traces[f.trace_id] : undefined);

function concentration(r: MsdsResult, c: Comp): ComponentSummary["concentration"] {
  for (const t of Object.values(r.traces)) {
    const i = t.inputs.find((x) => compKey(x.cas, x.name) === c.key && x.content);
    if (i?.content) {
      const { low, high } = i.content;
      const lo = low ?? null;
      const hi = high ?? null;
      const raw = lo !== null && hi !== null ? (lo === hi ? `${lo}` : `${lo}~${hi}`) : `${lo ?? hi ?? ""}`;
      return {
        raw_text: raw,
        min: lo,
        max: hi,
        operator: lo !== null && hi === null ? ">=" : lo === null && hi !== null ? "<=" : null,
        unit: "%",
      };
    }
  }
  const q = r.findings.find((f) => isComp(f, c) && (f.msds.content || f.expected.content));
  const content = q?.msds.content ?? q?.expected.content;
  if (content) {
    const lo = content.lower ?? content.value ?? null;
    const hi = content.upper ?? content.value ?? null;
    return {
      raw_text: content.raw ?? formatQ(content),
      min: lo,
      max: hi,
      operator: lo !== null && hi === null ? ">=" : lo === null && hi !== null ? "<=" : null,
      unit: content.unit ?? null,
    };
  }
  return { raw_text: "", min: null, max: null, operator: null, unit: null };
}

/** 기준 분류: 성분 단위 분류 판정(class)의 검증 결과. 출처는 expected.source 를 쉼표로 나눈다 */
function classifications(r: MsdsResult, c: Comp, basis: string): ComponentSummary["classifications"] {
  const out: ComponentSummary["classifications"] = [];
  // 계약 class_code 순서로 보인다 (피부 → 눈 → 발암성 → 표적장기)
  const order = (f: Finding) => classCode.options.indexOf(f.item as (typeof classCode.options)[number]);
  for (const f of [...r.findings].sort((a, b) => order(a) - order(b))) {
    if (f.kind !== "class" || !isComp(f, c) || !f.expected.present) continue;
    const name = CLASS_SHORT[f.item] ?? itemName(f);
    const sources = (f.expected.source ?? "").split(",").map((s) => s.trim()).filter(Boolean);
    for (const source of sources.length ? sources : [basis]) {
      out.push({ source, name, classification: f.expected.category ?? "", version: null, basis });
    }
  }
  return out;
}

const ACUTE = ["HH_ACUTE_ORAL", "HH_ACUTE_DERMAL", "HH_ACUTE_INHAL"];

/** 급성 독성 trace 에서 이 성분의 입력을 찾는다 */
function acuteInput(r: MsdsResult, c: Comp, classCode: string) {
  const f = r.findings.find((x) => x.kind === "class" && x.item === classCode);
  const t = f && traceOf(r, f);
  const input = t?.inputs.find((i) => compKey(i.cas, i.name) === c.key);
  return { f, t, input };
}

/** 흡입 ATE 를 가져온 6단계: 채택한 단계 앞은 "없음", 뒤는 "해당 없음" */
function ateSteps(r: MsdsResult, c: Comp): ComponentSummary["ate_steps"] {
  const { input } = acuteInput(r, c, "HH_ACUTE_INHAL");
  if (!input) return [];
  const adoptedStep = input.step ?? null;
  return ATE_STEP_LABELS.map((label, i) => {
    const step = i + 1;
    const adopted = adoptedStep === step;
    const value = adopted ? (input.ate_used ?? null) : null;
    return {
      step,
      label,
      input: adopted ? (input.excluded ?? [input.value?.form, input.value?.hours ? `${input.value.hours}hr` : null].filter(Boolean).join(", ")) || null : null,
      adopted,
      value,
      unit: adopted && value !== null ? (input.value?.unit ?? null) : null,
      excluded_reason: adopted ? null : adoptedStep !== null && step < adoptedStep ? "없음" : "해당 없음",
    };
  });
}

/** 표의 "사용 ATE (단계)" 한 줄 */
function usedAte(r: MsdsResult, c: Comp, mixture: boolean): ComponentSummary["used_ate"] {
  if (!mixture) return { applicable: false, reason: "해당 없음 (단일물질은 계산하지 않음)" };
  const parts: string[] = [];
  let step: number | null = null;
  let value: number | null = null;
  let unit: string | null = null;
  for (const code of ACUTE) {
    const { input } = acuteInput(r, c, code);
    if (!input) continue;
    const route = ACUTE_ROUTE[code];
    if (input.ate_used != null) {
      const v = input.value;
      parts.push(`${route} ${input.ate_used}${v?.unit ? ` ${v.unit}` : ""}${v?.form ? ` ${v.form}` : ""} (${[input.source?.replace(/^MSDS\s*/, ""), input.step ? `${input.step}단계` : null].filter(Boolean).join(", ")})`);
      if (code === "HH_ACUTE_INHAL") {
        step = input.step ?? null;
        value = input.ate_used;
        unit = v?.unit ?? null;
      }
    } else if (input.excluded) {
      parts.push(code === "HH_ACUTE_ORAL" ? `${route} 제외(${input.excluded})` : `${input.excluded}${input.step ? ` (${input.step}단계)` : ""}`);
      if (code === "HH_ACUTE_INHAL") step = input.step ?? null;
    }
  }
  if (parts.length === 0) return { applicable: false, reason: "해당 없음" };
  return { applicable: true, reason: parts.join(" · "), value, unit, step };
}

/** 근거에 나온 쪽 (칸 경로의 앞부분으로 항을 짐작한다: components → 3항, toxicity → 11항 …) */
function sourceRefs(r: MsdsResult, c: Comp): ComponentSummary["source_refs"] {
  const sectionOf = (field: string) =>
    field.startsWith("components") ? 3 : field.startsWith("tox") ? 11 : field.startsWith("hazard") ? 2 : field.startsWith("reg") ? 15 : 0;
  const refs = new Map<string, { section: number; page_no: number }>();
  const addFrom = (f: Finding, all: boolean) => {
    for (const e of [...(f.msds.evidence ?? []), ...(f.expected.evidence ?? [])]) {
      const section = sectionOf(e.field);
      // 성분의 근거는 성분표(3항)와 독성 정보(11항) 쪽. 그 밖의 쪽은 아래 대체 경로에서만 쓴다
      if (e.page !== null && (all || section === 3 || section === 11)) refs.set(`${e.page}`, { section, page_no: e.page });
    }
  };
  // 이 성분에 걸린 판정, 그리고 계산 과정(trace)의 입력에 이 성분이 들어간 판정 (예: 혼합물 급성 독성)
  const mine = (f: Finding) => isComp(f, c) || !!traceOf(r, f)?.inputs.some((i) => compKey(i.cas, i.name) === c.key);
  for (const f of r.findings) if (mine(f)) addFrom(f, false);
  // 3·11항 쪽이 없으면 이 성분에 걸린 판정의 근거 쪽을 쓴다
  if (refs.size === 0) for (const f of r.findings) if (isComp(f, c)) addFrom(f, true);
  // 판정이 없는 성분은 성분표(3항) 쪽을 같이 쓴다
  if (refs.size === 0) for (const f of r.findings) addFrom(f, false);
  return [...refs.values()].sort((a, b) => a.page_no - b.page_no);
}

export function adaptComponents(view: JudgmentView): ComponentsResponse {
  const r = resultOf(view);
  const productType = PRODUCT_TYPE[r.product_type.value];
  const mixture = productType === "mixture";
  const basis = view.consistency.knowledge.provider === "to21" ? "TO21 분류기준" : `기준정보 ${view.consistency.knowledge.version}`;

  const comps = productType === "unknown" ? [] : collectComps(r);
  const findingById = new Map(r.findings.map((f) => [f.id, f]));

  const items: ComponentSummary[] = comps.map((c, idx) => {
    const mine = r.findings.filter((f) => isComp(f, c));
    const legal = mine
      .filter((f) => (f.kind === "regulation" && f.expected.applicable === "해당") || (f.kind === "dangerous_goods" && !!f.expected.dg?.item))
      .map((f) => ({ finding_id: f.id, label: `${lawName(f) ?? ""} ${itemName(f)}`.trim() }));
    const inhal = r.findings.find((f) => f.kind === "class" && f.item === "HH_ACUTE_INHAL");
    const target = mixture && inhal && acuteInput(r, c, "HH_ACUTE_INHAL").input ? [{ section: 2 as const, finding_id: inhal.id }] : [];

    // 제약사항: 성분에 걸린 판정의 사유. 판정 없이 제품 전체에 걸린 사유는 첫 성분에 붙인다
    const limitations = r.limitations
      .filter((l) => {
        const f = l.finding_id ? findingById.get(l.finding_id) : undefined;
        return f?.comp ? isComp(f, c) : idx === 0;
      })
      .map((l) => {
        const f = l.finding_id ? findingById.get(l.finding_id) : undefined;
        const kind: "insufficient" | "borderline" = f && screenVerdict(f) === "borderline" ? "borderline" : "insufficient";
        return { kind, reason: l.text, finding_id: l.finding_id };
      });

    return {
      component_id: c.key,
      msds_id: `m${r.msds_index}`,
      name: c.name,
      cas_no: c.cas,
      concentration: concentration(r, c),
      classifications: classifications(r, c, basis),
      ate_steps: mixture ? ateSteps(r, c) : [],
      used_ate: usedAte(r, c, mixture),
      legal_findings: legal,
      // 계약에 신뢰도가 없다
      confidence: { level: null, reason: "" },
      limitations,
      target_links: target,
      source_refs: sourceRefs(r, c),
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

