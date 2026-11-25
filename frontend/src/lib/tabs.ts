/*
 * WAI-ARIA Tabs 키보드 내비게이션 순수 규칙 (ArrowLeft, ArrowRight, Home, End + roving tabIndex).
 * DOM 없이 node --test 로 검증한다 (tabs.test.ts).
 */

/**
 * 방향키·Home·End 입력에 대한 다음 탭 인덱스를 계산한다.
 * 처리 대상이 아닌 키이거나 항목이 비어 있으면 null 을 돌려준다.
 */
export function resolveTabKey(key: string, currentIndex: number, count: number): number | null {
  if (count <= 0) return null;
  const clamped = Math.min(Math.max(0, currentIndex), count - 1);
  switch (key) {
    case "ArrowRight":
      return (clamped + 1) % count;
    case "ArrowLeft":
      return (clamped - 1 + count) % count;
    case "Home":
      return 0;
    case "End":
      return count - 1;
    default:
      return null;
  }
}

/**
 * 현재 선택된 탭의 인덱스. 일치하는 항목이 없으면 첫 번째 탭(0)을 포커스 진입점으로 삼아
 * 키보드 사용자가 tablist 로 들어오지 못하는 상황을 막는다.
 */
export function activeTabIndex(ids: readonly string[], value: string): number {
  if (ids.length === 0) return -1;
  const idx = ids.indexOf(value);
  return idx >= 0 ? idx : 0;
}

/** Roving tabindex: 활성 탭만 0, 나머지는 -1 */
export function tabIndexFor(index: number, activeIndex: number): 0 | -1 {
  return index === activeIndex ? 0 : -1;
}
