/* 실행: node --test tests/a2-validation.test.cjs. 별도 테스트 프레임워크 불필요. */
const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");
const ts = require("typescript");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");

// 프로젝트 TypeScript와 @/ 별칭을 테스트 전용으로 읽는다.
const resolve = Module._resolveFilename;
Module._resolveFilename = function (request, ...args) {
  const mapped = request.startsWith("@/") ? path.join(__dirname, "../src", request.slice(2)) : request;
  return resolve.call(this, mapped, ...args);
};
for (const extension of [".ts", ".tsx"]) {
  require.extensions[extension] = (mod, filename) => {
    const input = fs.readFileSync(filename, "utf8");
    const output = ts.transpileModule(input, {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
    }).outputText;
    mod._compile(output, filename);
  };
}

const { documentSummarySchema, resultResponseSchema } = require("../src/api/schemas.ts");
const { statusLabel, validationLabel } = require("../src/lib/status.ts");
const { ValidationNotice } = require("../src/components/extract/validation-notice.tsx");
const { QueryClient, QueryClientProvider, QueryObserver } = require("@tanstack/react-query");
const { sectionResultQuery } = require("../src/api/documents.ts");
const { SectionValues } = require("../src/components/extract/section-progress.tsx");

const summary = {
  id: "U-20261103-001", filename: "test.pdf", size: 100, as_of: null, model_tag: "model",
  created_at: "2026-11-03T09:00:00+09:00", updated_at: "2026-11-03T09:01:00+09:00",
  status: "done", stage: "done", error: null, page_count: 1, text_layer: "정상", msds_count: 1,
  stage_index: 4, stage_total: 4,
  counts: { total: 9, queued: 0, running: 0, done: 9, failed: 0, needs_review: 0 }, can_retry: false,
};
const valid = {
  status: "passed", schema_errors: 0, validator_errors: 0, validator_warnings: 0,
  validator_exceptions: 0, failed_sections: [], needs_review: [], unmapped_findings: [],
};

test("기존 응답에 검사 정보가 없으면 완료를 검증 성공으로 표시하지 않는다", () => {
  const doc = documentSummarySchema.parse(summary);
  assert.equal(statusLabel(doc).label, "검증 미확인");
  assert.notEqual(statusLabel(doc).tone, "success");
  assert.equal(validationLabel(null).label, "검증 미확인");
  assert.equal(validationLabel({ status: "unavailable" }).label, "검증 미확인");
});

test("검증 오류와 경고를 파싱하고 실제 화면에 건수를 표시한다", () => {
  const validation = { ...valid, status: "invalid", validator_errors: 8, validator_warnings: 2 };
  const doc = documentSummarySchema.parse({ ...summary, validation });
  assert.equal(statusLabel(doc).tone, "danger");
  const markup = renderToStaticMarkup(React.createElement(ValidationNotice, { status: "done", counts: doc.counts, validation: doc.validation }));
  assert.match(markup, /추출값 검증 오류/);
  assert.match(markup, /TO21 오류 8건/);
  assert.match(markup, /경고 2건/);
  assert.match(markup, /정합성 판정과는 별도/);
  assert.match(markup, /role="alert"/);
});

test("완전한 무오류 검사만 성공이고 불일치하거나 미완성이면 성공으로 표시하지 않는다", () => {
  assert.equal(validationLabel(valid).tone, "success");
  assert.notEqual(validationLabel({ status: "passed" }).tone, "success");
  assert.notEqual(validationLabel({ ...valid, validator_errors: 1 }).tone, "success");
  assert.notEqual(validationLabel({ ...valid, unmapped_findings: [{}] }).tone, "success");
  assert.notEqual(statusLabel({ ...summary, counts: { ...summary.counts, total: 0 }, validation: valid }).tone, "success");
  assert.notEqual(statusLabel({ ...summary, counts: { ...summary.counts, running: 1 }, validation: valid }).tone, "success");
  assert.notEqual(statusLabel({ ...summary, counts: { ...summary.counts, needs_review: 1 }, validation: valid }).tone, "success");
  assert.equal(validationLabel({ ...valid, status: "needs_review", validator_warnings: 1 }).tone, "warning");
  assert.equal(validationLabel({ status: "invalid" }).tone, "danger");
});

test("아직 처리 중이면 최종 검사 알림을 표시하지 않고 결과 API도 검사 값을 유지한다", () => {
  assert.equal(renderToStaticMarkup(React.createElement(ValidationNotice, { status: "running", counts: summary.counts, validation: valid })), "");
  const incomplete = renderToStaticMarkup(React.createElement(ValidationNotice, { status: "done", counts: { ...summary.counts, done: 8 }, validation: valid }));
  assert.match(incomplete, /추출 결과 미확인/);
  assert.doesNotMatch(incomplete, />추출값 검증 통과<\/span>/);
  const result = resultResponseSchema.parse({ to21: {}, needs_review: [], warnings: [], schema_errors: [], to21_validator: [], validation: valid });
  assert.deepEqual(result.validation, valid);
});

test("열린 항 미리보기는 최종 재추출을 채택하면 새 값을 받아 표시한다", { timeout: 3000 }, async (t) => {
  const section = {
    msds_index: 0, section: 1, title: "제품 정보", pages: [1], status: "done",
    needs_review: false, reextracted: false, seconds: .1, errors: [],
  };
  let value = "최초추출값";
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url) => {
    calls.push(url);
    return Response.json({ ...section, check_problems: [], parsed: { name: value } });
  });
  // 캐시가 아직 최신인 동안에도 재추출 완료를 받으면 즉시 새 값을 읽어야 한다.
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } });
  const observer = new QueryObserver(client, sectionResultQuery(summary.id, 0, 1, false));
  const unsubscribe = observer.subscribe(() => {});
  t.after(() => { unsubscribe(); client.clear(); });
  await client.fetchQuery(sectionResultQuery(summary.id, 0, 1, false));
  assert.equal(observer.getCurrentResult().data.parsed.name, "최초추출값");

  const preview = (progress) => renderToStaticMarkup(React.createElement(
    QueryClientProvider, { client }, React.createElement(SectionValues, { docId: summary.id, section: progress }),
  ));
  assert.match(preview(section), /최초추출값/);

  value = "재추출수정값";
  const refreshed = new Promise((resolve) => {
    const stop = observer.subscribe((result) => {
      if (result.data?.parsed.name === value) { stop(); resolve(); }
    });
  });
  observer.setOptions(sectionResultQuery(summary.id, 0, 1, true));
  await refreshed;
  assert.equal(calls.length, 2);
  assert.equal(calls[0], calls[1]);
  const markup = preview({ ...section, reextracted: true });
  assert.match(markup, /재추출수정값/);
  assert.doesNotMatch(markup, /최초추출값/);
});
