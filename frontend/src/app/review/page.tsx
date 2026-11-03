"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { judgmentStatusQuery } from "@/api/judgments";
import { Suspense, useEffect, useState } from "react";
import { DocSummaryLine } from "@/components/review/doc-summary-line";
import { JudgmentMetaLine } from "@/components/review/judgment-meta-line";
import { HistoryPanel } from "@/components/review/history/history-panel";
import { HazardPanel } from "@/components/review/hazard/hazard-panel";
import { RegulationPanel } from "@/components/review/regulation/regulation-panel";
import { ComponentsPanel } from "@/components/review/summary/summary-panel";
import { ReviewStateProvider, useReviewState } from "@/components/review/review-state";
import { SaveGuardDialog } from "@/components/review/save-guard-dialog";
import { ValuesPanel } from "@/components/review/values-panel";
import { DocFrame } from "@/components/shell/doc-frame";
import { Button, Callout, UnderlineTabs } from "@/components/ui";
import { REVIEW_TABS, isReviewTab, routes, type ReviewTab } from "@/lib/routes";

function ReviewBody({ doc }: { doc: string }) {
  const router = useRouter();
  const param = useSearchParams().get("tab");
  const tab: ReviewTab = isReviewTab(param) ? param : "hazard";
  const [guardOpen, setGuardOpen] = useState(false);
  const { unresolvedCount, conflict, conflictMessage, refresh, version, ready } = useReviewState();
  // 추출값 탭은 판정이 필요 없다: 판정 서버가 없을 때 불필요한 요청과 오류를 만들지 않는다
  const status = useQuery({ ...judgmentStatusQuery(doc), enabled: tab !== "values" }).data;
  // 아직 판정이 없다가(404) 판정이 생기면 바로 다시 읽는다. 이미 판정을 보고 있으면 건드리지 않고 아래 안내만 한다
  const latestVersion = status?.latest_version ?? null;
  useEffect(() => {
    if (!ready && latestVersion !== null && tab !== "values") refresh();
  }, [ready, latestVersion, tab, refresh]);
  // 판정이 새로 나와 화면의 판정보다 최신이면 409 와 같은 안내를 미리 한다
  const outdated = conflict || (status?.latest_version != null && version !== null && status.latest_version > version);
  // 처리하지 않은 판정이 없으면 경고 없이 바로 저장 화면으로 간다
  const requestSave = () =>
    unresolvedCount(2) + unresolvedCount(15) === 0 ? router.push(routes.save(doc)) : setGuardOpen(true);

  return (
    <div className="flex flex-col gap-5">
      <div className="border-b border-line">
        <UnderlineTabs
          label="검수 구역"
          items={REVIEW_TABS.map((t) => ({ id: t.id, label: t.label }))}
          value={tab}
          onChange={(id) => router.replace(routes.review(doc, id as ReviewTab))}
        />
      </div>
      {tab === "values" ? <DocSummaryLine docId={doc} /> : <JudgmentMetaLine docId={doc} />}

      {outdated && (
        <Callout tone="danger" role="alert" className="flex flex-wrap items-center gap-2">
          <span>{conflictMessage || "더 새로운 판정 버전이 있습니다. 새로고침해 주세요."}</span>
          <Button onClick={refresh}>새로고침</Button>
        </Callout>
      )}
      {status?.pending_handoff != null && (
        <Callout role="status">
          {status.state === "판정 중" ? "더 새로운 추출값으로 판정 중입니다." : "더 새로운 추출값으로 다시 판정할 수 있습니다."}
        </Callout>
      )}

      {tab === "values" ? (
        <ValuesPanel docId={doc} />
      ) : tab === "hazard" ? (
        <HazardPanel docId={doc} onSave={requestSave} />
      ) : tab === "regulation" ? (
        <RegulationPanel docId={doc} onSave={requestSave} />
      ) : tab === "components" ? (
        <ComponentsPanel docId={doc} onSave={requestSave} />
      ) : (
        <HistoryPanel docId={doc} onSave={requestSave} />
      )}

      <SaveGuardDialog
        docId={doc}
        open={guardOpen}
        onClose={() => setGuardOpen(false)}
        onSave={() => router.push(routes.save(doc))}
      />
    </div>
  );
}

/** 2 검수: 탭(2항, 15항, 성분별 요약, 검토 이력, 추출값)을 언제든 오간다. 탭은 ?tab= 에 남긴다. */
function ReviewRoot() {
  const tab = useSearchParams().get("tab");
  return (
    <DocFrame stage="review">
      {(doc) => (
        <ReviewStateProvider key={doc} docId={doc} enabled={tab !== "values"}>
          <ReviewBody doc={doc} />
        </ReviewStateProvider>
      )}
    </DocFrame>
  );
}

export default function ReviewPage() {
  return (
    <Suspense>
      <ReviewRoot />
    </Suspense>
  );
}
