import assert from "node:assert/strict";
import { test } from "node:test";
import type { Finding, JudgmentView } from "../api/judgment.ts";
import { processedCounts, unreviewedFindings, valuesLabel } from "./save.ts";

const finding = (id: string, verdict: string, extra: Partial<Finding> = {}) =>
  ({ id, section: "2", kind: "class", item: "X", comp: null, msds: { present: true }, expected: { present: true }, verdict, type: null, severity: null, needs_explanation: false, label: id, method: "m", out_of_scope_reason: null, law_label: null, ...extra }) as unknown as Finding;

const view = (findings: Finding[], reviews: JudgmentView["reviews"]) =>
  ({ consistency: { results: [{ findings }] }, reviews }) as unknown as JudgmentView;

test("처리할 판정만, 급한 순서로 모은다", () => {
  const v = view([finding("m0/F2:A:-", "근거부족"), finding("m0/F2:B:-", "불일치", { severity: "높음" }), finding("m0/F2:C:-", "일치")], {});
  assert.deepEqual(unreviewedFindings(v).map((f) => f.id), ["m0/F2:B:-", "m0/F2:A:-"]);
});

test("처리했어도 판정이 바뀌었으면(stale) 다시 센다", () => {
  const done = { status: "불일치 확정", comment: null, reviewer: "홍", at: null, history_count: 1, stale: false } as const;
  const v = view([finding("m0/F2:A:-", "불일치"), finding("m0/F2:B:-", "불일치")], { "m0/F2:A:-": done, "m0/F2:B:-": { ...done, stale: true } });
  assert.deepEqual(unreviewedFindings(v).map((f) => f.id), ["m0/F2:B:-"]);
});

test("범위 외·참고·구버전은 처리 대상이 아니다", () => {
  const v = view([finding("m0/F2:A:-", "범위 외"), finding("m0/F2:B:-", "참고"), finding("m0/F15:C:OSH.X", "불일치", { type: "구버전" })], {});
  assert.equal(unreviewedFindings(v).length, 0);
});

test("처리 건수와 추출값 문구", () => {
  assert.deepEqual(processedCounts({ "불일치 확정": 2, "예외 승인": 1, 확인: 3 }), { confirmed: 5, exception: 1, total: 6 });
  assert.equal(valuesLabel("미검수"), "추출값 미검수");
  assert.equal(valuesLabel("완료"), "추출값 확인함");
});
