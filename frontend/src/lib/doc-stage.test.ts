import assert from "node:assert/strict";
import { test } from "node:test";
import { chunk, documentStage, gradeLabel, isJobId, type DocLike } from "./doc-stage.ts";
import { headerNote, judgmentLabel, reviewNote, saveNote, summaryParts } from "./doc-glance.ts";

const doc = (patch: Partial<DocLike> = {}): DocLike => ({ id: "U-20261103-001", status: "done", stage_index: 4, stage_total: 4, ...patch });

test("추출 중은 응답의 단계 수를 그대로 쓴다", () => {
  assert.equal(documentStage(doc({ status: "running", stage_index: 3, stage_total: 4 })).label, "추출 중 3/4");
  assert.equal(documentStage(doc({ status: "running", stage_index: 3, stage_total: 5 })).label, "추출 중 3/5");
  assert.equal(documentStage(doc({ status: "running" })).action, "진행 보기");
});

test("대기는 순번을 줄 때만 n번째", () => {
  assert.equal(documentStage(doc({ status: "queued", queue_position: 2 })).label, "대기 2번째");
  assert.equal(documentStage(doc({ status: "queued", queue_position: null })).label, "대기");
});

test("실패·중단은 진행 보기", () => {
  const failed = documentStage(doc({ status: "failed" }));
  assert.deepEqual([failed.label, failed.action, failed.tone], ["실패", "진행 보기", "danger"]);
  assert.equal(documentStage(doc({ status: "interrupted" })).label, "멈춤");
});

test("완료 + 저장본 없음 = 검수 중, 이어서 하기 (추출값 검수 상태는 알 때만)", () => {
  assert.equal(documentStage(doc(), { saved_snapshot: null }).label, "검수 중");
  assert.equal(documentStage(doc({ values_review: { state: "일부" } }), { saved_snapshot: null }).label, "검수 중 · 일부");
  assert.equal(documentStage(doc(), { saved_snapshot: null }).action, "이어서 하기");
  // 판정 서버가 없어도(judgment 없음) 저장본 없음으로 본다
  assert.equal(documentStage(doc()).label, "검수 중");
});

test("저장본이 있으면 완료 · 열기", () => {
  const s = documentStage(doc(), { saved_snapshot: 2, data_grade: "골드" });
  assert.deepEqual([s.label, s.action, s.target], ["완료", "열기", "hazard"]);
});

test("이어서 하기는 사람 구간에 따라 이어 열 곳이 다르다", () => {
  assert.equal(documentStage(doc({ review_stage: "추출값 확인 중" })).target, "values");
  assert.equal(documentStage(doc({ review_stage: "판정으로 넘김" })).target, "hazard");
  assert.equal(documentStage(doc({ review_stage: "검수 대기" })).target, "mode");
  assert.equal(documentStage(doc({ review_stage: null })).target, "mode");
});

test("모든 항이 실패한 완료 문서는 검수할 값이 없다", () => {
  const s = documentStage(doc(), { saved_snapshot: null }, true);
  assert.deepEqual([s.label, s.action, s.normal], ["실패", "진행 보기", false]);
});

test("등급은 서버 값만, 없으면 -", () => {
  assert.equal(gradeLabel({ saved_snapshot: null, data_grade: "실버" }), "실버");
  assert.equal(gradeLabel(null), "-");
  assert.equal(gradeLabel({ saved_snapshot: null }), "-");
});

test("판정 요약 호출은 200개씩, 작업 번호만", () => {
  assert.deepEqual(chunk(Array.from({ length: 450 }, (_, i) => i)).map((c) => c.length), [200, 200, 50]);
  assert.equal(chunk([]).length, 0);
  assert.equal(isJobId("U-20261103-001"), true);
  assert.equal(isJobId("demo"), false);
});

test("머리줄 글: 값이 없는 칸은 쓰지 않는다", () => {
  const d = { filename: "a.pdf", page_count: 12 };
  assert.equal(headerNote(d, null, null), "a.pdf · 12쪽");
  assert.equal(headerNote({ ...d, doc_code: "KZ-1", values_review: { state: "미검수" } }, "실버", "판정 미검토 3건"), "KZ-1 · a.pdf · 12쪽 · 실버 · 미검수 · 판정 미검토 3건");
  assert.equal(headerNote({ ...d, page_count: null }, null, null), "a.pdf · 쪽 수 확인 중");
});

test("판정 상태 칸", () => {
  assert.equal(judgmentLabel(null), null);
  assert.equal(judgmentLabel({ state: "판정 중" }), "판정 중");
  assert.equal(judgmentLabel({ state: "판정 있음", unreviewed: 3 }), "판정 미검토 3건");
  assert.equal(judgmentLabel({ state: "판정 있음", unreviewed: 3 }, 0), "판정 모두 처리");
  assert.equal(judgmentLabel({ state: "판정 있음" }), "판정 있음");
});

test("단계 띠 검수 칸: 추출값 확인 건너뜀 + 판정 확인 중", () => {
  const d = { filename: "a.pdf", page_count: 1, review_stage: "판정으로 넘김" as const };
  assert.equal(reviewNote(d, { state: "판정 있음", unreviewed: 2 }), "· 추출값 확인 건너뜀 · 판정 확인 중");
  assert.equal(reviewNote(d, { state: "판정 있음", unreviewed: 0 }), "· 추출값 확인 건너뜀 · 판정 모두 처리");
  assert.equal(reviewNote(d, { state: "판정 중" }), "· 추출값 확인 건너뜀 · 판정 중");
  assert.equal(reviewNote({ filename: "a", page_count: 1 }, null), undefined);
  assert.equal(reviewNote({ filename: "a", page_count: 1, values_review: { state: "완료" } }, { state: "판정 없음" }), "· 추출값 확인함 · 판정 전");
  assert.equal(saveNote({ state: "판정 있음", saved_snapshot: 2 }), "· 저장본 2");
  assert.equal(saveNote({ state: "판정 있음", saved_snapshot: null }), undefined);
});

test("요약 줄: 지식은 판정이 있을 때만", () => {
  assert.deepEqual(summaryParts({ revisionDate: "2022-06-29", composition: { type: "혼합물", count: 2 }, asOf: "2026-11-03" }), ["개정일 2022-06-29", "혼합물(성분 2)", "기준일 2026-11-03"]);
  assert.deepEqual(summaryParts({ asOf: "2026-11-03", knowledge: { provider: "reference", version: "ref-1" } }), ["기준일 2026-11-03", "지식 reference / ref-1"]);
});
