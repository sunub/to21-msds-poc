/* node --test 로 돈다 (pnpm test). */
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { test } from "node:test";
import { ghsPictogram } from "./ghs.ts";

const CODES = ["GHS01", "GHS02", "GHS03", "GHS04", "GHS05", "GHS06", "GHS07", "GHS08", "GHS09"];

test("스키마의 코드 9개는 모두 public 에 이미지가 있다", () => {
  for (const code of CODES) {
    const pictogram = ghsPictogram(code);
    assert.ok(pictogram, code);
    assert.ok(existsSync(new URL(`../../public${pictogram.src}`, import.meta.url)), pictogram.src);
  }
});

test("대체 글에 코드와 이름이 들어간다", () => {
  assert.equal(ghsPictogram("GHS05")?.alt, "GHS05 부식성 그림문자");
});

test("모르는 코드는 이미지를 주지 않는다", () => {
  for (const code of ["GHS10", "ghs05", "", "constructor", "../GHS05"]) assert.equal(ghsPictogram(code), null);
});
