import type { Severity, Verdict } from "@/api/findings-schemas";
import type { Tone } from "@/components/ui";

export const VERDICT_LABEL: Record<Verdict, string> = {
  match: "일치",
  mismatch: "불일치",
  borderline: "경계",
  insufficient: "근거부족",
  warning: "경고",
  outdated: "구버전",
};

export const VERDICT_TONE: Record<Verdict, Tone> = {
  match: "success",
  mismatch: "danger",
  borderline: "warning",
  insufficient: "neutral",
  warning: "warning",
  outdated: "stale",
};

/** 표의 기본 정렬 순서와 거르기 알약 순서 */
export const VERDICT_ORDER: Verdict[] = ["mismatch", "borderline", "insufficient", "warning", "outdated", "match"];

/** 사람이 처리해야 하는 판정 (푸터 안내의 기준) */
export const NEEDS_ACTION: Verdict[] = ["mismatch", "borderline", "insufficient"];

export const SEVERITY_LABEL: Record<NonNullable<Severity>, string> = { high: "높음", medium: "중간", low: "낮음" };

const SEVERITY_RANK: Record<NonNullable<Severity>, number> = { high: 0, medium: 1, low: 2 };

/** 심각도 높음→낮음, 심각도 없음은 맨 뒤 */
export const severityRank = (s: Severity) => (s ? SEVERITY_RANK[s] : 3);

/** 푸터 안내: 항(label)마다 처리하지 않은 판정 건수를 판정 종류 순으로 적는다 */
export function unresolvedNote(counts: Partial<Record<Verdict, number>>, label: string) {
  const parts = VERDICT_ORDER.filter((v) => (counts[v] ?? 0) > 0).map((v) => `${VERDICT_LABEL[v]} ${counts[v]}건`);
  return parts.length === 0
    ? `처리하지 않은 ${label} 판정이 없습니다.`
    : `처리하지 않은 ${label} 판정이 있습니다: ${parts.join(" · ")}. 저장하면 미검토로 남습니다.`;
}
