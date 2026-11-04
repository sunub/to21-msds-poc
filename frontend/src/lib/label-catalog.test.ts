/* node --test 로 돈다 (pnpm test). */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { categoryById, entriesByCode, labelCategories, rtdgImagesByDivision } from "./label-catalog.ts";

const FRONTEND = fileURLToPath(new URL("../../", import.meta.url));
const PUBLIC = join(FRONTEND, "public");
const classes = (code: string) => entriesByCode(code).map((m) => `${m.category.article} ${m.entry.class}`);

test("catalog.json 은 원본 기록과 같다 (원본에 없는 칸·파일이 있어도 여기서 실패한다)", () => {
  execFileSync(process.execPath, [join(FRONTEND, "scripts/build-label-catalog.mjs"), "--check"], { stdio: "pipe" });
});

test("폴더의 모든 파일이 이전 판을 포함한 카탈로그에 있다", () => {
  const root = join(PUBLIC, "msds-labels");
  const folders = readdirSync(root, { withFileTypes: true }).filter((d) => d.isDirectory() && d.name !== "ghs");
  assert.equal(folders.length, 28);
  for (const { name } of folders) {
    const category = categoryById(name);
    assert.ok(category, name);
    const listed = new Set(
      category.entries.flatMap((e) => [...e.ghs.images, ...e.rtdg.images, ...e.rtdg.required]).map((image) => image.file),
    );
    const files = readdirSync(join(root, name)).filter((file) => file.endsWith(".png"));
    assert.deepEqual([...listed].sort(), files.sort());
    for (const file of listed) assert.ok(existsSync(join(root, name, file)));
    assert.ok(existsSync(join(PUBLIC, category.record)));
  }
});

test("H코드로 그림문자·신호어·예방조치 문구를 찾는다", () => {
  const [match, ...rest] = entriesByCode("H314");
  assert.equal(rest.length, 0);
  assert.equal(match.category.id, "1.2.2_skin_corrosion_irritation");
  assert.equal(match.entry.signal, "위험");
  assert.deepEqual(match.entry.ghs.images.map((i) => i.code), ["GHS05"]);
  assert.deepEqual(match.entry.rtdg.images.map((i) => i.division), ["8"]);
  assert.ok(match.entry.statements.prevention.includes("P280"));
});

test("한 코드가 여러 분류에 걸치면 모두 돌려준다", () => {
  assert.deepEqual(classes("H250"), ["1.1.9 자연발화성 액체 구분 1", "1.1.10 자연발화성 고체 구분 1"]);
});

test("결합 코드와 접미 문자를 나눠 찾는다", () => {
  const routes = entriesByCode("H302+H312").map((m) => m.entry.route);
  assert.deepEqual(routes, ["oral", "dermal"]);
  assert.deepEqual(classes("H360FD"), classes("H360"));
  assert.ok(classes("H360").length > 0);
});

test("P코드는 결합·대괄호 표기 안에서도 찾는다", () => {
  assert.ok(entriesByCode("P378").some((m) => m.entry.statements.response.some((r) => r.includes("[+P378]"))));
  assert.ok(entriesByCode("P330").some((m) => m.entry.statements.response.includes("P301+P330+P331")));
});

test("GHS 코드로 분류를 찾고 모르는 코드는 빈 목록이다", () => {
  assert.ok(classes("GHS04").every((c) => c.startsWith("1.1.5 ")));
  for (const code of ["GHS10", "H999", "", "constructor"]) assert.deepEqual(entriesByCode(code), []);
});

test("급성 독성은 경로별 항목으로 나뉘어 문구가 다르다", () => {
  const [oral, dermal] = [entriesByCode("H300")[0], entriesByCode("H310")[0]];
  assert.equal(oral.entry.routeLabel, "경구");
  assert.equal(dermal.entry.routeLabel, "경피");
  assert.notDeepEqual(oral.entry.statements.prevention, dermal.entry.statements.prevention);
});

test("RTDG 표지의 택1과 함께 표시를 구분한다", () => {
  const liquid = entriesByCode("H225")[0].entry.rtdg;
  assert.equal(liquid.pick, "one_of");
  assert.deepEqual(liquid.images.map((i) => i.variant).sort(), ["black", "white"]);

  const reactive = entriesByCode("H241").find((m) => m.category.id === "1.1.8_self_reactive");
  assert.equal(reactive?.entry.rtdg.pick, "all");

  const peroxide = entriesByCode("H241").find((m) => m.category.id === "1.1.15_organic_peroxides");
  assert.equal(peroxide?.entry.rtdg.pick, "one_of");
  assert.deepEqual(peroxide?.entry.rtdg.required.map((i) => i.file), ["RTDG_1_organic_peroxide_B.png"]);
  assert.equal(peroxide?.entry.rtdg.requiredNote, "5.2와 함께 표시(그리고)");
});

test("그림문자가 없는 구분은 이유를 함께 준다", () => {
  const entry = entriesByCode("H221")[0].entry;
  assert.deepEqual(entry.ghs.images, []);
  assert.equal(entry.ghs.note, "없음");
  assert.equal(entry.rtdg.note, "요구되지 않음");
});

test("이전 판은 조회에서 빠지고 폴더 이름으로만 본다", () => {
  assert.ok(labelCategories.every((c) => !c.supersededBy));
  assert.deepEqual(entriesByCode("H220").map((m) => m.category.id), ["1.1.2_flammable_gases"]);
  const old = categoryById("1.1.2_flammable_gases_superseded");
  assert.equal(old?.supersededBy, "1.1.2_flammable_gases");
  assert.equal(old?.entries[0].rtdg.altNote, "원문 이미지 깨짐");
});

test("운송 등급과 흑백 판으로 RTDG 이미지를 찾는다", () => {
  assert.ok(rtdgImagesByDivision("8").length > 0);
  assert.deepEqual(rtdgImagesByDivision("3", "white").map((i) => i.file), ["RTDG_3_white.png"]);
  assert.deepEqual(rtdgImagesByDivision("3", "black").map((i) => i.file), ["RTDG_3_black.png"]);
  assert.ok(rtdgImagesByDivision("environmental").length > 0);
  assert.ok(rtdgImagesByDivision("1").some((i) => i.file === "RTDG_1_organic_peroxide_B.png"));
  assert.deepEqual(rtdgImagesByDivision("9"), []);
});
