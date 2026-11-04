/* node --test 로 돈다 (pnpm test). 판정 입구가 상황마다 어떤 안내를 고르는지 본다. 값은 모두 가상이다. */
import assert from "node:assert/strict";
import { test } from "node:test";
import type { JudgmentStatus } from "@/api/judgment";
import { gateView, type StatusQuery } from "./judgment-gate.ts";

const DONE = { status: "done" };
const MISSING = new Error("Not Found");
const isApiMissing = (e: unknown) => e === MISSING;

function judgment(patch: Partial<JudgmentStatus> = {}): JudgmentStatus {
  return {
    job_id: "U-20990101-001",
    state: "판정 있음",
    latest_version: 3,
    pending_handoff: null,
    explanations: { done: 0, total: 0 },
    saved_snapshot: null,
    error: null,
    ...patch,
  };
}

function query(patch: Partial<StatusQuery> = {}): StatusQuery {
  return { isPending: false, isError: false, isRefetchError: false, data: judgment(), error: null, ...patch };
}

const view = (doc: { status: string } | undefined, q: StatusQuery) => gateView(doc, q, isApiMissing);

test("문서를 받기 전이나, 끝난 문서의 판정 상태를 받는 중이면 기다린다", () => {
  assert.deepEqual(view(undefined, query()), { kind: "loading" });
  assert.deepEqual(view(DONE, query({ isPending: true, data: undefined })), { kind: "loading" });
});

test("추출이 끝나지 않았으면 판정 상태와 상관없이 추출 전 안내", () => {
  for (const status of ["queued", "running", "failed", "interrupted"]) {
    assert.deepEqual(view({ status }, query({ isPending: true, data: undefined })), { kind: "not-extracted" });
  }
});

test("판정 상태를 한 번도 받지 못했으면 API가 없을 때와 다른 오류를 나눈다", () => {
  assert.deepEqual(view(DONE, query({ isError: true, data: undefined, error: MISSING })), { kind: "not-connected" });
  const other = new Error("500");
  assert.deepEqual(view(DONE, query({ isError: true, data: undefined, error: other })), { kind: "error", error: other });
});

test("다시 묻기만 실패했으면 이전 상태로 보여 주고 offline 을 켠다", () => {
  const q = query({ isError: true, isRefetchError: true, error: new Error("끊김") });
  assert.deepEqual(view(DONE, q), { kind: "ready", doc: DONE, latest: 3, pending: false, offline: true });
});

test("판정 상태마다 안내를 고른다", () => {
  assert.deepEqual(view(DONE, query({ data: judgment({ state: "판정 없음", latest_version: null }) })), { kind: "start" });
  assert.deepEqual(view(DONE, query({ data: judgment({ state: "판정 중", latest_version: null }) })), { kind: "judging" });
  assert.deepEqual(view(DONE, query({ data: judgment({ state: "판정 실패", error: "시간 초과" }) })), {
    kind: "failed",
    error: "시간 초과",
  });
});

test("판정이 있다는데 버전이 없으면 실패로 본다", () => {
  assert.deepEqual(view(DONE, query({ data: judgment({ latest_version: null, error: undefined }) })), { kind: "failed", error: null });
});

test("판정이 있으면 최신 버전과 다시 판정 중인지를 넘긴다", () => {
  assert.deepEqual(view(DONE, query()), { kind: "ready", doc: DONE, latest: 3, pending: false, offline: false });
  assert.deepEqual(view(DONE, query({ data: judgment({ pending_handoff: 4 }) })), { kind: "ready", doc: DONE, latest: 3, pending: true, offline: false });
});
