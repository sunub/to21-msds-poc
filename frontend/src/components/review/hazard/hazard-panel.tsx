"use client";

import { judgmentErrorText } from "@/api/judgments";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { findingsQuery } from "@/api/findings";
import { Foot, Pane, Row } from "@/components/shell/layout";
import { Button, Skeleton } from "@/components/ui";
import { FindingSourceViewer } from "../source-viewer";
import { useReviewState } from "../review-state";
import { LoadError } from "../shared/load-error";
import { sortRows, type SortKey } from "../shared/sort";
import { useValidationId } from "../shared/use-validation-id";
import { FindingDetailView } from "./finding-detail";
import { FindingsTable } from "./findings-table";
import { VERDICT_LABEL, unresolvedNote } from "./verdict";
import { FootActions } from "../shared/foot-actions";

const FILTER_VERDICTS = ["mismatch", "borderline", "insufficient_evidence", "warning", "match"] as const;

/** 2 검수 · 2항 유해성·위험성 탭: 왼쪽 원문, 오른쪽 위 선택한 판정의 상세, 아래 2항 판정 표 */
export function HazardPanel({ docId, onSave }: { docId: string; onSave: () => void }) {
  const validation = useValidationId(docId);
  const { data, isPending, isError, error, refetch } = useQuery(findingsQuery(docId, validation, { section: 2 }));
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState<SortKey>("verdict");
  // 다른 탭의 "이동"이 ?finding= 으로 넘긴 판정을 먼저 고른다. 값이 바뀌면(같은 탭에서 이동) 다시 그 판정으로 간다
  const findingParam = useSearchParams().get("finding") ?? undefined;
  const [selected, setSelected] = useState<string | undefined>(findingParam);
  const [seenParam, setSeenParam] = useState(findingParam);
  if (findingParam !== seenParam) {
    setSeenParam(findingParam);
    setSelected(findingParam);
    setFilter("all");
  }
  const { unresolvedByVerdict } = useReviewState();

  const rows = useMemo(() => {
    const all = sortRows(data?.items ?? [], sort);
    return filter === "all" ? all : all.filter((r) => r.verdict === filter);
  }, [data, filter, sort]);

  if (isPending) return <Skeleton className="w-2/3" />;
  if (isError) {
    return <LoadError message={judgmentErrorText(error, "2항 판정을 불러오지 못했습니다.")} onRetry={() => void refetch()} />;
  }

  // 고른 행이 없거나 거르기로 사라졌으면 보이는 첫 행을 고른다
  const current = rows.find((r) => r.finding_id === selected) ?? rows[0];
  const filterItems = [
    { id: "all", label: `전체 ${data.items.length}` },
    ...FILTER_VERDICTS.map((v) => ({ id: v, label: `${VERDICT_LABEL[v]} ${data.counts[v] ?? 0}` })),
  ];
  const excluded = Object.values(data.excluded_counts).reduce((a, b) => a + b, 0);

  return (
    <>
      <Row>
        <FindingSourceViewer
          docId={docId}
          refs={current?.source_refs.map((r) => r.page_no) ?? []}
          resetKey={current?.finding_id}
        />
        <div className="flex min-w-0 grow basis-105 flex-col gap-5">
          <Pane title="선택한 판정의 상세">
            {current ? (
              <FindingDetailView
                key={current.finding_id}
                docId={docId}
                validationId={data.validation_id}
                finding={current}
              />
            ) : (
              <p className="text-sm text-mut">표에서 판정을 고르면 상세가 여기에 나옵니다.</p>
            )}
          </Pane>
          <Pane title="2항 판정 표">
            <FindingsTable
              rows={rows}
              filter={filter}
              filterItems={filterItems}
              onFilter={setFilter}
              sort={sort}
              onSort={setSort}
              selectedId={current?.finding_id}
              onSelect={setSelected}
              matchCount={data.items.filter((f) => f.verdict === "match").length}
              excludedCount={excluded}
            />
          </Pane>
        </div>
      </Row>

      <Foot>
        <p className="text-mut">{unresolvedNote(unresolvedByVerdict(2), "2항")}</p>
        <FootActions docId={docId} onSave={onSave} />
      </Foot>
    </>
  );
}
