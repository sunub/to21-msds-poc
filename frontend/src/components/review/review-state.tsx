"use client";

/*
 * 검수 화면의 판정 처리 상태 (확정·예외 승인·의견). 문서(job)마다 따로 둔다.
 * 2항·15항·성분별 요약·검토 이력 탭과 저장 화면이 같은 값을 읽는다.
 *
 * 처리 상태는 서버가 가진다: 판정 한 벌(judgment_view)의 reviews 에서 읽고, 확정·예외·되돌리기는
 * POST /api/judgments/{job_id}/reviews 로 보낸다. 요청에는 화면이 보던 판정 버전(seen_version)과
 * 그 항목의 마지막 이벤트 번호(seen_event_id)를 싣는다. 더 새 판정이 있거나 다른 검토자가 먼저 처리했으면 409 라서
 * conflict 가 켜지고, 화면은 판정 상태를 다시 읽은 뒤 "새로고침해 주세요"를 띄운다.
 * 검토 이력 목록은 서버(GET /history)에서 받는다 (이 파일은 이력을 들고 있지 않는다).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { screenReview } from "@/api/adapt/maps";
import { findingsQuery } from "@/api/findings";
import type { ReviewState, Verdict } from "@/api/findings-schemas";
import { conflictText, isConflict, judgmentKeys, judgmentViewQuery, postReview } from "@/api/judgments";
import { useReviewer } from "@/lib/reviewer";
import { isActionable } from "./hazard/verdict";
import { useValidationId } from "./shared/use-validation-id";

type FindingReview = { state: ReviewState; opinion: string; /** 마지막 처리 뒤에 판정이 바뀜 */ stale: boolean };

export const OPINION_MAX = 500;

export const REVIEW_STATE_LABEL: Record<ReviewState, string> = {
  unreviewed: "미검토",
  confirmed: "확정함",
  exception_approved: "예외 승인함",
  opinion: "의견만 남김",
};

/** 처리를 마친 상태인가. 의견만 남긴 판정은 처리한 것으로 보지 않는다 (미처리에 포함) */
export const isProcessed = (state: ReviewState) => state === "confirmed" || state === "exception_approved";

/** 지금 판정에 대해 처리가 끝난 항목인가: 처리했고 그 뒤 판정이 바뀌지 않았다 (바뀌었으면 다시 미검토 수에 들어간다) */
export const isResolved = (r: FindingReview) => isProcessed(r.state) && !r.stale;

type ReviewStateValue = {
  /** 판정을 읽어 오기 전에는 false (그동안은 처리 전 상태로 보인다) */
  ready: boolean;
  getState: (findingId: string) => FindingReview;
  confirm: (findingId: string, opinion?: string) => void;
  /** 의견이 비어 있으면 처리하지 않는다 */
  approveException: (findingId: string, opinion: string) => void;
  undo: (findingId: string) => void;
  /** 처리하지 않은 불일치·경계·근거부족·경고·구버전 건수 (의견만 남긴 판정과 판정이 바뀐 처리 포함, 일치·해당 없음·비교 제외 제외) */
  unresolvedCount: (section: 2 | 15) => number;
  unresolvedByVerdict: (section: 2 | 15) => Partial<Record<Verdict, number>>;
  /** 화면이 읽고 있는 판정 버전. 검토·저장 요청에 seen_version 으로 실린다 */
  version: number | null;
  /** 검토 요청이 409 로 막혔다: 더 새로운 판정 버전이 있거나 다른 검토자가 먼저 처리했다 */
  conflict: boolean;
  /** 409 의 이유를 사용자 말로 (conflict 가 켜졌을 때) */
  conflictMessage: string;
  /** 판정을 다시 읽는다 (409 안내의 새로고침) */
  refresh: () => void;
};

const Ctx = createContext<ReviewStateValue | null>(null);

type WriteArgs = { findingId: string; action: "불일치 확정" | "확인" | "예외 승인" | "되돌리기"; comment: string | null };

