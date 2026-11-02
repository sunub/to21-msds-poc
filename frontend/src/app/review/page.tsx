"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { DocSummaryLine } from "@/components/review/doc-summary-line";
import { HistoryPanel } from "@/components/review/history/history-panel";
import { HazardPanel } from "@/components/review/hazard/hazard-panel";
import { RegulationPanel } from "@/components/review/regulation/regulation-panel";
import { ComponentsPanel } from "@/components/review/summary/summary-panel";
import { ReviewStateProvider, useReviewState } from "@/components/review/review-state";
import { SaveGuardDialog } from "@/components/review/save-guard-dialog";
import { ValuesPanel } from "@/components/review/values-panel";
import { DocFrame } from "@/components/shell/doc-frame";
import { UnderlineTabs } from "@/components/ui";
import { REVIEW_TABS, isReviewTab, routes, type ReviewTab } from "@/lib/routes";

function ReviewBody({ doc }: { doc: string }) {
  const router = useRouter();
  const param = useSearchParams().get("tab");
  const tab: ReviewTab = isReviewTab(param) ? param : "hazard";
  const [guardOpen, setGuardOpen] = useState(false);
  const { unresolvedCount } = useReviewState();
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
      <DocSummaryLine docId={doc} />

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
export default function ReviewPage() {
  return (
    <Suspense>
      <DocFrame stage="review">
        {(doc) => (
          <ReviewStateProvider key={doc} docId={doc}>
            <ReviewBody doc={doc} />
          </ReviewStateProvider>
        )}
      </DocFrame>
    </Suspense>
  );
}
