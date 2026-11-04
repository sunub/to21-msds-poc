/* node --test 로 돈다 (pnpm test). 값은 모두 가상이다 (D-43·D-47). */
import assert from "node:assert/strict";
import { test } from "node:test";
import type { ComponentSummary, Finding, MsdsResult } from "@/api/judgment";
import {
  ateLadder,
  ateSummary,
  classesText,
  componentFindings,
  componentHeadline,
  ateKey,
  ateTabLabel,
  defaultAteKey,
  formatContent,
  groupBySource,
  hitsText,
  limitationCards,
  sourceTabs,
  sourcesAgree,
} from "./components.ts";

function comp(patch: Partial<ComponentSummary> = {}): ComponentSummary {
  return {
    comp_ref: "1",
    name: "가상물질 A",
    cas: "0000-00-1",
    content: { lower: 93, upper: 98, unit: "%" },
    reference_classes: [],
    ate: [],
    regulation_hits: 0,
    reliability: "높음",
    notes: [],
    ...patch,
  };
}

function finding(id: string, patch: Partial<Finding> = {}): Finding {
  return {
    id,
    section: "15",
    kind: "regulation",
    item: "X.Y",
    comp: null,
    msds: { present: true },
    expected: { present: true },
    verdict: "일치",
    type: null,
    severity: null,
    needs_explanation: false,
    label: "가상 항목",
    method: "규제DB 대조",
    out_of_scope_reason: null,
    law_label: null,
    ...patch,
  };
}

function result(findings: Finding[]): MsdsResult {
  return { msds_index: 0, msds_revision_date: null, product_type: { value: "혼합물" }, findings };
}

test("함량: 범위·하한·단일값·원문 순으로 적는다", () => {
  assert.equal(formatContent({ lower: 93, upper: 98, unit: "%" }), "93 ~ 98");
  assert.equal(formatContent({ lower: 99.99, lower_op: ">=", unit: "%" }), "99.99 이상");
  assert.equal(formatContent({ upper: 5, upper_op: "<", unit: "%" }), "5 미만");
  assert.equal(formatContent({ value: 20 }), "20");
  assert.equal(formatContent({ raw: " 영업비밀 " }), "영업비밀");
  assert.equal(formatContent(null), "-");
});

test("성분 상세 머리: CAS와 단위 붙은 함량", () => {
  assert.equal(componentHeadline(comp()), "0000-00-1 · 93~98%");
  assert.equal(componentHeadline(comp({ content: { lower: 99.99, lower_op: ">=", unit: "%" } })), "0000-00-1 · 99.99% 이상");
  assert.equal(componentHeadline(comp({ cas: null, content: null })), "CAS·함량 미기재");
});

test("기준 분류: 같은 칩은 한 번, 출처는 괄호에, 없으면 분류 없음", () => {
  const classes = [
    { class_code: "HH_SKIN_CORR", category: "1", route_form: null, source: "가상 기준" },
    { class_code: "HH_ACUTE_INHAL", category: "3", route_form: "분진·미스트" as const, source: "가상 기준" },
    { class_code: "HH_SKIN_CORR", category: "1", route_form: null, source: "가상 기준 2" },
  ];
  assert.equal(classesText(classes), "피부 1 · 급성 독성(흡입) 3 · 미스트 (가상 기준, 가상 기준 2)");
  assert.equal(classesText([]), "분류 없음");
});

test("출처별 묶기와 두 출처가 같은지", () => {
  const same = groupBySource([
    { class_code: "PH_FLAM_GAS", category: "1", route_form: null, source: "KR03" },
    { class_code: "PH_FLAM_GAS", category: "1", route_form: null, source: "KR02" },
  ]);
  assert.deepEqual(same.map((g) => g.source), ["KR02", "KR03"]);
  assert.equal(sourcesAgree(same), true);
  const differ = groupBySource([
    { class_code: "PH_FLAM_GAS", category: "1", route_form: null, source: "KR02" },
    { class_code: "PH_FLAM_GAS", category: "2", route_form: null, source: "KR03" },
  ]);
  assert.equal(sourcesAgree(differ), false);
  assert.equal(sourcesAgree(same.slice(0, 1)), false);
});

test("ATE 요약: 경로별, 모두 같은 이유로 빠지면 한 번, 단일물질은 계산하지 않음", () => {
  const ate = [
    { route: "oral" as const, value: null, unit: null, form: null, source: null, step: 6, excluded: "자료 없음" },
    { route: "inhal" as const, value: 0.375, unit: "mg/L", form: "분진·미스트" as const, source: "MSDS 11항", step: 3, excluded: null },
  ];
  assert.equal(ateSummary(ate, "혼합물"), "경구 제외(자료 없음) · 흡입 0.375 mg/L 미스트 (MSDS 11항, 3단계)");
  const water = (["oral", "dermal", "inhal"] as const).map((route) => ({ route, value: null, unit: null, form: null, source: null, step: 5, excluded: "무독성" }));
  assert.equal(ateSummary(water, "혼합물"), "무독성 제외 (5단계)");
  assert.equal(ateSummary([], "단일물질"), "해당 없음 (단일물질은 계산하지 않음)");
});

