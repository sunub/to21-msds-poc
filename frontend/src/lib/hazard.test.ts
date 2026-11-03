/* node --test 로 돈다 (pnpm test). 값은 모두 가상이다. */
import assert from "node:assert/strict";
import { test } from "node:test";
import type { Finding, FindingDisplay, JudgmentView } from "@/api/judgment";
import { basisTitle, buildHazardTable, hazardFilterItems, hazardFindings, hiddenByFilter, isHazardFilter, sourceTabs, valueEmphasis } from "./hazard.ts";

function f(id: string, patch: Partial<Finding> = {}): Finding {
  return {
    id: `m0/F2:${id}`,
    section: "2",
    kind: "class",
    item: id,
    comp: null,
    msds: { present: true },
    expected: { present: true },
    verdict: "일치",
    type: null,
    severity: null,
    needs_explanation: false,
    label: id,
    method: "가산·한계농도",
    out_of_scope_reason: null,
    law_label: null,
    ...patch,
  };
}

const display = (patch: Partial<FindingDisplay> = {}): FindingDisplay => ({
  msds: "구분 1",
  expected: "구분 1",
  component: null,
  basis_lines: [],
  calc_lines: [],
  source_pages: [],
  ...patch,
});

const FINDINGS = [
  f("match:-"),
  f("low:-", { verdict: "불일치", type: "표시 요소 불일치", severity: "낮음" }),
  f("lack:-", { verdict: "근거부족" }),
  f("high:-", { verdict: "불일치", type: "과소분류", severity: "높음" }),
  f("border:-", { verdict: "경계" }),
  f("na:-", { verdict: "범위 외", out_of_scope_reason: "해당 없음" }),
  f("ref:-", { verdict: "참고" }),
];

test("2항 판정만 고른다", () => {
  const view = {
    consistency: { results: [{ msds_index: 0, findings: [f("a:-"), f("b", { section: "15", id: "m0/F15:b" })] }] },
  } as unknown as JudgmentView;
  assert.deepEqual(hazardFindings(view, 0).map((x) => x.id), ["m0/F2:a:-"]);
});

test("전체 건수는 범위 외·참고를 뺀다. 경고 알약은 있을 때만 보인다", () => {
  assert.deepEqual(hazardFilterItems(FINDINGS).map((i) => i.label), ["전체 5", "불일치 2", "경계 1", "근거부족 1", "일치 1"]);
  assert.ok(hazardFilterItems([...FINDINGS, f("warn:-", { verdict: "경고" })]).some((i) => i.label === "경고 1"));
});

test("전체 보기: 처리 줄은 심각도 순, 일치와 범위 외는 따로 접는다", () => {
  const table = buildHazardTable(FINDINGS, null);
  assert.deepEqual(table.rows.map((x) => x.label), ["high:-", "low:-", "border:-", "lack:-"]);
  assert.deepEqual(table.matches.map((x) => x.label), ["match:-"]);
  assert.deepEqual(table.notes.map((x) => x.label), ["na:-", "ref:-"]);
});

test("거르면 그 판정만 바로 보이고 접힌 묶음은 없다", () => {
  const table = buildHazardTable(FINDINGS, "일치");
  assert.deepEqual(table.rows.map((x) => x.label), ["match:-"]);
  assert.equal(table.matches.length + table.notes.length, 0);
});

test("거르기로 숨은 줄을 가려낸다", () => {
  assert.equal(hiddenByFilter(f("a:-", { verdict: "경계" }), "불일치"), true);
  assert.equal(hiddenByFilter(f("a:-", { verdict: "불일치" }), "불일치"), false);
  assert.equal(hiddenByFilter(f("a:-", { verdict: "범위 외" }), null), false);
});

test("불일치만 틀린 값으로 강조한다", () => {
  assert.equal(valueEmphasis(f("a:-", { verdict: "불일치" })), "differ");
  assert.equal(valueEmphasis(f("a:-", { verdict: "일치" })), "same");
  assert.equal(valueEmphasis(f("a:-", { verdict: "근거부족" })), "neutral");
  assert.equal(valueEmphasis(f("a:-", { verdict: "일치", type: "구버전" })), "neutral");
});

test("원문 쪽 버튼은 겹치지 않고, 2항 밖 쪽만 제목에 적는다", () => {
  const d = display({
    calc_lines: ["가상 계산"],
    source_pages: [{ section: 2, page: 1 }, { section: 11, page: 3 }, { section: 11, page: 3 }],
  });
  assert.deepEqual(sourceTabs(d).map((t) => t.label), ["2항 p.1", "11항 p.3"]);
  assert.equal(basisTitle(d), "판단 근거와 계산 과정 · 11항 p.3");
  assert.equal(basisTitle(display({ source_pages: [{ section: 2, page: 1 }] })), "판단 근거");
});

test("주소의 거르기 값을 확인한다", () => {
  assert.equal(isHazardFilter("불일치"), true);
  assert.equal(isHazardFilter("all"), false);
  assert.equal(isHazardFilter(null), false);
});
