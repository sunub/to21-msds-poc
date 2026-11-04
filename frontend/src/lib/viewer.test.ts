import assert from "node:assert/strict";
import { test } from "node:test";
import { CSS_UNITS, MAX_SCALE, MIN_SCALE, matchSpans, parsePage, resolveScale, scrollInside, stepScale, zoomPercent } from "./viewer.ts";

test("한 칸씩 크게·작게, 끝에서는 멈춘다", () => {
  assert.equal(zoomPercent(stepScale(CSS_UNITS, 1)), 110);
  assert.equal(zoomPercent(stepScale(CSS_UNITS, -1)), 90);
  assert.equal(stepScale(MAX_SCALE, 1), MAX_SCALE);
  assert.equal(stepScale(MIN_SCALE, -1), MIN_SCALE);
});

test("맞춤 배율처럼 칸 사이 값에서는 가까운 다음 칸으로 간다", () => {
  const between = 1.18 * CSS_UNITS;
  assert.equal(zoomPercent(stepScale(between, 1)), 125);
  assert.equal(zoomPercent(stepScale(between, -1)), 110);
  const fit = 0.65 * CSS_UNITS;
  assert.equal(zoomPercent(stepScale(fit, 1)), 75);
  assert.equal(zoomPercent(stepScale(fit, -1)), 50);
});

test("폭 맞춤과 쪽 맞춤", () => {
  const page = { width: 600, height: 800 };
  assert.equal(resolveScale("width", page, { width: 632, height: 300 }), 1);
  assert.equal(resolveScale("page", page, { width: 632, height: 432 }), 0.5);
  assert.equal(resolveScale("page", page, { width: 632, height: 100 }), MIN_SCALE);
  assert.equal(resolveScale(99, page, { width: 1, height: 1 }), MAX_SCALE);
});

test("근거 글은 공백을 무시하고 여러 조각에 걸쳐 찾는다", () => {
  const texts = ["CAS 번호", "7647-", "01-0", "함량", "35 ~ 37"];
  assert.deepEqual(matchSpans(texts, "7647-01-0"), [1, 2]);
  assert.deepEqual(matchSpans(texts, "35~37"), [4]);
  assert.deepEqual(matchSpans(texts, "없는 글"), []);
  assert.deepEqual(matchSpans(texts, "%"), []);
  assert.deepEqual(matchSpans(texts, null), []);
});

test("근거 전체가 없으면 줄마다 찾는다", () => {
  const texts = ["제품명 : 가상", "다른 글", "제조자 : 가상화학"];
  assert.deepEqual(matchSpans(texts, "제품명 : 가상\n제조자 : 가상화학"), [0, 2]);
});

test("쪽 번호 입력", () => {
  assert.equal(parsePage("3", 5), 3);
  assert.equal(parsePage(" 9 ", 5), 5);
  assert.equal(parsePage("0", 5), 1);
  assert.equal(parsePage("둘", 5), null);
  assert.equal(parsePage("2.5", 5), null);
});

test("근거 줄로 옮길 때 원문 칸 안에서만 스크롤 위치를 정한다", () => {
  const view = { top: 100, bottom: 500, left: 0, right: 400 };
  // 가운데: 칸 높이 400, 줄 높이 20 → 줄 위가 칸 위에서 190 아래에 오게 한다
  assert.deepEqual(scrollInside(view, { top: 900, bottom: 920, left: 10, right: 50 }, { top: 0, left: 0 }, "center"), { top: 610, left: 0 });
  // 가까운 쪽: 이미 보이면 그대로, 아래로 벗어나면 아래 끝을 맞춘다
  assert.deepEqual(scrollInside(view, { top: 200, bottom: 220, left: 10, right: 50 }, { top: 30, left: 0 }, "nearest"), { top: 30, left: 0 });
  assert.deepEqual(scrollInside(view, { top: 520, bottom: 540, left: 10, right: 50 }, { top: 30, left: 0 }, "nearest"), { top: 70, left: 0 });
  assert.deepEqual(scrollInside(view, { top: 60, bottom: 80, left: 10, right: 50 }, { top: 30, left: 0 }, "nearest"), { top: -10, left: 0 });
  // 가로는 벗어날 때만 옮긴다
  assert.deepEqual(scrollInside(view, { top: 200, bottom: 220, left: 380, right: 450 }, { top: 0, left: 5 }, "nearest"), { top: 0, left: 55 });
});
