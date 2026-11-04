/*
 * 15항 탭의 표시 규칙. 화면과 분리한 순수 함수라 서버 없이 시험한다 (regulation.test.ts).
 * 판정을 새로 계산하지 않는다. 받은 판정을 거르고 정렬하고 세기만 한다.
 */
import type { Finding, FindingDisplay, JudgmentView, ReviewAction, ReviewState } from "@/api/judgment";

export type Tone = "danger" | "warning" | "success" | "neutral" | "stale";
type Reviews = Record<string, ReviewState>;

const TODO_ORDER: Record<string, number> = { 불일치: 0, 경계: 1, 근거부족: 2, 경고: 3 };
const SEVERITY_ORDER: Record<string, number> = { 높음: 0, 중간: 1, 낮음: 2 };

/** 구버전은 PoC 판정이 아니다 (D-09·D4). 판정 값과 상관없이 참고로 보인다 */
export const isNote = (f: Finding) => f.verdict === "참고" || f.verdict === "범위 외" || f.type === "구버전";
export const isMatch = (f: Finding) => f.verdict === "일치" && !isNote(f);
export const needsAction = (f: Finding) => !isNote(f) && f.verdict in TODO_ORDER;

/** 처리할 차례인가. 처리했어도 그 뒤 판정이 바뀌었으면(stale) 다시 처리한다 */
export function isUnreviewed(f: Finding, reviews: Reviews) {
  if (!needsAction(f)) return false;
  const r = reviews[f.id];
  return !r || r.status === "미검토" || r.stale;
}

const rank = (f: Finding) => [TODO_ORDER[f.verdict] ?? 9, f.severity ? SEVERITY_ORDER[f.severity] : 3] as const;

export function byPriority(a: Finding, b: Finding) {
  const [av, as] = rank(a);
  const [bv, bs] = rank(b);
  return av - bv || as - bs || a.id.localeCompare(b.id);
}

/** 고른 MSDS 의 15항 판정 */
export function regulationFindings(view: JudgmentView, msdsIndex: number) {
  const result = view.consistency.results.find((r) => r.msds_index === msdsIndex) ?? view.consistency.results[0];
  return result.findings.filter((f) => f.section === "15");
}

export type MatchGroup = { component: string; items: Finding[] };
export type RegulationTable = { todo: Finding[]; matches: MatchGroup[]; notes: Finding[] };

/** 처리 필요 줄은 위에 정렬해서, 일치 줄은 성분별로, 참고 줄은 한 묶음으로 나눈다 */
export function buildTable(
  findings: Finding[],
  display: Record<string, FindingDisplay>,
  { law, todoOnly }: { law: string | null; todoOnly: boolean },
): RegulationTable {
  const shown = findings.filter((f) => !law || f.law_label === law);
  const groups = new Map<string, Finding[]>();
  for (const f of shown.filter(isMatch)) {
    const key = display[f.id]?.component ?? "제품";
    groups.set(key, [...(groups.get(key) ?? []), f]);
  }
  return {
    todo: shown.filter(needsAction).sort(byPriority),
    matches: todoOnly ? [] : [...groups].map(([component, items]) => ({ component, items })),
    notes: todoOnly ? [] : shown.filter(isNote),
  };
}

/** 데이터에 있는 법령만 건수와 함께. 계약의 순서를 따른다 */
const LAW_ORDER = ["산안법", "화관법", "화평법", "위험물법", "폐기물법", "POPs법", "기타 국내", "해외"];
export function lawCounts(findings: Finding[]) {
  return LAW_ORDER.flatMap((law) => {
    const count = findings.filter((f) => f.law_label === law).length;
    return count ? [{ law, count }] : [];
  });
}

export function regulationCounts(findings: Finding[], reviews: Reviews) {
  const count = (test: (f: Finding) => boolean) => findings.filter(test).length;
  return {
    total: findings.length,
    mismatch: count((f) => !isNote(f) && f.verdict === "불일치"),
    border: count((f) => !isNote(f) && f.verdict === "경계"),
    lacking: count((f) => !isNote(f) && f.verdict === "근거부족"),
    warning: count((f) => !isNote(f) && f.verdict === "경고"),
    match: count(isMatch),
    note: count(isNote),
    unreviewed: count((f) => isUnreviewed(f, reviews)),
  };
}

/** 참고 묶음의 이유별 건수. 예: 구버전 3 · 대조만 2 */
export function noteBreakdown(notes: Finding[]) {
  const counts = new Map<string, number>();
  for (const f of notes) {
    const reason = f.type === "구버전" ? "구버전" : (f.out_of_scope_reason ?? f.verdict);
    counts.set(reason, (counts.get(reason) ?? 0) + 1);
  }
  return [...counts].map(([reason, count]) => `${reason} ${count}`).join(" · ");
}

/** 주소에 값이 없을 때 먼저 볼 줄: 미처리 → 처리 필요 → 없음 */
export function defaultFindingId(findings: Finding[], reviews: Reviews) {
  const todo = findings.filter(needsAction).sort(byPriority);
  return (todo.find((f) => isUnreviewed(f, reviews)) ?? todo[0])?.id ?? null;
}

/** 지금 줄 다음의 미처리 줄. 없으면 앞으로 돌아가서 찾는다 */
export function nextUnreviewedId(findings: Finding[], reviews: Reviews, currentId: string | null) {
  const todo = findings.filter((f) => isUnreviewed(f, reviews)).sort(byPriority);
  const others = todo.filter((f) => f.id !== currentId);
  if (!others.length) return null;
  const all = findings.filter(needsAction).sort(byPriority);
  const from = all.findIndex((f) => f.id === currentId);
  return (others.find((f) => all.indexOf(f) > from) ?? others[0]).id;
}

/** 문서 전체(모든 MSDS, 2항·15항)에서 처리할 차례인 판정. 처리할 순서로 */
export function unreviewedFindings(view: JudgmentView) {
  return view.consistency.results.flatMap((r) => r.findings.filter((f) => isUnreviewed(f, view.reviews)).sort(byPriority));
}

export function verdictTone(f: Finding): Tone {
  if (f.type === "구버전") return "stale";
  if (f.verdict === "일치") return "success";
  if (f.verdict === "불일치") return f.severity === "높음" ? "danger" : "warning";
  if (f.verdict === "경계" || f.verdict === "경고") return "warning";
  return "neutral";
}

export function verdictText(f: Finding) {
  if (f.type === "구버전") return "참고 · 구버전";
  if (isNote(f)) return [f.verdict, f.out_of_scope_reason].filter(Boolean).join(" · ");
  return [f.verdict, f.type, f.severity].filter(Boolean).join(" · ");
}

/** 표의 처리 칸. 일치·참고 줄은 처리하지 않아도 되므로 기록이 없으면 비운다 */
export function reviewText(f: Finding, reviews: Reviews) {
  const r = reviews[f.id];
  if (r?.stale) return "다시 확인 필요";
  if (r && r.status !== "미검토") return [r.status, r.reviewer].filter(Boolean).join(" · ");
  return needsAction(f) ? "미처리" : null;
}

/** 줄마다 누를 수 있는 처리. 참고 줄은 판정이 아니어서 없다 */
export function actionsFor(f: Finding): ReviewAction[] {
  if (isNote(f)) return [];
  if (f.verdict === "일치") return ["확인"];
  return ["불일치 확정", "예외 승인"];
}

export const commentRequired = (action: ReviewAction) => action === "예외 승인" || action === "의견";
