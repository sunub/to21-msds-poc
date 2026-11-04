"use client";

/*
 * 판정을 읽는 탭이 함께 쓰는 입구. 판정 상태를 보고 연결 전 · 추출 전 · 판정 없음 · 판정 중 · 실패 · 오류를
 * 같은 말로 보여 주고, 판정이 있을 때만 children 을 그린다. 무엇을 보일지는 lib/judgment-gate 가 정한다.
 */
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { documentDetailQuery } from "@/api/documents";
import { isJudgmentApiMissing, judgmentStatusQuery } from "@/api/judgment";
import type { DocumentDetail } from "@/api/schemas";
import { gateView } from "@/lib/judgment-gate";
import type { ReviewTab } from "@/lib/routes";
import { JudgmentError } from "./error";
import { JudgmentFailed } from "./failed";
import { NotConnected } from "./not-connected";
import { NotExtracted } from "./not-extracted";
import { StartJudgment } from "./start-judgment";

export type JudgmentReady = {
  doc: DocumentDetail;
  latest: number;
  /** 추출값이 바뀌어 다시 판정하는 중 */
  pending: boolean;
  /** 마지막으로 다시 묻기에 실패함 */
  offline: boolean;
};

export function JudgmentGate({
  docId,
  tab,
  paneTitle,
  what,
  loading,
  children,
}: {
  docId: string;
  tab: ReviewTab;
  /** 안내 카드 제목 (탭 이름) */
  paneTitle: string;
  /** 연결 전 안내의 '…을 바로 볼 수 있습니다' 자리 */
  what: string;
  /** 기다리는 동안의 뼈대. 판정 중이면 안내 문장을 받는다 */
  loading: (message?: string) => ReactNode;
  children: (ready: JudgmentReady) => ReactNode;
}) {
  const { data: doc } = useQuery(documentDetailQuery(docId));
  const status = useQuery({ ...judgmentStatusQuery(docId), enabled: doc?.status === "done" });
  const retry = () => void status.refetch();
  const view = gateView(doc, status, isJudgmentApiMissing);

  switch (view.kind) {
    case "loading":
      return loading();
    case "not-extracted":
      return <NotExtracted docId={docId} paneTitle={paneTitle} />;
    case "not-connected":
      return <NotConnected docId={docId} tab={tab} paneTitle={paneTitle} what={what} />;
    case "error":
      return <JudgmentError paneTitle={paneTitle} error={view.error} onRetry={retry} />;
    case "start":
      return <StartJudgment docId={docId} paneTitle={paneTitle} />;
    case "judging":
      return loading("판정하는 중입니다. 끝나면 이 자리에 나타납니다.");
    case "failed":
      return <JudgmentFailed docId={docId} paneTitle={paneTitle} error={view.error} onRetry={retry} />;
    case "ready":
      return children({ doc: view.doc, latest: view.latest, pending: view.pending, offline: view.offline });
  }
}
