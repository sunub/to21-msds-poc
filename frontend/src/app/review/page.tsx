"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { DocSummaryLine } from "@/components/review/doc-summary-line";
import { HistoryPanel } from "@/components/review/history/history-panel";
import { HazardPanel } from "@/components/review/hazard/hazard-panel";
import { RegulationPanel } from "@/components/review/regulation/regulation-panel";
import { ReviewStateProvider, useReviewState } from "@/components/review/review-state";
import { SaveGuardDialog } from "@/components/review/save-guard-dialog";
import { ValuesPanel } from "@/components/review/values-panel";
import { DocFrame } from "@/components/shell/doc-frame";
import { Foot, Pane, Row, SourcePane } from "@/components/shell/layout";
import { Button, UnderlineTabs } from "@/components/ui";
import { REVIEW_TABS, isReviewTab, routes, type ReviewTab } from "@/lib/routes";

/** 탭마다 오른쪽 작업 영역에 들어올 구역. 시안 2.2~2.4와 성분별 요약·검토 이력 탭. */
const PANELS: Record<ReviewTab, { title: string; note: string }[]> = {
  hazard: [
    { title: "선택한 판정의 상세", note: "MSDS 기재와 검증 결과, 판단 근거·계산 과정, 확정·예외 승인 버튼이 들어올 자리" },
    { title: "2항 판정 표", note: "판정 건수 요약과 유해성 항목별 판정 표가 들어올 자리" },
  ],
  regulation: [
    { title: "선택한 판정의 상세", note: "MSDS 기재와 규제DB 결과, 판단 근거, 확정·예외 승인 버튼이 들어올 자리" },
    { title: "15항 판정 표", note: "법령별 거르기와 규제 항목별 판정 표가 들어올 자리" },
  ],
  components: [
    { title: "성분 상세", note: "성분의 기준 분류와 ATE를 가져온 순서가 들어올 자리 (단일물질이면 기준 분류 비교)" },
    { title: "구성성분별 판단 요약", note: "성분별 기준 분류, 사용 ATE, 15항 해당, 자료 신뢰도 표가 들어올 자리" },
    { title: "제약사항 · 검토 필요", note: "근거부족과 경계 사유가 들어올 자리" },
  ],
  history: [
    { title: "처리하지 않은 판정", note: "아직 처리하지 않은 판정 목록이 들어올 자리" },
    { title: "검토 이력", note: "시각, 검토자, 구분, 대상, 처리 내용, 의견 표가 들어올 자리" },
  ],
  values: [],
};

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
      ) : tab === "history" ? (
        <HistoryPanel docId={doc} onSave={requestSave} />
      ) : (
        <>
      <Row>
        <SourcePane />
        <div className="flex min-w-0 grow basis-105 flex-col gap-5">
          {PANELS[tab].map((p) => (
            <Pane key={p.title} title={p.title}>
              <p className="text-sm text-mut">{p.note}</p>
            </Pane>
          ))}
        </div>
      </Row>

      <Foot>
        <p className="text-mut">미검수·미검토 안내가 들어올 자리</p>
        <Button variant="primary" size="lg" onClick={requestSave}>
          저장하기
        </Button>
      </Foot>
        </>
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
