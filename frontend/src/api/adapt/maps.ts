/*
 * 계약의 한국어 값 → 화면 내부 값 매핑표 (한 곳에 모은다).
 * 판정 변환 계층(adapt/*)이 이 표만 본다.
 */
import type { Finding } from "../contract/consistency";
import type { ReviewState as ContractReviewState } from "../contract/api";
import type { ReviewState, Severity, Verdict } from "../findings-schemas";

/**
 * 판정. 참고는 처리 대상이 아닌 안내라 "해당 없음"(not_applicable), 범위 외는 "비교 제외"(excluded)에 가장 가깝다.
 * 구버전은 계약에서 verdict 가 아니라 type("구버전") 이므로 screenVerdict 에서 따로 가른다.
 */
const VERDICT: Record<Finding["verdict"], Verdict> = {
  일치: "match",
  불일치: "mismatch",
  경계: "borderline",
  근거부족: "insufficient_evidence",
  참고: "not_applicable",
  "범위 외": "excluded",
};

export function screenVerdict(f: Pick<Finding, "verdict" | "type">): Verdict {
  if (f.verdict === "불일치" && f.type === "구버전") return "outdated";
  return VERDICT[f.verdict];
}

const SEVERITY: Record<NonNullable<Finding["severity"]>, NonNullable<Severity>> = { 높음: "high", 중간: "medium", 낮음: "low" };
export const screenSeverity = (s: Finding["severity"]): Severity => (s ? SEVERITY[s] : null);

/**
 * 검토 상태. 계약의 status 에는 의견이 없다: 미검토이면서 의견(comment)만 있으면 opinion(의견만 남김)으로 본다.
 * 불일치 확정·확인은 확정(confirmed), 예외 승인은 exception_approved.
 */
export function screenReview(r: ContractReviewState | undefined): { state: ReviewState; opinion: string; stale: boolean; historyCount: number } {
  if (!r) return { state: "unreviewed", opinion: "", stale: false, historyCount: 0 };
  const state: ReviewState =
    r.status === "예외 승인" ? "exception_approved" : r.status === "미검토" ? (r.comment ? "opinion" : "unreviewed") : "confirmed";
  return { state, opinion: r.comment ?? "", stale: r.stale, historyCount: r.history_count };
}

/**
 * 화면의 "확정" 버튼이 보내는 검토 동작. 일치 판정은 "확인", 그 밖(불일치·경계·근거부족 등)은 "불일치 확정".
 * 계약에 경계·근거부족 전용 확정 동작이 없어 불일치 확정으로 보낸다.
 */
export const confirmAction = (verdict: Finding["verdict"]) => (verdict === "일치" ? ("확인" as const) : ("불일치 확정" as const));

export const PRODUCT_TYPE = { 단일물질: "single", 혼합물: "mixture", 불명확: "unknown" } as const;
