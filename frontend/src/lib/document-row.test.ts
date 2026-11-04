/* 목록 한 줄(1.1)의 단계·진행·등급·다음 행동. 화면 계약 contracts/6-screens.md 1.1 의 표를 그대로 시험한다. */
import assert from "node:assert/strict";
import { test } from "node:test";
import type { JudgmentBatchItem } from "@/api/judgment";
import type { DocumentSummary, ValuesReview } from "@/api/schemas";
import { type CheckLabel, documentRow as rowOf, failureMessage } from "./document-row.ts";

/* 검사 문구는 lib/status.ts validationLabel 이 정한다 (tests/a2-validation.test.cjs). 여기서는 그 결과를 받는 쪽만 본다 */
const OK: CheckLabel = { tone: "success", label: "검증 통과", detail: "스키마 오류 0건" };
const VALUES: CheckLabel = { tone: "warning", label: "값 확인 5건", detail: "TO21 오류 3건 · 경고 2건" };
const REVIEW: CheckLabel = { tone: "warning", label: "검토 필요", detail: "경고 2건" };
const UNKNOWN: CheckLabel = { tone: "warning", label: "검증 미확인", detail: "추출값 검증 결과를 확인할 수 없습니다." };
const BROKEN: CheckLabel = { tone: "danger", label: "추출 오류", detail: "추출 실패 1항" };
const documentRow = (d: DocumentSummary, j: JudgmentBatchItem | undefined, check: CheckLabel = OK) => rowOf(d, j, check);

const ID = "U-20990101-001";
const NINE = { total: 9, queued: 0, running: 0, done: 9, failed: 0, needs_review: 5 };
const NONE = { total: 0, queued: 0, running: 0, done: 0, failed: 0, needs_review: 0 };
const PASSED = {
  status: "passed" as const, schema_errors: 0, validator_errors: 0, validator_warnings: 0, validator_exceptions: 0,
  failed_sections: [], needs_review: [], unmapped_findings: [],
};

function values(patch: Partial<ValuesReview> = {}): ValuesReview {
  return { state: "미검수", sections_confirmed: 0, sections_total: 9, fields_checked: 0, fields_edited: 0, fields_total: 154, ...patch };
}

function doc(patch: Partial<DocumentSummary> = {}): DocumentSummary {
  return {
    id: ID, filename: "a.pdf", size: 1, as_of: null, model_tag: "m", created_at: "2026-11-04T15:00:00+09:00",
    updated_at: "2026-11-04T15:15:00+09:00", status: "done", stage: "done", error: null, page_count: 4, text_layer: "정상",
    msds_count: 1, stage_index: 4, stage_total: 4, counts: NINE, can_retry: false, validation: PASSED,
    queue_position: null, eta_seconds: null, review_stage: "검수 대기",
    document_extras: { product_name: null, doc_code: null, msds_revision_date: null, composition: null, values_review: values() },
    ...patch,
  };
}

function judged(patch: Partial<JudgmentBatchItem> = {}): JudgmentBatchItem {
  return { job_id: ID, state: "판정 있음", latest_version: 1, unreviewed: 0, saved_snapshot: null, saved_at: null, data_grade: "실버", ...patch };
}

test("끝났지만 저장본이 없으면 '검수 중', 진행 칸에 추출값 검수 상태를 붙인다", () => {
  const row = documentRow(doc(), judged({ state: "판정 없음", latest_version: null }));
  assert.deepEqual(row.stage, { tone: "info", label: "검수 중" });
  assert.equal(row.progress.text, "9 / 9항");
  assert.equal(row.progress.percent, 100);
  assert.equal(row.progress.detail, "추출값 미검수");
  assert.equal(row.note?.text, "검토 필요");   // 검사는 통과지만 사람이 볼 항(needs_review 5)이 있다
});

test("추출값 확인 일부·완료와 판정 미검토 수를 보여 준다", () => {
  const some = documentRow(doc({ document_extras: { ...doc().document_extras!, values_review: values({ state: "일부", sections_confirmed: 3 }) } }), undefined);
  assert.equal(some.progress.detail, "추출값 확인 3 / 9항");
  const all = values({ state: "완료", sections_confirmed: 9, fields_checked: 154 });
  const row = documentRow(doc({ review_stage: "판정으로 넘김", document_extras: { ...doc().document_extras!, values_review: all } }), judged({ unreviewed: 2 }));
  assert.equal(row.progress.detail, "추출값 확인 완료 · 판정 미검토 2건");
});

