/* node --test 로 돈다 (pnpm test). WAI-ARIA Tabs 키보드 탐색과 roving tabIndex 규칙을 확인한다. */
import assert from "node:assert/strict";
import { test } from "node:test";
import { activeTabIndex, resolveTabKey, tabIndexFor } from "./tabs.ts";

test("ArrowRight / ArrowLeft 는 끝에서 순환 이동한다", () => {
  assert.equal(resolveTabKey("ArrowRight", 0, 5), 1);
  assert.equal(resolveTabKey("ArrowRight", 4, 5), 0);
  assert.equal(resolveTabKey("ArrowLeft", 2, 5), 1);
  assert.equal(resolveTabKey("ArrowLeft", 0, 5), 4);
});

test("Home / End 는 첫 탭과 마지막 탭으로 바로 이동한다", () => {
  assert.equal(resolveTabKey("Home", 3, 5), 0);
  assert.equal(resolveTabKey("End", 0, 5), 4);
  assert.equal(resolveTabKey("Home", 0, 1), 0);
  assert.equal(resolveTabKey("End", 0, 1), 0);
});

test("관련 없는 키나 빈 탭 목록은 null 을 반환한다", () => {
  for (const key of ["Tab", "Enter", " ", "ArrowDown", "ArrowUp", "Escape", "a"]) {
    assert.equal(resolveTabKey(key, 1, 5), null);
  }
  assert.equal(resolveTabKey("ArrowRight", 0, 0), null);
  assert.equal(resolveTabKey("Home", 0, 0), null);
});

test("roving tabIndex 는 정확히 하나의 탭에만 0을 부여한다", () => {
  const ids = ["hazard", "regulation", "components", "history", "values"];
  const active = activeTabIndex(ids, "regulation");
  assert.equal(active, 1);
  assert.deepEqual(
    ids.map((_, i) => tabIndexFor(i, active)),
    [-1, 0, -1, -1, -1],
  );
});

test("일치하는 값이 없어도 첫 탭이 tabindex=0 진입점을 유지한다", () => {
  const ids = ["hazard", "regulation"];
  const fallback = activeTabIndex(ids, "unknown");
  assert.equal(fallback, 0);
  assert.deepEqual(
    ids.map((_, i) => tabIndexFor(i, fallback)),
    [0, -1],
  );
  assert.equal(activeTabIndex([], "hazard"), -1);
});
