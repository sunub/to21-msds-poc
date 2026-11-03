// pdf.js가 실행 중에 읽는 파일(worker, CMap, 표준 글꼴, wasm 해독기, ICC)을 public/pdfjs로 복사한다.
// 폐쇄망에서는 외부 CDN을 쓸 수 없어 정적 빌드(out/)에 함께 넣는다. 설치한 pdfjs-dist 판과 늘 같게 dev·build 전에 다시 복사한다.
import { cpSync, mkdirSync, rmSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";

const root = dirname(createRequire(import.meta.url).resolve("pdfjs-dist/package.json"));
const out = join(import.meta.dirname, "..", "public", "pdfjs");
rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });
cpSync(join(root, "build", "pdf.worker.min.mjs"), join(out, "pdf.worker.min.mjs"));
for (const dir of ["cmaps", "standard_fonts", "wasm", "iccs"]) cpSync(join(root, dir), join(out, dir), { recursive: true });
console.log(`pdfjs 파일 복사: ${out}`);