test("자동 검사 결과는 단계가 아니라 보조 문구로 남고, 받은 문구를 그대로 쓴다", () => {
  const row = documentRow(doc(), judged(), VALUES);
  assert.equal(row.stage.label, "검수 중");
  assert.deepEqual(row.note && { tone: row.note.tone, text: row.note.text }, { tone: "warning", text: "값 확인 5건" });
  assert.match(row.note!.title, /TO21 오류 3건/);
  assert.match(row.note!.title, /검수해도 이 결과는 바뀌지 않습니다/);
  assert.equal(documentRow(doc(), judged(), REVIEW).note?.text, "검토 필요");
  assert.equal(documentRow(doc({ counts: { ...NINE, needs_review: 2 } }), judged(), OK).note?.text, "검토 필요");
  assert.equal(documentRow(doc({ counts: { ...NINE, needs_review: 0 } }), judged(), OK).note, null);
  assert.equal(documentRow(doc(), judged(), UNKNOWN).note?.text, "검증 미확인");
  const failed = documentRow(doc({ counts: { ...NINE, done: 8, failed: 1 }, can_retry: true }), judged(), BROKEN);
  assert.deepEqual([failed.stage.label, failed.note?.tone, failed.note?.text], ["검수 중", "danger", "추출 오류"]);
  assert.equal(failed.action.kind, "link");
});

test("저장본이 있으면 '완료'와 열기", () => {
  const row = documentRow(doc({ review_stage: "판정으로 넘김" }), judged({ saved_snapshot: 1 }));
  assert.deepEqual(row.stage, { tone: "success", label: "완료" });
  assert.deepEqual(row.action, { kind: "link", label: "열기", href: `/save/?doc=${ID}`, primary: false });
});

test("이어서 하기는 사람 구간 상태에 따라 여는 화면이 다르다", () => {
  assert.deepEqual(documentRow(doc(), undefined).action, { kind: "link", label: "검수하기", href: `/review/mode/?doc=${ID}`, primary: true });
  assert.deepEqual(documentRow(doc({ review_stage: "추출값 확인 중" }), undefined).action,
    { kind: "link", label: "이어서 하기", href: `/review/?doc=${ID}&tab=values`, primary: true });
  assert.deepEqual(documentRow(doc({ review_stage: "판정으로 넘김" }), judged()).action,
    { kind: "link", label: "이어서 하기", href: `/review/?doc=${ID}&tab=hazard`, primary: true });
});

test("항을 나누지 못하고 끝난 문서도 막대 값이 숫자다", () => {
  const row = documentRow(doc({ counts: NONE, validation: null }), undefined);
  assert.deepEqual([row.progress.text, row.progress.percent], ["0 / 0항", 0]);
});

test("다시 추출한 문서는 지난 저장본이 있어도 '완료'가 아니다", () => {
  const row = documentRow(doc({ review_stage: "검수 대기" }), judged({ saved_snapshot: 1 }));
  assert.equal(row.stage.label, "검수 중");
  assert.equal(row.action.kind === "link" && row.action.label, "검수하기");
});

test("판정 쪽 상태를 모르면 저장했다고 단정하지 않는다", () => {
  const row = documentRow(doc({ review_stage: "판정으로 넘김" }), undefined);
  assert.equal(row.stage.label, "검수 중");
  assert.equal(row.action.kind === "link" && row.action.label, "이어서 하기");
});

test("모든 항이 실패하면 검수할 값이 없어 다시 시도만 남긴다", () => {
  const row = documentRow(doc({ counts: { ...NINE, done: 0, failed: 9 }, can_retry: true, review_stage: "검수 대기" }), undefined);
  assert.deepEqual(row.stage, { tone: "danger", label: "모든 항 실패" });
  assert.deepEqual(row.action, { kind: "retry" });
  assert.equal(row.progress.detail, null);
});

test("대기·진행 중 막대는 끝낸 단계만큼만 찬다", () => {
  const waiting = documentRow(doc({ status: "queued", stage: null, stage_index: 0, counts: NONE, queue_position: 2, review_stage: null, document_extras: null, validation: null }), undefined);
  assert.deepEqual(waiting.stage, { tone: "neutral", label: "대기" });
  assert.deepEqual([waiting.progress.text, waiting.progress.percent], ["대기 2번째", 0]);
  const pre = documentRow(doc({ status: "running", stage: "preprocess", stage_index: 1, counts: NONE, review_stage: null, document_extras: null, validation: null }), undefined);
  assert.deepEqual([pre.stage.label, pre.progress.text, pre.progress.percent], ["전처리", "1 / 4단계", 0]);
  assert.deepEqual(pre.action, { kind: "link", label: "진행 보기", href: `/extract/?doc=${ID}`, primary: false });
});

