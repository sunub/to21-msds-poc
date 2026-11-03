/* node --test 로 돈다 (pnpm test). 시험 도구를 더 들이지 않으려고 Node 내장 시험기를 쓴다. 값은 모두 가상이다. */
import assert from "node:assert/strict";
import { test } from "node:test";
import type { Finding, FindingDisplay, ReviewState } from "@/api/judgment";
import {
  actionsFor,
  buildTable,
  commentRequired,
  defaultFindingId,
  isUnreviewed,
  lawCounts,
  nextUnreviewedId,
  noteBreakdown,
  regulationCounts,
  reviewText,
  verdictText,
} from "./regulation.ts";

function f(id: string, patch: Partial<Finding> = {}): Finding {
  return {
    id: `m0/F15:${id}`,
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
    label: id,
    method: "규제DB 대조",
    out_of_scope_reason: null,
    law_label: "산안법",
    ...patch,
  };
}
const review = (patch: Partial<ReviewState> = {}): ReviewState => ({
  status: "불일치 확정",
  comment: null,
  reviewer: "가상",
  at: "2026-11-03T00:00:00+09:00",
  history_count: 1,
  stale: false,
  ...patch,
});
const display = (component: string | null): FindingDisplay => ({
  msds: "",
  expected: "",
  component,
  basis_lines: [],
  calc_lines: [],
  source_pages: [],
});

const low = f("low", { verdict: "불일치", type: "과기재", severity: "낮음" });
const high = f("high", { verdict: "불일치", type: "규제 누락", severity: "높음", law_label: "화관법" });
const border = f("border", { verdict: "경계" });
const lacking = f("lacking", { verdict: "근거부족" });
const match = f("match");
const old = f("old", { verdict: "불일치", type: "구버전", severity: "중간" });
const scope = f("scope", { verdict: "범위 외", out_of_scope_reason: "대조만" });
const all = [low, match, lacking, old, border, high, scope];
const names = (rows: Finding[]) => rows.map((r) => r.label);

test("처리 필요 줄은 불일치 심각도, 경계, 근거부족 순이다", () => {
  assert.deepEqual(names(buildTable(all, {}, { law: null, todoOnly: false }).todo), ["high", "low", "border", "lacking"]);
});

test("구버전은 불일치 값이어도 판정이 아니라 참고다 (D-09)", () => {
  const table = buildTable(all, {}, { law: null, todoOnly: false });
  assert.ok(!names(table.todo).includes("old"));
  assert.deepEqual(names(table.notes), ["old", "scope"]);
  assert.deepEqual(actionsFor(old), []);
  assert.equal(verdictText(old), "참고 · 구버전");
  assert.equal(noteBreakdown(table.notes), "구버전 1 · 대조만 1");
  assert.equal(regulationCounts(all, {}).mismatch, 2);
});

test("일치 줄은 성분별로 묶고 처리 필요만이면 숨긴다", () => {
  const rows = [f("a"), f("b"), f("c")];
  const shown = { [rows[0].id]: display("가"), [rows[1].id]: display("나"), [rows[2].id]: display("가") };
  const groups = buildTable(rows, shown, { law: null, todoOnly: false }).matches;
  assert.deepEqual(groups.map((g) => [g.component, g.items.length]), [["가", 2], ["나", 1]]);
  assert.deepEqual(buildTable(rows, shown, { law: null, todoOnly: true }).matches, []);
});

test("법령 거르기와 건수: 데이터에 있는 법령만", () => {
  assert.deepEqual(names(buildTable(all, {}, { law: "화관법", todoOnly: false }).todo), ["high"]);
  assert.deepEqual(lawCounts(all), [{ law: "산안법", count: 6 }, { law: "화관법", count: 1 }]);
});

test("기본 선택은 미처리 첫 줄, 모두 처리하면 처리 필요 첫 줄, 없으면 없음", () => {
  assert.equal(defaultFindingId(all, {}), high.id);
  assert.equal(defaultFindingId(all, { [high.id]: review() }), low.id);
  const done = Object.fromEntries([high, low, border, lacking].map((x) => [x.id, review()]));
  assert.equal(defaultFindingId(all, done), high.id);
  assert.equal(defaultFindingId([match, scope], {}), null);
});

test("판정이 바뀐 처리(stale)는 다시 미처리로 센다", () => {
  const stale = { [high.id]: review({ stale: true }) };
  assert.ok(isUnreviewed(high, stale));
  assert.equal(reviewText(high, stale), "다시 확인 필요");
  assert.equal(regulationCounts(all, stale).unreviewed, 4);
  assert.equal(regulationCounts(all, { [high.id]: review() }).unreviewed, 3);
});

test("다음 미처리: 뒤로 찾고, 끝이면 앞으로 돌아가고, 없으면 없음", () => {
  assert.equal(nextUnreviewedId(all, {}, high.id), low.id);
  assert.equal(nextUnreviewedId(all, {}, lacking.id), high.id);
  const onlyOne = Object.fromEntries([low, border, lacking].map((x) => [x.id, review()]));
  assert.equal(nextUnreviewedId(all, onlyOne, high.id), null);
});

test("처리 표기와 의견 필수 규칙", () => {
  assert.equal(reviewText(high, {}), "미처리");
  assert.equal(reviewText(match, {}), null);
  assert.equal(reviewText(high, { [high.id]: review({ status: "예외 승인" }) }), "예외 승인 · 가상");
  assert.deepEqual(actionsFor(match), ["확인"]);
  assert.deepEqual(actionsFor(lacking), ["불일치 확정", "예외 승인"]);
  assert.ok(commentRequired("예외 승인") && commentRequired("의견") && !commentRequired("불일치 확정"));
});

test("처리할 판정은 2항까지 포함해 모든 MSDS에서 모은다", async () => {
  const { unreviewedFindings } = await import("./regulation.ts");
  const hazard = f("hazard", { section: "2", verdict: "근거부족", id: "m1/F2:X:-" });
  const view = {
    consistency: { results: [{ findings: [low, match, high] }, { findings: [hazard, scope] }] },
    reviews: { [low.id]: review() },
  } as never;
  assert.deepEqual(names(unreviewedFindings(view)), ["high", "hazard"]);
});
