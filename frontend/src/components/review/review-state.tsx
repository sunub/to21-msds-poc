"use client";

/*
 * 검수 화면의 판정 처리 상태 (확정·예외 승인·의견)와 이력. 문서마다 따로 둔다.
 * 2항·15항 탭과, 이어서 만들 검토 이력·저장 전 경고·저장 화면이 같은 값을 읽는다.
 * 서버에는 보내지 않는다. 새로고침해도 남도록 sessionStorage 에 문서별로 저장한다.
 * 저장소를 못 쓰거나 값이 깨져 있어도 화면은 이 탭 안의 값으로 정상 동작한다.
 */
import { useQuery } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { findingsQuery } from "@/api/findings";
import type { ReviewState, Verdict } from "@/api/findings-schemas";
import { useReviewer } from "@/lib/reviewer";
import { isActionable } from "./hazard/verdict";
import { useValidationId } from "./shared/use-validation-id";

export type HistoryKind = "confirm" | "exception" | "undo";

export type HistoryEntry = {
  id: string;
  /** ISO-8601, 시간대 +09:00 */
  at: string;
  reviewer: string;
  kind: HistoryKind;
  findingId: string;
  section: 2 | 15;
  /** 항목명 (예: "급성 독성(흡입)") */
  target: string;
  opinion: string;
};

type FindingReview = { state: ReviewState; opinion: string };

export const OPINION_MAX = 500;

type Stored = { items: Record<string, FindingReview>; history: HistoryEntry[] };

const EMPTY: Stored = { items: {}, history: [] };

const storageKey = (docId: string) => `msds.review-state.${docId}`;

function readStored(docId: string): Stored {
  try {
    const raw = window.sessionStorage.getItem(storageKey(docId));
    if (!raw) return EMPTY;
    const data: unknown = JSON.parse(raw);
    if (typeof data !== "object" || data === null) return EMPTY;
    const { items, history } = data as Partial<Stored>;
    return {
      items: items && typeof items === "object" && !Array.isArray(items) ? items : {},
      history: Array.isArray(history) ? history : [],
    };
  } catch {
    return EMPTY;
  }
}

function writeStored(docId: string, value: Stored) {
  try {
    window.sessionStorage.setItem(storageKey(docId), JSON.stringify(value));
  } catch {
    // 저장소를 못 쓰면 이 탭 안의 상태로만 둔다
  }
}

/** 한국 표준시(+09:00) ISO 문자열 */
function kstNow(): string {
  const shifted = new Date(Date.now() + 9 * 60 * 60 * 1000);
  return `${shifted.toISOString().slice(0, 19)}+09:00`;
}

let seq = 0;
const newId = () => `hist_${Date.now().toString(36)}_${(seq++).toString(36)}`;

export const REVIEW_STATE_LABEL: Record<ReviewState, string> = {
  unreviewed: "미검토",
  confirmed: "확정함",
  exception_approved: "예외 승인함",
  opinion: "의견만 남김",
};

/** 처리를 마친 상태인가. 의견만 남긴 판정은 처리한 것으로 보지 않는다 (미처리에 포함) */
export const isProcessed = (state: ReviewState) => state === "confirmed" || state === "exception_approved";

type ReviewStateValue = {
  /** 저장소에서 읽어 오기 전에는 false (그동안은 처리 전 상태로 보인다) */
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
};

const Ctx = createContext<ReviewStateValue | null>(null);

export function ReviewStateProvider({ docId, children }: { docId: string; children: ReactNode }) {
  const reviewerName = useReviewer() || "미지정";
  const validation = useValidationId(docId);
  // 판정 목록은 두 탭이 쓰는 것과 같은 요청이라 캐시를 나눠 쓴다
  const hazard = useQuery(findingsQuery(docId, validation, { section: 2 })).data;
  const regulation = useQuery(findingsQuery(docId, validation, { section: 15 })).data;
  const findings = useMemo(() => [...(hazard?.items ?? []), ...(regulation?.items ?? [])], [hazard, regulation]);

  const [data, setData] = useState<Stored>(EMPTY);
  const [ready, setReady] = useState(false);

  // 서버 렌더·첫 그림과 같게 비워 두었다가, 마운트한 뒤에 저장소 값을 읽는다
  useEffect(() => {
    setData(readStored(docId));
    setReady(true);
  }, [docId]);

  // ready 가 되기 전에 쓰면 읽어 오기 전의 빈 값이 저장된 값을 덮어쓴다
  useEffect(() => {
    if (ready) writeStored(docId, data);
  }, [docId, data, ready]);

  const byId = useMemo(() => new Map(findings.map((f) => [f.finding_id, f])), [findings]);

  const getState = useCallback(
    (findingId: string): FindingReview =>
      data.items[findingId] ?? { state: byId.get(findingId)?.review_state ?? "unreviewed", opinion: "" },
    [data, byId],
  );

  const record = useCallback(
    (findingId: string, kind: HistoryKind, next: FindingReview) => {
      const f = byId.get(findingId);
      if (!f) return;
      const entry: HistoryEntry = {
        id: newId(),
        at: kstNow(),
        reviewer: reviewerName,
        kind,
        findingId,
        section: f.section,
        target: f.item,
        opinion: next.opinion,
      };
      setData((d) => ({ items: { ...d.items, [findingId]: next }, history: [...d.history, entry] }));
    },
    [byId, reviewerName],
  );

  const confirm = useCallback(
    (findingId: string, opinion = "") =>
      record(findingId, "confirm", { state: "confirmed", opinion: opinion.trim().slice(0, OPINION_MAX) }),
    [record],
  );

  const approveException = useCallback(
    (findingId: string, opinion: string) => {
      const text = opinion.trim().slice(0, OPINION_MAX);
      if (text) record(findingId, "exception", { state: "exception_approved", opinion: text });
    },
    [record],
  );

  const undo = useCallback(
    (findingId: string) => {
      if (getState(findingId).state !== "unreviewed") record(findingId, "undo", { state: "unreviewed", opinion: "" });
    },
    [getState, record],
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

  const value = useMemo<ReviewStateValue>(
    () => ({ ready, getState, confirm, approveException, undo, unresolvedCount, unresolvedByVerdict, history: data.history }),
    [ready, getState, confirm, approveException, undo, unresolvedCount, unresolvedByVerdict, data.history],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useReviewState(): ReviewStateValue {
  const value = useContext(Ctx);
  if (!value) throw new Error("useReviewState 는 ReviewStateProvider 안에서만 쓸 수 있습니다.");
  return value;
}
