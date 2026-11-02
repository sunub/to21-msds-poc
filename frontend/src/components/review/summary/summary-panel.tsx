"use client";

import { judgmentErrorText } from "@/api/judgments";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { componentsQuery } from "@/api/components";
import { findingsQuery } from "@/api/findings";
import { Foot, Pane, Row } from "@/components/shell/layout";
import Link from "next/link";
import { routes } from "@/lib/routes";
import { Button, Callout, Skeleton, buttonStyles } from "@/components/ui";
import { FindingSourceViewer } from "../source-viewer";
import { useReviewState } from "../review-state";
import { useValidationId } from "../shared/use-validation-id";
import { ComponentDetail } from "./component-detail";
import { ComponentsTable } from "./components-table";
import { Constraints } from "./constraints";
import { FootActions } from "../shared/foot-actions";

/** 2 검수 · 성분별 요약 탭: 왼쪽 원문, 오른쪽 성분 상세, 아래 구성성분별 판단 요약 표와 제약사항 */
export function ComponentsPanel({ docId, onSave }: { docId: string; onSave: () => void }) {
  // &product=single 은 demo 문서에서만 듣는다 (components.ts 가 운영 요청에는 싣지 않는다)
  const validation = useValidationId(docId);
  const productParam = useSearchParams().get("product");
  const product = productParam === "single" || productParam === "unknown" ? productParam : undefined;
  const { data, isPending, isError, error, refetch } = useQuery(componentsQuery(docId, validation, { product }));
  const hazard = useQuery(findingsQuery(docId, validation, { section: 2 })).data;
  const regulation = useQuery(findingsQuery(docId, validation, { section: 15 })).data;
  const findingsById = useMemo(
    () => new Map([...(hazard?.items ?? []), ...(regulation?.items ?? [])].map((f) => [f.finding_id, f])),
    [hazard, regulation],
  );
  const { unresolvedCount } = useReviewState();
  const [selected, setSelected] = useState<string | undefined>();

  if (isPending) return <Skeleton className="w-2/3" />;
  if (isError) {
    return (
      <Callout tone="danger" role="alert" className="flex flex-wrap items-center gap-2">
        <span>{judgmentErrorText(error, "성분별 요약을 불러오지 못했습니다.")}</span>
        <Button onClick={() => void refetch()}>다시 불러오기</Button>
      </Callout>
    );
  }

  const unresolved = unresolvedCount(2) + unresolvedCount(15);
  const foot = (
    <Foot>
      <p className="text-mut">
        {unresolved === 0 ? "처리하지 않은 판정이 없습니다." : `처리하지 않은 판정 ${unresolved}건은 저장하면 미검토로 남습니다.`}
      </p>
      <FootActions docId={docId} onSave={onSave} />
    </Foot>
  );

  // 단일물질인지 혼합물인지 모르면 자동으로 정하지 않고, 사용자가 정하도록 안내만 한다
  if (data.product_type === "unknown") {
    return (
      <>
        <Callout tone="warning" role="alert" className="flex flex-col gap-1 [word-break:keep-all]">
          <b>제품이 혼합물인지 단일물질인지 자동으로 판별하지 못했습니다.</b>
          <span>유형 지정 기능은 아직 연결되지 않았습니다. 담당자에게 확인을 요청해 주세요.</span>
          <span className="mt-1 flex flex-wrap gap-2">
            <Link href={routes.review(docId, "hazard")} className={buttonStyles()}>
              2항 판정으로 가기
            </Link>
            <Link href={routes.review(docId, "regulation")} className={buttonStyles()}>
              15항 판정으로 가기
            </Link>
          </span>
        </Callout>
        {foot}
      </>
    );
  }

  const current =
    data.items.find((c) => c.component_id === selected) ??
    data.items.find((c) => c.component_id === data.selected_component_id) ??
    data.items[0];

  return (
    <>
      <Row>
        <FindingSourceViewer
          docId={docId}
          refs={current?.source_refs.map((r) => r.page_no) ?? []}
          resetKey={current?.component_id}
        />
        <div className="flex min-w-0 grow basis-105 flex-col gap-5">
          <Pane title="성분 상세" className="border-l-4 border-l-blue-line">
            {current ? (
              <ComponentDetail
                key={current.component_id}
                docId={docId}
                product={data.product_type}
                component={current}
                findingsById={findingsById}
              />
            ) : (
              <p className="text-sm text-mut">표에서 성분을 고르면 상세가 여기에 나옵니다.</p>
            )}
          </Pane>
        </div>
      </Row>

      <section aria-labelledby="comp-summary" className="flex flex-col gap-2.5">
        <h2 id="comp-summary" className="text-lg font-bold">
          구성성분별 판단 요약
        </h2>
        <ComponentsTable items={data.items} selectedId={current?.component_id} onSelect={setSelected} />
      </section>

      <section aria-labelledby="comp-limits" className="flex flex-col gap-2.5">
        <div className="flex flex-wrap items-baseline gap-2.5">
          <h2 id="comp-limits" className="text-lg font-bold">
            제약사항 · 검토 필요
          </h2>
          <span className="text-sm text-mut">근거부족과 경계 사유를 한곳에 모았습니다. 먼저 확인해 주세요.</span>
        </div>
        <Constraints docId={docId} items={data.items} findingsById={findingsById} />
      </section>

      {foot}
    </>
  );
}
