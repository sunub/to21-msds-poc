/* node --test 로 돈다 (pnpm test). 오류 본문 세 가지 모양을 스키마가 받는지 본다. */
import assert from "node:assert/strict";
import { test } from "node:test";
import { apiErrorSchema } from "../api/schemas.ts";

test("판정 API의 409 객체를 받고 문장을 읽는다", () => {
  const parsed = apiErrorSchema.parse({
    detail: { message: "넘김 기록 2을 아직 판정하지 않음", latest_version: 1, pending_handoff: 2 },
  });
  assert.deepEqual(parsed.detail, {
    message: "넘김 기록 2을 아직 판정하지 않음",
    latest_version: 1,
    pending_handoff: 2,
  });
});

test("문장과 422 항목 목록은 그대로 받는다", () => {
  assert.equal(apiErrorSchema.parse({ detail: "없는 문서" }).detail, "없는 문서");
  const list = apiErrorSchema.parse({ detail: [{ loc: ["body", "reviewer"], msg: "필수" }] }).detail;
  assert.ok(Array.isArray(list));
});

test("message 없는 객체는 받지 않는다", () => {
  assert.equal(apiErrorSchema.safeParse({ detail: { latest_version: 1 } }).success, false);
});
