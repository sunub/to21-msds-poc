/*
 * 항별 값(parsed, 펼치기 전 중간 형식)을 "칸 경로: 값" 줄로 편다.
 * 모양이 프롬프트를 따라 바뀌므로 항별로 칸을 고정하지 않는다. 근거 줄 번호와 빈 칸은 뺀다.
 */
const EVIDENCE_KEYS = new Set(["line", "lines"]);

export type ValueRow = { path: string; value: string };

export function flattenValues(value: unknown, path = ""): ValueRow[] {
  if (value === null || value === undefined || value === "") return [];
  if (Array.isArray(value)) {
    if (value.every((v) => typeof v !== "object" || v === null)) {
      const items = value.filter((v) => v !== null && v !== "");
      return items.length ? [{ path, value: items.join(", ") }] : [];
    }
    return value.flatMap((v, i) => flattenValues(v, `${path}[${i + 1}]`));
  }
  if (typeof value === "object") {
    return Object.entries(value).flatMap(([k, v]) =>
      EVIDENCE_KEYS.has(k) ? [] : flattenValues(v, path ? `${path}.${k}` : k),
    );
  }
  return [{ path, value: String(value) }];
}
