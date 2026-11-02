import type { FindingSummary } from "@/api/findings-schemas";
import { VERDICT_ORDER, severityRank } from "../hazard/verdict";

/** 판정 표 정렬 기준. 심각도는 거르기에 쓰지 않고 정렬에만 쓴다 */
export type SortKey = "verdict" | "severity";

export const SORTS: { id: SortKey; label: string }[] = [
  { id: "verdict", label: "판정 순" },
  { id: "severity", label: "심각도 순" },
];

const verdictRank = (v: FindingSummary["verdict"]) => VERDICT_ORDER.indexOf(v);

/** 기본은 판정 종류 순(불일치→경계→근거부족→경고→구버전→일치) 안에서 심각도 높음→낮음. 심각도 순은 심각도를 먼저 본다. */
export function sortRows(rows: FindingSummary[], sort: SortKey) {
  return [...rows].sort((a, b) =>
    sort === "severity"
      ? severityRank(a.severity) - severityRank(b.severity) || verdictRank(a.verdict) - verdictRank(b.verdict)
      : verdictRank(a.verdict) - verdictRank(b.verdict) || severityRank(a.severity) - severityRank(b.severity),
  );
}
