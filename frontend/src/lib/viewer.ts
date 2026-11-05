/*
 * 원문 PDF 보기의 계산. 배율과 근거 강조는 화면 없이 시험한다.
 * 배율(scale)은 pdf.js 화면 배율이다. 100%는 종이 실제 크기(1pt = 96/72 px)다.
 */

export const CSS_UNITS = 96 / 72;
export const ZOOM_STEPS = [0.25, 0.33, 0.5, 0.67, 0.75, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3, 4].map((z) => z * CSS_UNITS);
export const MIN_SCALE = ZOOM_STEPS[0];
export const MAX_SCALE = ZOOM_STEPS[ZOOM_STEPS.length - 1];

/** 맞춤(폭·쪽) 또는 고정 배율 */
export type Zoom = "width" | "page" | number;

export const clampScale = (scale: number) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));

/** 화면에 보이는 백분율 */
export const zoomPercent = (scale: number) => Math.round((scale / CSS_UNITS) * 100);

/**
 * 지금 배율에서 한 칸 크게(+1)·작게(-1). 맞춤 배율처럼 칸 사이 값이면 다음 칸으로 가되,
 * 5% 안쪽의 칸은 건너뛴다 (65%에서 + 를 눌러 67%가 되면 바뀐 줄 모른다).
 */
export function stepScale(scale: number, dir: 1 | -1): number {
  if (dir > 0) return ZOOM_STEPS.find((z) => z > scale * 1.05) ?? MAX_SCALE;
  return [...ZOOM_STEPS].reverse().find((z) => z < scale / 1.05) ?? MIN_SCALE;
}

/** 쪽 크기(배율 1)와 보이는 칸 크기로 실제 배율을 정한다. pad는 종이 둘레 여백(한쪽) */
export function resolveScale(
  zoom: Zoom,
  page: { width: number; height: number },
  box: { width: number; height: number },
  pad = 16,
): number {
  if (typeof zoom === "number") return clampScale(zoom);
  const byWidth = (box.width - pad * 2) / page.width;
  if (zoom === "width" || box.height <= 0) return clampScale(byWidth);
  return clampScale(Math.min(byWidth, (box.height - pad * 2) / page.height));
}

/** 강조할 글. 앞에서부터 찾아 처음 걸린 것을 쓴다. once: 쪽에 한 번만 나올 때만 쓴다(짧은 값이 여러 곳에 걸리지 않게) */
export type HighlightPart = { text: string; once?: boolean };
export type Highlight = string | readonly HighlightPart[] | null | undefined;

/**
 * 근거 글이 걸친 글 조각 번호. 공백과 표 칸 구분(|)은 무시하고 쪽 글 전체에서 찾는다.
 * 전처리 글은 표 칸 사이에 | 를 넣지만 원본 PDF의 글자 층에는 없다.
 * 근거 전체가 없으면 줄·칸마다 다시 찾는다 (근거가 여러 줄이나 칸을 이어 붙인 글일 때). 한 글자짜리는 찾지 않는다.
 */
export function matchSpans(texts: string[], highlight: Highlight): number[] {
  if (!highlight) return [];
  const parts: readonly HighlightPart[] = typeof highlight === "string" ? [{ text: highlight }] : highlight;
  const squash = (s: string) => s.replace(/[\s|]+/g, "");
  const starts: number[] = [];
  let joined = "";
  for (const t of texts) {
    starts.push(joined.length);
    joined += squash(t);
  }
  const find = (needle: string) => {
    const hits = new Set<number>();
    let count = 0;
    if (needle.length < 2) return { hits, count };
    for (let at = joined.indexOf(needle); at >= 0; at = joined.indexOf(needle, at + 1)) {
      count += 1;
      const end = at + needle.length;
      texts.forEach((_, i) => {
        const s = starts[i];
        const e = i + 1 < starts.length ? starts[i + 1] : joined.length;
        if (e > s && s < end && e > at) hits.add(i);
      });
    }
    return { hits, count };
  };
  for (const part of parts) {
    const whole = find(squash(part.text));
    if (part.once) {
      if (whole.count === 1) return [...whole.hits].sort((a, b) => a - b);
      continue;
    }
    let hits = whole.hits;
    if (hits.size === 0) {
      hits = new Set(part.text.split(/[\n|]+/).flatMap((piece) => [...find(squash(piece)).hits]));
    }
    if (hits.size > 0) return [...hits].sort((a, b) => a - b);
  }
  return [];
}

/**
 * 추출값 칸의 근거 강조. 근거 줄은 칸이 아니라 행(회사·성분 한 건) 단위라 같은 행의 칸이 모두 같은 줄을 가리킨다.
 * 그래서 값 자체가 쪽에 한 번만 나오면 값을 강조하고, 아니면 근거 줄을 강조한다. 짧은 값은 우연히 걸리므로 쓰지 않는다.
 */
export function fieldHighlight(value: string | number | boolean | null, sourceText: string | null): HighlightPart[] {
  const parts: HighlightPart[] = [];
  const text = typeof value === "string" ? value.trim() : "";
  if (text.replace(/\s+/g, "").length >= 4) parts.push({ text, once: true });
  if (sourceText) parts.push({ text: sourceText });
  return parts;
}

/** 쪽 번호 입력 → 범위 안의 쪽. 숫자가 아니면 null */
export function parsePage(input: string, total: number): number | null {
  const n = Number(input.trim());
  if (!Number.isInteger(n) || total < 1) return null;
  return Math.min(total, Math.max(1, n));
}

type Box = { top: number; bottom: number; left: number; right: number };

/**
 * 근거 자리로 옮길 원문 칸의 스크롤 위치. scrollIntoView 는 바깥 본문까지 움직여 위에 둔 판정 표를 밀어내므로
 * 칸 하나만 움직인다. center: 세로 가운데에 둔다. nearest: 보이면 그대로, 벗어나면 가까운 끝을 맞춘다.
 * 가로는 벗어날 때만 옮긴다. 범위 밖 값은 브라우저가 잘라 준다.
 */
export function scrollInside(view: Box, target: Box, scroll: { top: number; left: number }, block: "center" | "nearest") {
  let { top, left } = scroll;
  if (block === "center") top += target.top - view.top - (view.bottom - view.top - (target.bottom - target.top)) / 2;
  else if (target.top < view.top) top += target.top - view.top;
  else if (target.bottom > view.bottom) top += target.bottom - view.bottom;
  if (target.left < view.left) left += target.left - view.left;
  else if (target.right > view.right) left += target.right - view.right;
  return { top, left };
}

/** scrollInside 를 실제 칸에 적용한다 */
export function scrollWithin(container: HTMLElement, target: HTMLElement, block: "center" | "nearest") {
  const next = scrollInside(
    container.getBoundingClientRect(),
    target.getBoundingClientRect(),
    { top: container.scrollTop, left: container.scrollLeft },
    block,
  );
  container.scrollTop = next.top;
  container.scrollLeft = next.left;
}
