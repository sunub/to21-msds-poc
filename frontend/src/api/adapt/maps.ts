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
  경고: "warning",
  참고: "not_applicable",
  "범위 외": "excluded",
};

export function screenVerdict(f: Pick<Finding, "verdict" | "type" | "out_of_scope_reason">): Verdict {
  if (f.verdict === "불일치" && f.type === "구버전") return "outdated";
  // 범위 외의 해당 없음은 해당 없음 건수에, 대조만·구버전 제외·해외 규제는 비교 제외 건수에 센다 (화면 2.3 범위 외 · 비교 제외 7건 (해당 없음 5 · 대조 2))
  if (f.verdict === "범위 외" && f.out_of_scope_reason === "해당 없음") return "not_applicable";
  return VERDICT[f.verdict];
}

const SEVERITY: Record<NonNullable<Finding["severity"]>, NonNullable<Severity>> = { 높음: "high", 중간: "medium", 낮음: "low" };
export const screenSeverity = (s: Finding["severity"]): Severity => (s ? SEVERITY[s] : null);

/**
 * 검토 상태. 계약의 status 에는 의견이 없다: 미검토이면서 의견(comment)만 있으면 opinion(의견만 남김)으로 본다.
 * 불일치 확정·확인은 확정(confirmed), 예외 승인은 exception_approved.
 */
export function screenReview(r: ContractReviewState | undefined): {
  state: ReviewState;
  opinion: string;
  stale: boolean;
  historyCount: number;
  lastEventId: number | null;
} {
  if (!r) return { state: "unreviewed", opinion: "", stale: false, historyCount: 0, lastEventId: null };
  const state: ReviewState =
    r.status === "예외 승인" ? "exception_approved" : r.status === "미검토" ? (r.comment ? "opinion" : "unreviewed") : "confirmed";
  return { state, opinion: r.comment ?? "", stale: r.stale, historyCount: r.history_count, lastEventId: r.last_event_id };
}

/**
 * 화면의 확정 버튼이 보내는 검토 동작 (계약 review_event_request).
 * 확인은 일치·참고·범위 외에만, 불일치 확정은 불일치·경계·근거부족·경고에만 된다 (그 밖은 서버가 422).
 */
export const confirmAction = (verdict: Finding["verdict"]) =>
  verdict === "일치" || verdict === "참고" || verdict === "범위 외" ? ("확인" as const) : ("불일치 확정" as const);

export const PRODUCT_TYPE = { 단일물질: "single", 혼합물: "mixture", 불명확: "unknown" } as const;