test("ATE 순서: 쓴 단계 앞은 없음, 뒤는 해당 없음", () => {
  const steps = ateLadder({ route: "inhal", value: 0.375, unit: "mg/L", form: "분진·미스트", source: "MSDS 11항", step: 3, excluded: null });
  assert.deepEqual(steps.map((s) => s.state), ["missing", "missing", "used", "skipped", "skipped", "skipped"]);
  assert.equal(steps[2].text, "● 사용함 · 0.375 mg/L (미스트, MSDS 11항)");
  const water = ateLadder({ route: "oral", value: null, unit: null, form: null, source: null, step: 5, excluded: "무독성" });
  assert.equal(water[4].text, "● 해당 · 무독성");
  assert.ok(ateLadder({ route: "oral", value: null, unit: null, form: null, source: null, step: null, excluded: null }).every((s) => s.state === "unknown"));
});

test("처음 보여 줄 경로는 값을 쓴 경로", () => {
  assert.equal(
    defaultAteKey([
      { route: "oral", value: null, unit: null, form: null, source: null, step: 6, excluded: "자료 없음" },
      { route: "dermal", value: 2000, unit: "mg/kg", form: null, source: "가상", step: 1, excluded: null },
    ]),
    "dermal",
  );
  assert.equal(defaultAteKey([]), null);
});

test("흡입은 형태(가스·증기·분진·미스트)마다 따로 고른다", () => {
  // 판정 API는 흡입 ATE를 형태별로 한 줄씩 준다. 경로만으로 고르면 둘째 형태를 볼 수 없다
  const ate = [
    { route: "oral" as const, value: null, unit: null, form: null, source: null, step: 6, excluded: "자료 없음" },
    { route: "inhal" as const, value: null, unit: null, form: "분진·미스트" as const, source: null, step: 6, excluded: "자료 없음" },
    { route: "inhal" as const, value: 3.1, unit: "mg/L", form: "증기" as const, source: "가상", step: 1, excluded: null },
  ];
  const keys = ate.map(ateKey);
  assert.equal(new Set(keys).size, ate.length);
  assert.deepEqual(ate.map(ateTabLabel), ["경구", "흡입(분진·미스트)", "흡입(증기)"]);
  assert.equal(defaultAteKey(ate), "inhal:증기");
  assert.equal(
    ateSummary(ate, "혼합물"),
    "경구 제외(자료 없음) · 흡입(분진·미스트) 제외(자료 없음) · 흡입 3.1 mg/L 증기 (가상, 1단계)",
  );
});

test("성분의 판정은 comp_ref 또는 CAS로 찾고 항으로 거른다", () => {
  const r = result([
    finding("a", { comp: { comp_ref: "1", cas: "0000-00-1", name: "가상물질 A" } }),
    finding("b", { comp: { comp_ref: "9", cas: "0000-00-1", name: "가상물질 A" } }),
    finding("c", { comp: { comp_ref: "2", cas: "0000-00-2", name: "가상물질 B" } }),
    finding("d", { section: "2", kind: "class", comp: { comp_ref: "1", cas: "0000-00-1", name: "가상물질 A" } }),
    finding("e"),
  ]);
  assert.deepEqual(componentFindings(r, comp(), "15").map((f) => f.id), ["a", "b"]);
  assert.deepEqual(componentFindings(r, comp(), "2").map((f) => f.id), ["d"]);
});

test("제약사항 카드: 판정을 찾으면 이름·판정·항을 붙이고, 못 찾아도 문장은 남긴다", () => {
  const r = result([finding("m0/F2:PH_METAL_CORR:-", { section: "2", kind: "class", verdict: "근거부족", label: "금속부식성" })]);
  const cards = limitationCards(r, [
    { finding_id: "m0/F2:PH_METAL_CORR:-", text: "시험자료가 없습니다" },
    { finding_id: "m0/F2:없는번호", text: "판정이 사라짐" },
    { finding_id: null, text: "가정 문장" },
  ]);
  assert.deepEqual(
    cards.map((c) => [c.title, c.verdict, c.section, c.text]),
    [
      ["금속부식성", "근거부족", "2", "시험자료가 없습니다"],
      ["검토 필요", null, null, "판정이 사라짐"],
      ["검토 필요", null, null, "가정 문장"],
    ],
  );
  assert.equal(new Set(cards.map((c) => c.key)).size, 3);
});

test("원문 버튼: 혼합물은 3항·11항, 단일물질은 3항, 쪽이 없는 항은 뺀다", () => {
  const sections = [
    { msds_index: 0, section: 3, pages: [3] },
    { msds_index: 0, section: 11, pages: [9, 10] },
    { msds_index: 1, section: 3, pages: [20] },
  ];
  assert.deepEqual(sourceTabs(sections, 0, false), [{ section: 3, page: 3 }, { section: 11, page: 9 }]);
  assert.deepEqual(sourceTabs(sections, 0, true), [{ section: 3, page: 3 }]);
  assert.deepEqual(sourceTabs(sections, 1, false), [{ section: 3, page: 20 }]);
});

test("15항 해당 수", () => {
  assert.equal(hitsText(8), "8건 해당");
  assert.equal(hitsText(0), "없음");
});