test("전처리를 마치고 추출을 기다리면 '추출 대기'이고 막대는 두 단계만큼이다", () => {
  const row = documentRow(doc({ status: "queued", stage: "extract", stage_index: 3, counts: NONE, queue_position: 1, review_stage: null, document_extras: null, validation: null }), undefined);
  assert.deepEqual(row.stage, { tone: "neutral", label: "추출 대기" });
  assert.deepEqual([row.progress.text, row.progress.percent], ["2 / 4단계 끝 · 대기 1번째", 50]);
});

test("추출 중에는 항 진행과 검토 필요 수를 보여 준다", () => {
  const row = documentRow(doc({ status: "running", stage: "extract", stage_index: 3, counts: { ...NONE, total: 9, done: 2, running: 1, queued: 6, needs_review: 2 }, review_stage: null, document_extras: null, validation: null }), undefined);
  assert.deepEqual([row.stage.label, row.progress.text, row.progress.detail], ["추출 중", "2 / 9항", "검토 필요 2항"]);
});

test("실패한 문서는 멈춘 단계와 다시 시도", () => {
  const row = documentRow(doc({ status: "failed", stage: "extract", stage_index: 3, counts: NONE, can_retry: true, error: "x", review_stage: null, document_extras: null, validation: null }), undefined);
  assert.deepEqual(row.stage, { tone: "danger", label: "실패" });
  assert.deepEqual([row.progress.text, row.progress.percent], ["3 / 4단계에서 멈춤", 50]);
  assert.deepEqual(row.action, { kind: "retry" });
});

test("저장까지 끝낸 문서에는 추출 직후 검사 문구를 붙이지 않는다", () => {
  const row = documentRow(doc({ review_stage: "판정으로 넘김" }), judged({ saved_snapshot: 1 }), VALUES);
  assert.equal(row.stage.label, "완료");
  assert.equal(row.note, null);
});

test("항은 모두 확인했어도 손대지 않은 칸이 남으면 저장 화면처럼 '완료'라 하지 않는다", () => {
  const most = values({ state: "완료", sections_confirmed: 9, fields_checked: 120 });
  const row = documentRow(doc({ document_extras: { ...doc().document_extras!, values_review: most } }), undefined);
  assert.equal(row.progress.detail, "추출값 9 / 9항 확인 · 칸 120 / 154");
});

test("제품명을 알면 제목으로 쓰고 파일명은 아래 줄로 내린다", () => {
  const named = documentRow(doc({ document_extras: { ...doc().document_extras!, product_name: "가상 세정액 B" } }), undefined);
  assert.deepEqual([named.title, named.subtitle], ["가상 세정액 B", `a.pdf · ${ID} · 4쪽`]);
  const plain = documentRow(doc(), undefined);
  assert.deepEqual([plain.title, plain.subtitle], ["a.pdf", `${ID} · 4쪽`]);
});

test("실패 원인은 사람이 읽는 말로 바꾸고 원래 오류는 따로 남긴다", () => {
  const raw = "RuntimeError: .env에 RUNPOD_VLLM_BASE_URL가 없습니다.";
  assert.deepEqual(failureMessage(raw, "failed"), { text: "추출 모델 서버에 연결하지 못했습니다. 잠시 뒤 다시 시도해 주세요.", detail: raw });
  assert.equal(failureMessage("APIConnectionError: Connection error.", "failed")?.text, "추출 모델 서버에 연결하지 못했습니다. 잠시 뒤 다시 시도해 주세요.");
  assert.equal(failureMessage("ReadTimeout: timed out", "failed")?.text, "추출 모델 서버가 제때 답하지 않았습니다. 잠시 뒤 다시 시도해 주세요.");
  assert.equal(failureMessage("PdfReadError: EOF marker not found", "failed")?.text, "PDF를 읽지 못했습니다. 파일이 손상되었거나 암호가 걸려 있는지 확인해 주세요.");
  assert.equal(failureMessage("server restarted", "interrupted")?.text, "서버가 다시 시작되어 처리가 멈췄습니다. 다시 시도해 주세요.");
  assert.equal(failureMessage("KeyError: 'x'", "failed")?.text, "처리하는 중 오류가 났습니다. 다시 시도해 주세요.");
  assert.equal(failureMessage(null, "failed"), null);
});
