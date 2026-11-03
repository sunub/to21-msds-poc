/* node --test 로 돈다 (pnpm test). 값은 모두 가상이다. */
import assert from "node:assert/strict";
import { test } from "node:test";
import type { SaveOverview, Snapshot } from "@/api/save";
import { REPORT_PARTS, headline, processedText, reportFileName, reportInclude, saveState, valueRows, verdictSummary } from "./save.ts";

const counts = { 일치: 5, 불일치: 1, 경계: 0, 근거부족: 2, 경고: 1, 참고: 3, "범위 외": 4 };

function overview(patch: Partial<SaveOverview> = {}): SaveOverview {
  return {
    job_id: "U-20261104-001",
    version: 2,
    handoff_seq: 3,
    verdicts: { total: counts, by_section: { "2": counts, "15": counts } },
    reviews: { 미검토: 0, "불일치 확정": 1, "예외 승인": 1, 확인: 2, unreviewed_ids: [] },
    values: { state: "완료", model_as_is: 0, confirmed: 112, edited: 3, fields_total: 115 },
    snapshots: [],
    ...patch,
  };
}

function snap(patch: Partial<Snapshot> = {}): Snapshot {
  return {
    contract: "snapshot/1",
    job_id: "U-20261104-001",
    snapshot_no: 1,
    handoff_seq: 3,
    version: 2,
    last_review_event_id: 7,
    counts: { findings: 9, 미검토: 0, "불일치 확정": 1, "예외 승인": 1, 확인: 2, "미검수 칸": 0 },
    saved_by: "가상 검토자",
    saved_at: "2026-10-31T11:08:00+09:00",
    note: null,
    ...patch,
  };
}

test("판정 요약은 판정한 다섯 가지만 시안 순서로 센다 (참고·범위 외 제외)", () => {
  assert.deepEqual(
    verdictSummary(counts).map((v) => `${v.verdict} ${v.count}`),
    ["불일치 1", "경계 0", "근거부족 2", "경고 1", "일치 5"],
  );
});

test("처리 건수는 0인 처리를 빼고 괄호로 나눠 적는다", () => {
  assert.equal(processedText(overview().reviews), "처리 4건 (불일치 확정 1 · 예외 승인 1 · 확인 2)");
  assert.equal(processedText({ 미검토: 4, "불일치 확정": 0, "예외 승인": 0, 확인: 0, unreviewed_ids: [] }), "처리 0건");
});

test("저장 상태: 저장본이 없음 / 지금 판정과 같음 / 저장 뒤 바뀜", () => {
  assert.equal(saveState(overview()).kind, "none");
  const current = saveState(overview({ snapshots: [snap({ snapshot_no: 2 }), snap()] }));
  assert.equal(current.kind, "current");
  assert.equal(current.kind === "current" && current.snapshot.snapshot_no, 2);
  // 저장 뒤 값을 고쳐 넘김 번호가 올랐거나 다시 판정해 버전이 올랐다
  assert.equal(saveState(overview({ snapshots: [snap({ handoff_seq: 2 })] })).kind, "changed");
  assert.equal(saveState(overview({ snapshots: [snap({ version: 1 })] })).kind, "changed");
});

test("머리말은 저장 여부와 미검토로 정한다 (시안 3.1·3.2)", () => {
  assert.equal(headline(overview()).title, "검토 결과를 저장합니다");
  assert.equal(headline(overview({ snapshots: [snap()] })).title, "검토를 마쳤습니다");
  const unreviewed = overview({ reviews: { ...overview().reviews, 미검토: 4 }, snapshots: [snap()] });
  assert.equal(headline(unreviewed).title, "저장했습니다. 처리하지 않은 판정이 남아 있습니다");
  assert.equal(headline(overview({ snapshots: [snap({ version: 1 })] })).title, "저장한 뒤 바뀐 내용이 있습니다");
});

test("값의 출처 칸 수: 확인함 · 수정됨 · 미검수", () => {
  assert.deepEqual(
    valueRows(overview().values).map((r) => `${r.label} ${r.count}`),
    ["확인함 112", "수정됨 3", "미검수 (확인하지 않음) 0"],
  );
});

test("PDF 포함 항목은 서버 include 칸으로 바꾼다. 고르지 않은 칸은 false", () => {
  const all = Object.fromEntries(REPORT_PARTS.map((p) => [p.key, true]));
  assert.deepEqual(reportInclude(all), { regenerated_msds: true, findings_2: true, findings_15: true, components: true, history: true });
  assert.deepEqual(reportInclude({ findings_2: true }), {
    regenerated_msds: false,
    findings_2: true,
    findings_15: false,
    components: false,
    history: false,
  });
});

test("내려받는 파일 이름: 서버가 준 이름 → 없으면 원본 파일 이름", () => {
  assert.equal(reportFileName("attachment; filename*=UTF-8''%ED%99%A9%EC%82%B0_MSDS_%EA%B2%80%ED%86%A0%EA%B2%B0%EA%B3%BC.pdf", "a.pdf", "pdf"), "황산_MSDS_검토결과.pdf");
  assert.equal(reportFileName(null, "25_황산.pdf", "pdf"), "25_황산_MSDS_검토결과.pdf");
  assert.equal(reportFileName(null, "25_황산.PDF", "json"), "25_황산_MSDS_검토결과.json");
});
