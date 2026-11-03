/*
 * 성분별 요약 탭의 표시 규칙. 화면과 분리한 순수 함수라 서버 없이 시험한다 (components.test.ts).
 * 판정을 새로 계산하지 않는다. 판정 API가 준 성분 요약(component_summary)과 제약사항을 고르고 글로 바꾸기만 한다.
 */
import type { ComponentSummary, Finding, Limitation, MsdsResult } from "@/api/judgment";
import type { Tone } from "@/components/ui";

type Quantity = ComponentSummary["content"];
type ReferenceClass = ComponentSummary["reference_classes"][number];
export type AteEntry = ComponentSummary["ate"][number];

/** 유해성 분류 코드의 짧은 이름 (화면 표기. 시안 '피부 1 · 눈 1 · 발암성 1A') */
const CLASS_LABEL: Record<string, string> = {
  PH_EXPLOSIVE: "폭발성 물질",
  PH_FLAM_GAS: "인화성 가스",
  PH_AEROSOL: "에어로졸",
  PH_OXID_GAS: "산화성 가스",
  PH_PRESS_GAS: "고압가스",
  PH_FLAM_LIQ: "인화성 액체",
  PH_FLAM_SOL: "인화성 고체",
  PH_SELF_REACT: "자기반응성",
  PH_PYRO_LIQ: "자연발화성 액체",
  PH_PYRO_SOL: "자연발화성 고체",
  PH_SELF_HEAT: "자기발열성",
  PH_WATER_REACT: "물반응성",
  PH_OXID_LIQ: "산화성 액체",
  PH_OXID_SOL: "산화성 고체",
  PH_ORG_PEROX: "유기과산화물",
  PH_METAL_CORR: "금속부식성",
  PH_DESENS_EXPL: "둔감화된 폭발성",
  HH_ACUTE_ORAL: "급성 독성(경구)",
  HH_ACUTE_DERMAL: "급성 독성(경피)",
  HH_ACUTE_INHAL: "급성 독성(흡입)",
  HH_SKIN_CORR: "피부",
  HH_EYE_DMG: "눈",
  HH_RESP_SENS: "호흡기 과민성",
  HH_SKIN_SENS: "피부 과민성",
  HH_MUTAGEN: "생식세포 변이원성",
  HH_CARCINOGEN: "발암성",
  HH_REPRO: "생식독성",
  HH_STOT_SE: "표적장기(1회)",
  HH_STOT_RE: "표적장기(반복)",
  HH_ASPIRATION: "흡인 유해성",
  ENV_AQ_ACUTE: "급성 수생환경",
  ENV_AQ_CHRONIC: "만성 수생환경",
  ENV_OZONE: "오존층",
  ETC_UNMAPPED: "기타",
};

export const classLabel = (code: string) => CLASS_LABEL[code] ?? code;

const ROUTE_LABEL: Record<AteEntry["route"], string> = { oral: "경구", dermal: "경피", inhal: "흡입" };
export const routeLabel = (route: AteEntry["route"]) => ROUTE_LABEL[route];
/** 시안 '0.375 mg/L 미스트': 분진·미스트는 미스트로 줄여 적는다 */
const formLabel = (form: AteEntry["form"]) => (form === "분진·미스트" ? "미스트" : form);

const OP_TEXT: Record<string, string> = { ">=": "이상", ">": "초과", "<=": "이하", "<": "미만" };
const num = (v: number) => String(v);

/** 함량 Q → '93 ~ 98', '99.99 이상'. 단위(%)는 열 머리에 있어 붙이지 않는다. 숫자가 없으면 원문 */
export function formatContent(q: Quantity): string {
  if (!q) return "-";
  const { value, lower, upper, lower_op, upper_op } = q;
  if (lower != null && upper != null) return `${num(lower)} ~ ${num(upper)}`;
  if (lower != null) return `${num(lower)} ${OP_TEXT[lower_op ?? ">="] ?? "이상"}`;
  if (upper != null) return `${num(upper)} ${OP_TEXT[upper_op ?? "<="] ?? "이하"}`;
  if (value != null) return num(value);
  return q.raw?.trim() || "-";
}