/** enabled 가 false 면 판정을 새로 부르지 않는다 (판정이 필요 없는 추출값 탭). 이미 받아 둔 값은 그대로 쓴다 */
export function ReviewStateProvider({ docId, enabled = true, children }: { docId: string; enabled?: boolean; children: ReactNode }) {
  const reviewerName = useReviewer() || "미지정";
  const validation = useValidationId(docId);
  const queryClient = useQueryClient();
  // 판정 목록은 여러 탭이 쓰는 것과 같은 요청이라 캐시를 나눠 쓴다
  const view = useQuery({ ...judgmentViewQuery(docId, validation), enabled });
  const hazard = useQuery({ ...findingsQuery(docId, validation, { section: 2 }), enabled }).data;
  const regulation = useQuery({ ...findingsQuery(docId, validation, { section: 15 }), enabled }).data;
  const findings = useMemo(() => [...(hazard?.items ?? []), ...(regulation?.items ?? [])], [hazard, regulation]);
  const byId = useMemo(() => new Map(findings.map((f) => [f.finding_id, f])), [findings]);

  const [conflictMessage, setConflictMessage] = useState<string | null>(null);
  const version = view.data?.version ?? null;

  const getState = useCallback(
    (findingId: string): FindingReview => {
      const { state, opinion, stale } = screenReview(view.data?.reviews[findingId]);
      return { state, opinion, stale };
    },
    [view.data],
  );

  const viewKey = judgmentKeys.view(docId, validation);
  const write = useMutation({
    // 같은 문서의 쓰기는 차례로 보낸다: 앞 요청이 끝나고 판정을 다시 읽은 뒤에 다음 요청의 seen_event_id 를 정한다
    scope: { id: `review-${docId}` },
    mutationFn: (args: WriteArgs) => {
      // 실행하는 시점의 판정에서 읽는다 (앞 요청이 방금 끝났어도 최신 번호를 쓴다)
      const current = queryClient.getQueryData<NonNullable<typeof view.data>>(viewKey);
      if (!current) throw new Error("판정을 아직 읽지 못했습니다.");
      return postReview(docId, {
        finding_id: args.findingId,
        action: args.action,
        comment: args.comment,
        reviewer: reviewerName,
        seen_version: current.version,
        // 보고 있던 항목의 마지막 이벤트 번호. 기록이 없는 항목은 null (기록이 없는 것을 봤다는 뜻)
        seen_event_id: current.reviews[args.findingId]?.last_event_id ?? null,
      });
    },
    // 판정과 상태·이력·저장 요약을 다시 읽는다. 읽기가 끝날 때까지 기다려 다음 쓰기가 최신 값을 보게 한다
    onSuccess: async () => {
      setConflictMessage(null);
      await queryClient.invalidateQueries({ queryKey: [...judgmentKeys.all, docId] });
    },
    onError: async (error) => {
      if (!isConflict(error)) return;
      // 409 본문(conflict_response)이 말하는 대로 판정 상태를 다시 읽는다
      setConflictMessage(conflictText(error));
      await queryClient.invalidateQueries({ queryKey: judgmentKeys.status(docId) });
    },
  });

  const confirm = useCallback(
    (findingId: string, opinion = "") => {
      const verdict = view.data?.consistency.results[0].findings.find((f) => f.id === findingId)?.verdict;
      if (!verdict) return;
      write.mutate({
        findingId,
        // 일치·참고·범위 외는 확인, 불일치·경계·근거부족·경고는 불일치 확정 (그 밖은 서버가 422)
        action: verdict === "일치" || verdict === "참고" || verdict === "범위 외" ? "확인" : "불일치 확정",
        comment: opinion.trim().slice(0, OPINION_MAX) || null,
      });
    },
    [write, view.data],
  );

  const approveException = useCallback(
    (findingId: string, opinion: string) => {
      const text = opinion.trim().slice(0, OPINION_MAX);
      if (text) write.mutate({ findingId, action: "예외 승인", comment: text });
    },
    [write],
  );

  const undo = useCallback(
    (findingId: string) => {
      if (getState(findingId).state !== "unreviewed") write.mutate({ findingId, action: "되돌리기", comment: null });
    },
    [getState, write],
  );

  const unresolvedByVerdict = useCallback(
    (section: 2 | 15) => {
      const counts: Partial<Record<Verdict, number>> = {};
      for (const f of findings) {
        if (f.section === section && isActionable(f.verdict) && !isResolved(getState(f.finding_id))) {
          counts[f.verdict] = (counts[f.verdict] ?? 0) + 1;
        }
      }
      return counts;
    },
    [findings, getState],
  );

  const unresolvedCount = useCallback(
    (section: 2 | 15) => Object.values(unresolvedByVerdict(section)).reduce((a, b) => a + b, 0),
    [unresolvedByVerdict],
  );

  const refresh = useCallback(() => {
    setConflictMessage(null);
    void queryClient.invalidateQueries({ queryKey: [...judgmentKeys.all, docId] });
  }, [queryClient, docId]);

  const ready = view.isSuccess;
  const value = useMemo<ReviewStateValue>(
    () => ({ ready, getState, confirm, approveException, undo, unresolvedCount, unresolvedByVerdict, version, conflict: conflictMessage !== null, conflictMessage: conflictMessage ?? "", refresh }),
    [ready, getState, confirm, approveException, undo, unresolvedCount, unresolvedByVerdict, version, conflictMessage, refresh],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useReviewState(): ReviewStateValue {
  const value = useContext(Ctx);
  if (!value) throw new Error("useReviewState 는 ReviewStateProvider 안에서만 쓸 수 있습니다.");
  return value;
}
