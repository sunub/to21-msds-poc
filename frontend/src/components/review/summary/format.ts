import type { Classification, Concentration, Confidence } from "@/api/components-schemas";
import type { Tone } from "@/components/ui";

/** 함량 표시. 표는 "93 ~ 98", 머리줄은 "93~98%"처럼 줄여 쓴다. 모르는 부등호면 원문 그대로 */
export function formatConcentration(c: Concentration, compact = false): string {
  const { min, max, operator, unit } = c;
  let text: string;
  if (operator === ">=" && min !== null) text = `${min} 이상`;
  else if (operator === "<=" && max !== null) text = `${max} 이하`;
  else if (operator === null && min !== null && max !== null) text = min === max ? `${min}` : compact ? `${min}~${max}` : `${min} ~ ${max}`;
  else return c.raw_text;
  if (!compact || !unit) return text;
  return text.endsWith("이상") || text.endsWith("이하") ? text.replace(/^([\d.]+)/, `$1${unit}`) : `${text}${unit}`;
}

/** 분류 한 칩: "피부 1". 구분이 없으면 이름만 ("고압가스") */
export const classificationChip = (c: Classification) => (c.classification ? `${c.name} ${c.classification}` : c.name);

/** 출처별로 묶는다 (들어온 순서 유지) */
export function groupBySource(list: Classification[]): { source: string; chips: string[] }[] {
  const groups: { source: string; chips: string[] }[] = [];
  for (const c of list) {
    const g = groups.find((x) => x.source === c.source) ?? groups[groups.push({ source: c.source, chips: [] }) - 1];
    g.chips.push(classificationChip(c));
  }
  return groups;
}

/** 모든 출처가 같은 분류를 주는가 (출처가 둘 이상일 때만 뜻이 있다) */
export function sourcesAgree(groups: { chips: string[] }[]) {
  return groups.length > 1 && groups.every((g) => g.chips.join("|") === groups[0].chips.join("|"));
}

export const CONFIDENCE: Record<NonNullable<Confidence["level"]>, { label: string; tone: Tone }> = {
  high: { label: "높음", tone: "success" },
  medium: { label: "보통", tone: "warning" },
  low: { label: "낮음", tone: "danger" },
};

export const confidenceView = (c: Confidence) => (c.level ? CONFIDENCE[c.level] : { label: "미확인", tone: "neutral" as Tone });
