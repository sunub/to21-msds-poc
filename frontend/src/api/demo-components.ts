/*
 * 성분별 요약 화면용 고정 데이터 (개발용): 25번 황산 KZ-A-S004 (혼합물), 주소에 &product=single 을 붙이면 단일물질 예시.
 * 문서 번호가 "demo" 일 때만 components.ts 가 이 값을 돌려준다. 값은 시안(성분별 요약 혼합물·단일물질)의 예시를 따른다.
 */
import { DEMO_FINDINGS_15 } from "./demo-findings";
import type { ComponentsResponse, ComponentSummary } from "./components-schemas";

const MSDS_ID = "msds_a";
const H2SO4 = "comp_h2so4";
const WATER = "comp_water";
const HYDROGEN = "comp_h2";

/** ATE 를 가져오는 6단계의 이름과 순서 (시안) */
const ATE_LABELS = ["독성DB 수치", "분류 구분 → 환산값", "MSDS 11항 수치", "부등호 값만 있음", "무독성 성분", "자료 없음"];

type StepSpec = { adopted?: { input: string | null; value: number | null; unit: string | null }; reason?: string };

/** 단계 6개를 시안 순서대로 만든다. adopted 가 있는 단계가 채택된 단계이고, 나머지는 채택하지 않은 이유를 갖는다 */
const steps = (specs: StepSpec[]) =>
  ATE_LABELS.map((label, i) => {
    const s = specs[i];
    return {
      step: i + 1,
      label,
      input: s.adopted?.input ?? null,
      adopted: !!s.adopted,
      value: s.adopted?.value ?? null,
      unit: s.adopted?.unit ?? null,
      excluded_reason: s.adopted ? null : (s.reason ?? "해당 없음"),
    };
  });

const sulfuric: ComponentSummary = {
  component_id: H2SO4,
  msds_id: MSDS_ID,
  name: "황산",
  cas_no: "7664-93-9",
  concentration: { raw_text: "93~98", min: 93, max: 98, operator: null, unit: "%" },
  classifications: [
    { source: "TO21 분류기준", name: "피부", classification: "1", version: null, basis: "TO21 분류기준" },
    { source: "TO21 분류기준", name: "눈", classification: "1", version: null, basis: "TO21 분류기준" },
    { source: "TO21 분류기준", name: "발암성", classification: "1A", version: null, basis: "TO21 분류기준" },
    { source: "TO21 분류기준", name: "표적장기(1회)", classification: "1", version: null, basis: "TO21 분류기준" },
  ],
  ate_steps: steps([
    { reason: "없음" },
    { reason: "없음" },
    { adopted: { input: "미스트, 4hr", value: 0.375, unit: "mg/L" } },
    {},
    {},
    {},
  ]),
  used_ate: { applicable: true, reason: "경구 제외(11항) · 흡입 0.375 mg/L 미스트 (11항, 3단계)", value: 0.375, unit: "mg/L", step: 3 },
  // 15항 판정 중 이 성분에 걸린 건 (demo-findings 의 15항 데이터와 같은 번호)
  legal_findings: DEMO_FINDINGS_15.items
    .filter((f) => f.component_id === H2SO4)
    .map((f) => ({ finding_id: f.finding_id, label: `${f.law} ${f.item}` })),
  confidence: { level: "medium", reason: "기준정보 DB 값이 없어 MSDS 11항 값으로 계산했습니다." },
  limitations: [
    { kind: "insufficient", reason: "혼합물 시험자료가 없어 판정할 수 없습니다.", finding_id: "fnd_demo_2" },
    { kind: "insufficient", reason: "황산·물 모두 기준정보에 수생 분류가 없습니다. MSDS 구분3의 근거를 확인해야 합니다.", finding_id: "fnd_demo_3" },
  ],
  target_links: [{ section: 2, finding_id: "fnd_demo_1" }],
  source_refs: [
    { section: 3, page_no: 3 },
    { section: 11, page_no: 9 },
  ],
};

const water: ComponentSummary = {
  component_id: WATER,
  msds_id: MSDS_ID,
  name: "물",
  cas_no: "7732-18-5",
  concentration: { raw_text: "2~7", min: 2, max: 7, operator: null, unit: "%" },
  classifications: [{ source: "TO21 분류기준", name: "분류안됨", classification: "", version: null, basis: "TO21 분류기준" }],
  ate_steps: steps([{ reason: "없음" }, { reason: "없음" }, { reason: "없음" }, {}, { adopted: { input: "무독성 제외", value: null, unit: null } }, {}]),
  used_ate: { applicable: true, reason: "무독성 제외 (5단계)", step: 5 },
  legal_findings: [],
  confidence: { level: "high", reason: "무독성 성분이라 계산에서 제외했습니다." },
  limitations: [],
  target_links: [],
  source_refs: [{ section: 3, page_no: 3 }],
};

export const DEMO_COMPONENTS_MIXTURE: ComponentsResponse = {
  msds_id: MSDS_ID,
  product_type: "mixture",
  items: [sulfuric, water],
  selected_component_id: H2SO4,
  limitations: [],
  confidence_rule_version: "demo-1",
};

const SINGLE_SOURCES = ["KR02 환경부", "KR03 고용노동부"];

const hydrogen: ComponentSummary = {
  component_id: HYDROGEN,
  msds_id: MSDS_ID,
  name: "수소",
  cas_no: "1333-74-0",
  concentration: { raw_text: "99.99 이상", min: 99.99, max: null, operator: ">=", unit: "%" },
  classifications: SINGLE_SOURCES.flatMap((source) => [
    { source, name: "인화성 가스", classification: "1", version: null, basis: "TO21 분류기준" },
    { source, name: "고압가스", classification: "", version: null, basis: "TO21 분류기준" },
  ]),
  ate_steps: [],
  used_ate: { applicable: false, reason: "해당 없음 (단일물질은 계산하지 않음)" },
  // 시안의 "3건 해당". 데모의 15항 판정은 황산 기준이라 이 번호들은 실제 판정과 이어지지 않는다 (이동하면 첫 행이 선택된다)
  legal_findings: [
    { finding_id: "fnd_single_15_1", label: "산안법 작업환경측정 대상" },
    { finding_id: "fnd_single_15_2", label: "산안법 특수건강진단 대상" },
    { finding_id: "fnd_single_15_3", label: "위험물법 위험물" },
  ],
  confidence: { level: "high", reason: "두 출처의 기준 분류가 같습니다." },
  limitations: [],
  target_links: [],
  source_refs: [{ section: 3, page_no: 2 }],
};

export const DEMO_COMPONENTS_SINGLE: ComponentsResponse = {
  msds_id: MSDS_ID,
  product_type: "single",
  items: [hydrogen],
  selected_component_id: HYDROGEN,
  limitations: [],
  confidence_rule_version: "demo-1",
};

/** 판별하지 못한 경우 (&product=unknown) */
export const DEMO_COMPONENTS_UNKNOWN: ComponentsResponse = {
  msds_id: MSDS_ID,
  product_type: "unknown",
  items: [],
  selected_component_id: null,
  limitations: [],
  confidence_rule_version: null,
};
