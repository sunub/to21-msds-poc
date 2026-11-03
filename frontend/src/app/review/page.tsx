"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { ComponentsTab } from "@/components/review/components/components-tab";
import { HazardTab } from "@/components/review/hazard/hazard-tab";
import { HistoryTab } from "@/components/review/history/history-tab";
import { RegulationTab } from "@/components/review/regulation/regulation-tab";
import { DocSummaryLine } from "@/components/review/doc-summary-line";
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
  // 2항·15항 의견 초안은 다른 탭을 보고 돌아와도 남도록 탭 바깥에 둔다
  const [regulationDrafts, setRegulationDrafts] = useState<Record<string, string>>({});

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
      ) : tab === "components" ? (
        <ComponentsTab docId={doc} onSave={(unreviewed) => (unreviewed > 0 ? setGuardOpen(true) : router.push(routes.save(doc)))} />
      ) : tab === "history" ? (
        <HistoryTab docId={doc} onSave={(unreviewed) => (unreviewed > 0 ? setGuardOpen(true) : router.push(routes.save(doc)))} />
      ) : tab === "regulation" ? (
        <RegulationTab
          docId={doc}
          drafts={regulationDrafts}
          onDraft={(id, text) => setRegulationDrafts((prev) => ({ ...prev, [id]: text }))}
          onSave={(unreviewed) => (unreviewed > 0 ? setGuardOpen(true) : router.push(routes.save(doc)))}
        />
      ) : (
        <HazardTab
          docId={doc}
          drafts={regulationDrafts}
          onDraft={(id, text) => setRegulationDrafts((prev) => ({ ...prev, [id]: text }))}
        />
      )}

      <SaveGuardDialog
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
      <DocFrame stage="review">{(doc) => <ReviewBody doc={doc} />}</DocFrame>
    </Suspense>
  );
}