/** 성분 상세 머리 '7664-93-9 · 93~98%' */
export function componentHeadline(c: ComponentSummary): string {
  return [c.cas, contentWithUnit(c.content)].filter(Boolean).join(" · ") || "CAS·함량 미기재";
}

/** '93~98%', '99.99% 이상'. 숫자가 없으면 원문, 원문도 없으면 null */
function contentWithUnit(q: Quantity): string | null {
  if (!q) return null;
  const unit = q.unit ?? "%";
  const { value, lower, upper, lower_op, upper_op } = q;
  if (lower != null && upper != null) return `${num(lower)}~${num(upper)}${unit}`;
  if (lower != null) return `${num(lower)}${unit} ${OP_TEXT[lower_op ?? ">="] ?? "이상"}`;
  if (upper != null) return `${num(upper)}${unit} ${OP_TEXT[upper_op ?? "<="] ?? "이하"}`;
  if (value != null) return `${num(value)}${unit}`;
  return q.raw?.trim() || null;
}

/** 칩 하나 '피부 1', '급성 독성(흡입) 3 · 미스트' */
export function classChip(c: ReferenceClass): string {
  const form = c.route_form ? ` · ${formLabel(c.route_form)}` : "";
  return `${classLabel(c.class_code)} ${c.category}${form}`;
}

/** 표 한 칸 '피부 1 · 눈 1 (TO21 분류기준)'. 출처가 여럿이면 괄호 안에 모두 적는다 */
export function classesText(classes: ReferenceClass[]): string {
  if (classes.length === 0) return "분류 없음";
  const chips = [...new Set(classes.map(classChip))];
  const sources = [...new Set(classes.map((c) => c.source))];
  return `${chips.join(" · ")} (${sources.join(", ")})`;
}

export type SourceGroup = { source: string; chips: string[] };

/** 출처별로 묶는다 (단일물질 '기준 분류 (출처별)'). 출처 이름순 */
export function groupBySource(classes: ReferenceClass[]): SourceGroup[] {
  const groups = new Map<string, string[]>();
  for (const c of classes) {
    const chips = groups.get(c.source) ?? [];
    const chip = classChip(c);
    if (!chips.includes(chip)) chips.push(chip);
    groups.set(c.source, chips);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([source, chips]) => ({ source, chips }));
}

/** 출처가 둘 이상이고 분류가 모두 같으면 참. 시안 '두 출처가 같아 어느 쪽을 써도 결과가 같습니다' */
export function sourcesAgree(groups: SourceGroup[]): boolean {
  if (groups.length < 2) return false;
  const key = (g: SourceGroup) => [...g.chips].sort().join("|");
  return groups.every((g) => key(g) === key(groups[0]));
}

/** ATE 수집 순서 (설계서 v0.4 21장). 번호가 판정 API의 step 이다 */
export const ATE_STEPS = ["독성DB 수치", "분류 구분 → 환산값", "MSDS 11항 수치", "부등호 값만 있음", "무독성 성분", "자료 없음"] as const;

function ateValue(a: AteEntry): string | null {
  if (a.value == null) return null;
  const extra = [formLabel(a.form), a.source].filter(Boolean).join(", ");
  return `${num(a.value)}${a.unit ? ` ${a.unit}` : ""}${extra ? ` (${extra})` : ""}`;
}

/** 표 한 칸 '경구 제외(자료 없음) · 흡입 0.375 mg/L 미스트 (MSDS 11항, 3단계)'. 경로가 모두 같은 이유로 빠졌으면 한 번만 */
export function ateSummary(ate: AteEntry[], productType: string): string {
  if (ate.length === 0) return productType === "단일물질" ? "해당 없음 (단일물질은 계산하지 않음)" : "-";
  const allSame = ate.every((a) => a.excluded && a.excluded === ate[0].excluded && a.step === ate[0].step);
  if (allSame) return `${ate[0].excluded} 제외${ate[0].step ? ` (${ate[0].step}단계)` : ""}`;
  return ate
    .map((a) => {
      if (a.excluded) return `${routeLabel(a.route)} 제외(${a.excluded})`;
      const where = [a.source, a.step ? `${a.step}단계` : null].filter(Boolean).join(", ");
      const value = a.value == null ? "값 없음" : `${num(a.value)}${a.unit ? ` ${a.unit}` : ""}`;
      return `${routeLabel(a.route)} ${value}${a.form ? ` ${formLabel(a.form)}` : ""}${where ? ` (${where})` : ""}`;
    })
    .join(" · ");
}

