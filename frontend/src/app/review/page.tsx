"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { saveOverviewQuery } from "@/api/save";
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
  const client = useQueryClient();
  // 저장하기: 방금 누른 처리가 아직 서버로 가는 중이거나 화면 판정이 다시 받기 전이면 화면의 건수가 지난 값이다.
  // 처리 요청이 끝나기를 기다린 뒤 서버(save-overview)의 미검토 수로 정한다. 서버를 못 부르면 화면 건수로 정한다
  const goSave = async (shown: number) => {
    let unreviewed = shown;
    try {
      for (let waited = 0; client.isMutating() > 0 && waited < 15_000; waited += 100) await new Promise((r) => setTimeout(r, 100));
      unreviewed = (await client.fetchQuery(saveOverviewQuery(doc))).reviews.unreviewed_ids.length;
    } catch {
      // 화면 건수를 쓴다
    }
    if (unreviewed > 0) setGuardOpen(true);
    else router.push(routes.save(doc));
  };
  // 2항·15항 의견 초안은 다른 탭을 보고 돌아와도 남도록 탭 바깥에 둔다
  const [regulationDrafts, setRegulationDrafts] = useState<Record<string, string>>({});

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5">
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
        <ComponentsTab docId={doc} onSave={(unreviewed) => void goSave(unreviewed)} />
      ) : tab === "history" ? (
        <HistoryTab docId={doc} onSave={(unreviewed) => void goSave(unreviewed)} />
      ) : tab === "regulation" ? (
        <RegulationTab
          docId={doc}
          drafts={regulationDrafts}
          onDraft={(id, text) => setRegulationDrafts((prev) => ({ ...prev, [id]: text }))}
          onSave={(unreviewed) => void goSave(unreviewed)}
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

/** 추출값 탭은 표가 없어 화면에 꼭 맞추고, 나머지 탭은 표와 원문·판정 칸이 이어져 스크롤한다 */
function ReviewFrame() {
  const fill = useSearchParams().get("tab") === "values";
  return (
    <DocFrame stage="review" fill={fill}>
      {(doc) => <ReviewBody doc={doc} />}
    </DocFrame>
  );
}

/** 2 검수: 탭(2항, 15항, 성분별 요약, 검토 이력, 추출값)을 언제든 오간다. 탭은 ?tab= 에 남긴다. */
export default function ReviewPage() {
  return (
    <Suspense>
      <ReviewFrame />
    </Suspense>
  );
}
