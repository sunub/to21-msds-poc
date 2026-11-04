/*
 * 계약 견본 시험: docs/superpowers/specs/contracts/samples/*.json 을 src/api/contract 의 zod 로 파싱한다.
 *   pnpm test:contract
 * 스키마와 zod 가 따로 놀지 않게 하는 시험이다. 새 의존성 없이, dev-mock 서버처럼 typescript 로 .gen/ 에 옮겨 실행한다.
 * 견본 파일 이름 = 5-api·3-consistency 의 $defs 이름 (snake_case). 맞는 zod 가 없는 견본은 실패로 센다.
 * 끝에는 일부러 틀린 견본이 걸리는지도 본다.
 */
import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");
const SAMPLES = path.resolve(ROOT, "..", "docs", "superpowers", "specs", "contracts", "samples");
const ts = createRequire(path.join(ROOT, "package.json"))("typescript");
const GEN = path.join(HERE, ".gen-test");
fs.rmSync(GEN, { recursive: true, force: true });
for (const f of ["contract/api", "contract/common", "contract/consistency"]) {
  const src = fs.readFileSync(path.join(HERE, `${f}.ts`), "utf8");
  const js = ts
    .transpileModule(src, { compilerOptions: { module: "esnext", target: "es2022" } })
    .outputText.replace(/from "(\.\.?\/[^"]+)"/g, 'from "$1.js"');
  fs.mkdirSync(path.dirname(path.join(GEN, `${f}.js`)), { recursive: true });
  fs.writeFileSync(path.join(GEN, `${f}.js`), js);
}
fs.writeFileSync(path.join(GEN, "package.json"), '{"type":"module"}');
const api = await import(pathToFileURL(path.join(GEN, "contract/api.js")).href);
const cons = await import(pathToFileURL(path.join(GEN, "contract/consistency.js")).href);

const camel = (s) => s.replace(/_([a-z])/g, (_, ch) => ch.toUpperCase());
const schemaOf = (name) => (name === "consistency" ? cons.consistency : api[camel(name)]);

let failed = 0;
const issues = (error) => error.issues.slice(0, 5).map((i) => `${i.path.join(".") || "(최상위)"}: ${i.message}`).join("; ");
for (const file of fs.readdirSync(SAMPLES).filter((f) => f.endsWith(".json")).sort()) {
  const name = file.replace(/\.json$/, "");
  const schema = schemaOf(name);
  if (!schema) {
    console.log(`✗ ${name}: 맞는 zod 스키마가 없음`);
    failed += 1;
    continue;
  }
  const result = schema.safeParse(JSON.parse(fs.readFileSync(path.join(SAMPLES, file), "utf8")));
  if (result.success) console.log(`✓ ${name}`);
  else {
    console.log(`✗ ${name}: ${issues(result.error)}`);
    failed += 1;
  }
}

/* 틀린 견본이 걸리는지 */
const view = JSON.parse(fs.readFileSync(path.join(SAMPLES, "judgment_view.json"), "utf8"));
const bad = (label, make, schema = api.judgmentView) => {
  const copy = structuredClone(view);
  make(copy);
  const result = schema.safeParse(copy);
  if (result.success) {
    console.log(`✗ 틀린 견본이 통과함: ${label}`);
    failed += 1;
  } else console.log(`✓ 걸림: ${label}`);
};
bad("contract 가 consistency/1", (v) => (v.consistency.contract = "consistency/1"));
bad("verdict 오타", (v) => (v.consistency.results[0].findings[0].verdict = "맞음"));
bad("finding 의 label 없음", (v) => delete v.consistency.results[0].findings[0].label);
bad("summary 에 경고 없음", (v) => delete v.consistency.results[0].summary["경고"]);
bad("display 칸 모자람", (v) => delete Object.values(v.display)[0].source_pages);
bad("계약에 없는 칸 (reviews.stale 뺌)", (v) => v.reviews && Object.values(v.reviews)[0] && delete Object.values(v.reviews)[0].stale);
const badReq = (label, body) => {
  const result = api.reviewEventRequest.safeParse(body);
  if (result.success) {
    console.log(`✗ 틀린 요청이 통과함: ${label}`);
    failed += 1;
  } else console.log(`✓ 걸림: ${label}`);
};
badReq("예외 승인에 comment 없음", { finding_id: "m0/F2:HH_SKIN_CORR:-", action: "예외 승인", reviewer: "홍", seen_version: 1 });
badReq("seen_event_id 0", { finding_id: "m0/F2:HH_SKIN_CORR:-", action: "확인", reviewer: "홍", seen_version: 1, seen_event_id: 0 });

fs.rmSync(GEN, { recursive: true, force: true });
console.log(failed ? `\n실패 ${failed}건` : "\n모두 통과");
process.exit(failed ? 1 : 0);
