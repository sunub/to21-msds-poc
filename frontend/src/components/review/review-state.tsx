"use client";

/*
 * 검수 화면의 판정 처리 상태 (확정·예외 승인·의견)와 이력. 문서(job)마다 따로 둔다.
 * 2항·15항·성분별 요약·검토 이력 탭과 저장 화면이 같은 값을 읽는다.
 *
 * 처리 상태는 서버가 가진다: 판정 한 벌(judgment_view)의 reviews 에서 읽고, 확정·예외·되돌리기는
 * POST /api/judgments/{job_id}/reviews 로 보낸다 (seen_version 포함). 더 새 판정 버전이 있으면 409 라서
 * conflict 가 켜지고 화면이 "새로고침해 주세요"를 띄운다.
 * 이력 목록은 계약에 목록 API 가 없어 이 브라우저 탭에 쌓는다 (lib/review-history.ts).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { screenReview } from "@/api/adapt/maps";
import { findingsQuery } from "@/api/findings";
import type { ReviewState, Verdict } from "@/api/findings-schemas";
import { isConflict, judgmentKeys, judgmentViewQuery, postReview } from "@/api/judgments";
import { appendHistory, kstNow, loadHistory, newHistoryId, type HistoryEntry, type HistoryKind } from "@/lib/review-history";
import { useReviewer } from "@/lib/reviewer";
import { isActionable } from "./hazard/verdict";
import { useValidationId } from "./shared/use-validation-id";

export type { HistoryEntry, HistoryKind };

type FindingReview = { state: ReviewState; opinion: string; /** 마지막 검토 뒤에 판정이 바뀜 */ stale: boolean };

export const OPINION_MAX = 500;

export const REVIEW_STATE_LABEL: Record<ReviewState, string> = {
  unreviewed: "미검토",
  confirmed: "확정함",
  exception_approved: "예외 승인함",
  opinion: "의견만 남김",
};

/** 처리를 마친 상태인가. 의견만 남긴 판정은 처리한 것으로 보지 않는다 (미처리에 포함) */
export const isProcessed = (state: ReviewState) => state === "confirmed" || state === "exception_approved";

type ReviewStateValue = {
  /** 판정과 이력을 읽어 오기 전에는 false (그동안은 처리 전 상태로 보인다) */
  ready: boolean;
  getState: (findingId: string) => FindingReview;
  confirm: (findingId: string, opinion?: string) => void;
  /** 의견이 비어 있으면 처리하지 않는다 */
  approveException: (findingId: string, opinion: string) => void;
  undo: (findingId: string) => void;
  /** 처리하지 않은 불일치·경계·근거부족·경고·구버전 건수 (의견만 남긴 판정 포함, 일치·해당 없음·비교 제외 제외) */
  unresolvedCount: (section: 2 | 15) => number;
  unresolvedByVerdict: (section: 2 | 15) => Partial<Record<Verdict, number>>;
  history: HistoryEntry[];
  /** 화면이 읽고 있는 판정 버전. 검토·저장 요청에 seen_version 으로 실린다 */
  version: number | null;
  /** 검토 요청이 409 로 막혔다: 더 새로운 판정 버전이 있다 */
  conflict: boolean;
  /** 판정을 다시 읽는다 (409 안내의 새로고침) */
  refresh: () => void;
};

const Ctx = createContext<ReviewStateValue | null>(null);

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

  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [historyReady, setHistoryReady] = useState(false);
  const [conflict, setConflict] = useState(false);

  // 서버 렌더·첫 그림과 같게 비워 두었다가, 마운트한 뒤에 저장소의 이력을 읽는다
  useEffect(() => {
    setHistory(loadHistory(docId));
    setHistoryReady(true);
  }, [docId]);

  const version = view.data?.version ?? null;

  const getState = useCallback(
    (findingId: string): FindingReview => {
      const { state, opinion, stale } = screenReview(view.data?.reviews[findingId]);
      return { state, opinion, stale };
    },
    [view.data],
  );

  const write = useMutation({
    scope: { id: `review-${docId}` },
    mutationFn: (args: { findingId: string; kind: HistoryKind; action: "불일치 확정" | "확인" | "예외 승인" | "되돌리기"; comment: string | null }) => {
      if (version === null) throw new Error("판정을 아직 읽지 못했습니다.");
      return postReview(docId, {
        finding_id: args.findingId,
        action: args.action,
        comment: args.comment,
        reviewer: reviewerName,
        seen_version: version,
      });
    },
    onSuccess: (_event, args) => {
      setConflict(false);
      void queryClient.invalidateQueries({ queryKey: [...judgmentKeys.all, docId] });
      const f = byId.get(args.findingId);
      if (!f) return;
      const entry: HistoryEntry = {
        id: newHistoryId(),
        at: kstNow(),
        reviewer: reviewerName,
        kind: args.kind,
        findingId: args.findingId,
        section: f.section,
        target: f.item,
        opinion: args.comment ?? "",
      };
      setHistory((h) => appendHistory(docId, entry, h));
    },
    onError: (error) => {
      if (isConflict(error)) setConflict(true);
    },
  });

  const confirm = useCallback(
    (findingId: string, opinion = "") =>
      write.mutate({
        findingId,
        kind: "confirm",
        // 일치 판정은 확인, 그 밖의 판정은 불일치 확정으로 보낸다 (계약에 경계·근거부족 전용 확정 동작이 없다)
        action: byId.get(findingId)?.verdict === "match" ? "확인" : "불일치 확정",
        comment: opinion.trim().slice(0, OPINION_MAX) || null,
      }),
    [write, byId],
  );

  const approveException = useCallback(
    (findingId: string, opinion: string) => {
      const text = opinion.trim().slice(0, OPINION_MAX);
      if (text) write.mutate({ findingId, kind: "exception", action: "예외 승인", comment: text });
    },
    [write],
  );

  const undo = useCallback(
    (findingId: string) => {
      if (getState(findingId).state !== "unreviewed") write.mutate({ findingId, kind: "undo", action: "되돌리기", comment: null });
    },
    [getState, write],
  );

  const unresolvedByVerdict = useCallback(
    (section: 2 | 15) => {
      const counts: Partial<Record<Verdict, number>> = {};
      for (const f of findings) {
        if (f.section === section && isActionable(f.verdict) && !isProcessed(getState(f.finding_id).state)) {
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
    setConflict(false);
    void queryClient.invalidateQueries({ queryKey: [...judgmentKeys.all, docId] });
  }, [queryClient, docId]);

  const ready = historyReady && view.isSuccess;
  const value = useMemo<ReviewStateValue>(
    () => ({ ready, getState, confirm, approveException, undo, unresolvedCount, unresolvedByVerdict, history, version, conflict, refresh }),
    [ready, getState, confirm, approveException, undo, unresolvedCount, unresolvedByVerdict, history, version, conflict, refresh],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useReviewState(): ReviewStateValue {
  const value = useContext(Ctx);
  if (!value) throw new Error("useReviewState 는 ReviewStateProvider 안에서만 쓸 수 있습니다.");
  return value;
}