export type LadderStep = { no: number; name: string; state: "missing" | "used" | "skipped" | "unknown"; text: string };

/** 성분 상세의 'ATE를 가져온 순서'. 쓴 단계 앞은 찾아봤지만 없음, 뒤는 볼 필요가 없어 해당 없음 */
export function ateLadder(a: AteEntry): LadderStep[] {
  return ATE_STEPS.map((name, i) => {
    const no = i + 1;
    if (a.step == null) return { no, name, state: "unknown", text: "확인 안 됨" };
    if (no < a.step) return { no, name, state: "missing", text: "없음" };
    if (no > a.step) return { no, name, state: "skipped", text: "해당 없음" };
    const value = ateValue(a);
    return { no, name, state: "used", text: a.excluded ? `● 해당 · ${a.excluded}` : `● 사용함${value ? ` · ${value}` : ""}` };
  });
}

/** 상세에서 처음 보여 줄 경로: 값을 쓴 경로 → 흡입 → 첫 경로 */
export function defaultRoute(ate: AteEntry[]): AteEntry["route"] | null {
  return (ate.find((a) => !a.excluded && a.value != null) ?? ate.find((a) => a.route === "inhal") ?? ate[0])?.route ?? null;
}

const RELIABILITY_TONE: Record<ComponentSummary["reliability"], Tone> = { 높음: "success", 보통: "warning", 낮음: "danger" };
export const reliabilityTone = (r: ComponentSummary["reliability"]) => RELIABILITY_TONE[r];

const VERDICT_TONE: Record<string, Tone> = { 불일치: "danger", 경계: "warning", 근거부족: "neutral", 경고: "warning", 일치: "success" };
export const verdictTone = (verdict: string): Tone => VERDICT_TONE[verdict] ?? "neutral";

/** 15항 '해당' 수 '8건 해당' / '없음' */
export const hitsText = (n: number) => (n > 0 ? `${n}건 해당` : "없음");

/** 고른 MSDS 의 결과. 없는 번호면 첫 건 */
export function pickResult(results: MsdsResult[], msdsIndex: number): MsdsResult {
  return results.find((r) => r.msds_index === msdsIndex) ?? results[0];
}

/** 그 성분의 15항 판정 (성분 연결은 comp_ref, 없으면 CAS로 찾는다) */
export function componentFindings(result: MsdsResult, c: ComponentSummary, section: "2" | "15"): Finding[] {
  return result.findings.filter(
    (f) => f.section === section && !!f.comp && (f.comp.comp_ref === c.comp_ref || (!!c.cas && f.comp.cas === c.cas)),
  );
}

export type LimitationCard = {
  key: string;
  title: string;
  verdict: string | null;
  text: string;
  findingId: string | null;
  section: "2" | "15" | null;
};

/** 제약사항 카드: 판정 번호가 있으면 그 판정의 이름과 판정을 붙인다. 판정을 찾지 못해도 문장은 보인다 */
export function limitationCards(result: MsdsResult, limitations: Limitation[]): LimitationCard[] {
  const byId = new Map(result.findings.map((f) => [f.id, f]));
  return limitations.map((l, i) => {
    const f = l.finding_id ? byId.get(l.finding_id) : undefined;
    return {
      key: `${l.finding_id ?? "none"}#${i}`,
      title: f?.label ?? "검토 필요",
      verdict: f?.verdict ?? null,
      text: l.text,
      findingId: f?.id ?? null,
      section: f?.section ?? null,
    };
  });
}

export type SourceTab = { section: 3 | 11; page: number };

/** 원문 버튼 '3항 p.3 · 11항 p.9'. 단일물질은 성분이 하나라 3항만 본다 */
export function sourceTabs(
  sections: { msds_index: number; section: number; pages: number[] }[],
  msdsIndex: number,
  single: boolean,
): SourceTab[] {
  const wanted: (3 | 11)[] = single ? [3] : [3, 11];
  return wanted.flatMap((section) => {
    const page = sections.find((s) => s.msds_index === msdsIndex && s.section === section)?.pages[0];
    return page ? [{ section, page }] : [];
  });
}
