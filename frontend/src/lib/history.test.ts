/* node --test 로 돈다 (pnpm test). 값은 모두 가상이다. */
import assert from "node:assert/strict";
import { test } from "node:test";
import type { HistoryEntry } from "@/api/history";
import { filterHistory, historyPills, kindOf, linkOf, mergeHistory } from "./history.ts";

function e(at: string, area: HistoryEntry["area"], target: string, ref?: HistoryEntry["ref"]): HistoryEntry {
  return { at, reviewer: "가상", area, target, action: "확인", detail: null, comment: null, ref };
}

test("두 서버의 이력을 최근 처리부터 합친다", () => {
  const values = [e("2026-11-03T10:00:00+09:00", "추출값", "a"), e("2026-11-03T12:00:00+09:00", "추출값", "c")];
  const judgment = [e("2026-11-03T11:00:00+09:00", "15항", "b")];
  assert.deepEqual(mergeHistory(values, judgment).map((x) => x.target), ["c", "b", "a"]);
});

test("시간대 표기가 달라도 실제 시각으로 비교한다", () => {
  const kst = e("2026-11-03T10:30:00+09:00", "2항", "늦음");
  const utc = e("2026-11-03T01:00:00+00:00", "2항", "이름");
  assert.deepEqual(mergeHistory([utc], [kst]).map((x) => x.target), ["늦음", "이름"]);
});

test("같은 시각이면 뒤에 받은 기록이 위로 온다", () => {
  const at = "2026-11-03T10:00:00+09:00";
  assert.deepEqual(mergeHistory([e(at, "2항", "먼저"), e(at, "2항", "나중")]).map((x) => x.target), ["나중", "먼저"]);
});

test("2항과 15항은 판정 처리로 묶고, 기록이 없는 구분은 숨긴다", () => {
  const rows = [e("2026-11-03T10:00:00+09:00", "2항", "a"), e("2026-11-03T10:00:00+09:00", "15항", "b"), e("2026-11-03T10:00:00+09:00", "추출값", "c")];
  assert.equal(kindOf(rows[0]), "judgment");
  assert.equal(filterHistory(rows, "judgment").length, 2);
  assert.deepEqual(historyPills(rows).map((p) => p.label), ["전체 3", "판정 처리 2", "추출값 1"]);
  assert.deepEqual(historyPills([]).map((p) => p.label), ["전체 0"]);
});

test("이동 칸은 구분과 ref 로 갈 곳을 정한다", () => {
  const at = "2026-11-03T10:00:00+09:00";
  assert.deepEqual(linkOf(e(at, "15항", "a", { finding_id: "m1/F15:0000-00-1:OSH.X" })), { tab: "regulation", finding: "m1/F15:0000-00-1:OSH.X", msds: 1 });
  assert.deepEqual(linkOf(e(at, "2항", "b")), { tab: "hazard" });
  assert.deepEqual(linkOf(e(at, "추출값", "c", { msds_index: 0, path: "x" })), { tab: "values" });
  assert.deepEqual(linkOf(e(at, "저장", "d")), { save: true });
});
