"use client";

/*
 * 판정을 읽는 탭(2항, 15항, 성분별 요약)이 함께 쓰는 입구. 판정 상태를 보고
 * 연결 전 · 추출 전 · 판정 없음 · 판정 중 · 실패 · 오류를 같은 말로 보여 주고, 판정이 있을 때만 children 을 그린다.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import type { ReactNode } from "react";
import { ApiContractError, ApiRequestError } from "@/api/client";
import { documentDetailQuery } from "@/api/documents";
import type { DocumentDetail } from "@/api/schemas";
import { isJudgmentApiMissing, judgmentKeys, judgmentStatusQuery, postToJudgment, type JudgmentStatus } from "@/api/judgment";
import { Pane } from "@/components/shell/layout";
import { Button, buttonStyles } from "@/components/ui";
import { useReviewer } from "@/lib/reviewer";
import { routes, type ReviewTab } from "@/lib/routes";

/** 처음 켤 때만 쓰는 대역 안내 링크. 제품 빌드에서는 조건이 거짓이라 빠진다 */
const DEV = process.env.NODE_ENV === "development";

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

  if (!doc || (doc.status === "done" && status.isPending)) return loading();
  if (doc.status !== "done") {
    return (
      <JudgmentNotice paneTitle={paneTitle} title="추출이 끝나야 판정할 수 있습니다">
        <Link href={routes.extract(docId)} className={buttonStyles()}>
          추출 진행 보기
        </Link>
      </JudgmentNotice>
    );
  }
  if (status.isError && !status.data) {
    if (isJudgmentApiMissing(status.error)) return <NotConnected docId={docId} tab={tab} paneTitle={paneTitle} what={what} />;
    return <JudgmentError paneTitle={paneTitle} error={status.error} onRetry={() => void status.refetch()} />;
  }
  const data = status.data as JudgmentStatus;

  if (data.state === "판정 없음") return <StartJudgment docId={docId} paneTitle={paneTitle} />;
  if (data.state === "판정 중") return loading("판정하는 중입니다. 끝나면 이 자리에 나타납니다.");
  if (data.state === "판정 실패" || data.latest_version === null) {
    return (
      <JudgmentNotice paneTitle={paneTitle} title="판정하지 못했습니다" alert>
        <p className="break-words text-mut">
          문서 {docId}
          {data.error && ` · ${data.error}`}
        </p>
        <p className="text-mut">다시 불러와도 같으면 개발 담당에게 위 내용을 알려 주세요.</p>
        <Button onClick={() => void status.refetch()}>다시 불러오기</Button>
      </JudgmentNotice>
    );
  }
  return children({ doc, latest: data.latest_version, pending: data.pending_handoff !== null, offline: status.isRefetchError });
}

function StartJudgment({ docId, paneTitle }: { docId: string; paneTitle: string }) {
  const client = useQueryClient();
  const reviewer = useReviewer();
  const start = useMutation({
    mutationFn: () => postToJudgment(docId, reviewer),
    onSuccess: () => client.invalidateQueries({ queryKey: judgmentKeys.status(docId) }),
  });
  return (
    <JudgmentNotice paneTitle={paneTitle} title="아직 판정하지 않았습니다">
      <p className="text-mut">추출값을 먼저 확인하거나, 지금 값으로 바로 판정할 수 있습니다.</p>
      <div className="flex flex-wrap justify-center gap-2">
        <Link href={routes.review(docId, "values")} className={buttonStyles()}>
          추출값 확인
        </Link>
        <Button variant="primary" disabled={!reviewer || start.isPending} onClick={() => start.mutate()}>
          {start.isPending ? "넘기는 중…" : "판정으로 넘기기"}
        </Button>
      </div>
      {!reviewer && <p className="text-sm text-mut">판정으로 넘기려면 머리줄에서 검토자 이름을 정해 주세요.</p>}
      {start.isError && (
        <p role="alert" className="text-sm break-words text-red">
          {isJudgmentApiMissing(start.error) ? "판정으로 넘기는 서버 기능이 아직 연결되지 않았습니다." : `넘기지 못했습니다: ${start.error.message}`}
        </p>
      )}
    </JudgmentNotice>
  );
}

function NotConnected({ docId, tab, paneTitle, what }: { docId: string; tab: ReviewTab; paneTitle: string; what: string }) {
  return (
    <JudgmentNotice paneTitle={paneTitle} title="판정 서비스가 아직 연결되지 않았습니다">
      <p className="text-mut">판정 API가 준비되면 이 화면에서 {what}을 바로 볼 수 있습니다. 그동안 추출값은 확인할 수 있습니다.</p>
      <div className="flex flex-wrap justify-center gap-2">
        <Link href={routes.review(docId, "values")} className={buttonStyles()}>
          추출값 확인
        </Link>
        {DEV && (
          <Link href={`${routes.review(docId, tab)}&judgmentMock=ready`} className={buttonStyles({ variant: "outline" })}>
            개발용 가상 판정 보기
          </Link>
        )}
      </div>
    </JudgmentNotice>
  );
}

export function JudgmentError({ paneTitle, error, onRetry }: { paneTitle: string; error: unknown; onRetry: () => void }) {
  const message =
    error instanceof ApiContractError
      ? "판정 응답이 화면 약속과 달라 틀린 판정을 보여 주지 않으려고 표시하지 않았습니다."
      : error instanceof ApiRequestError
        ? error.message
        : "서버에 연결하지 못했습니다.";
  return (
    <JudgmentNotice paneTitle={paneTitle} title="판정 결과를 불러오지 못했습니다" alert>
      <p className="break-words text-mut">{message}</p>
      {error instanceof ApiContractError && <p className="text-sm break-words text-mut">{error.message}</p>}
      <Button onClick={onRetry}>다시 불러오기</Button>
    </JudgmentNotice>
  );
}

export function JudgmentNotice({
  paneTitle,
  title,
  alert,
  children,
}: {
  paneTitle: string;
  title: string;
  alert?: boolean;
  children: ReactNode;
}) {
  return (
    <Pane title={paneTitle}>
      <div role={alert ? "alert" : "status"} className="flex flex-col items-center gap-3 py-10 text-center">
        <h3 className="text-lg font-bold">{title}</h3>
        {children}
      </div>
    </Pane>
  );
}
