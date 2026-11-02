"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { DEMO_VALIDATION_ID } from "@/api/demo-findings";
import { findingsQuery } from "@/api/findings";
import type { FindingSummary } from "@/api/findings-schemas";
import { Foot, Pane, Row } from "@/components/shell/layout";
import { Button, Callout, Skeleton } from "@/components/ui";
import { FindingSourceViewer } from "../source-viewer";
import { useReviewState } from "../review-state";
import { FindingDetailView } from "./finding-detail";
import { FindingsTable, type SortKey } from "./findings-table";
import { VERDICT_LABEL, VERDICT_ORDER, severityRank, unresolvedNote } from "./verdict";

const verdictRank = (v: FindingSummary["verdict"]) => VERDICT_ORDER.indexOf(v);

/** 기본은 판정 종류 순(불일치→근거부족→경고→일치) 안에서 심각도 높음→낮음. 심각도 순은 반대로 묶는다. */
function sortRows(rows: FindingSummary[], sort: SortKey) {
  return [...rows].sort((a, b) =>
    sort === "severity"
      ? severityRank(a.severity) - severityRank(b.severity) || verdictRank(a.verdict) - verdictRank(b.verdict)
      : verdictRank(a.verdict) - verdictRank(b.verdict) || severityRank(a.severity) - severityRank(b.severity),
  );
}

const FILTER_VERDICTS = ["mismatch", "borderline", "insufficient", "warning", "match"] as const;

/** 2 검수 · 2항 유해성·위험성 탭: 왼쪽 원문, 오른쪽 위 선택한 판정의 상세, 아래 2항 판정 표 */
export function HazardPanel({ docId, onSave }: { docId: string; onSave: () => void }) {
  const { data, isPending, isError, refetch } = useQuery(findingsQuery(docId, DEMO_VALIDATION_ID, { section: 2 }));
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState<SortKey>("verdict");
  const [selected, setSelected] = useState<string | undefined>();
  const { unresolvedByVerdict } = useReviewState();

  const rows = useMemo(() => {
    const all = sortRows(data?.items ?? [], sort);
    return filter === "all" ? all : all.filter((r) => r.verdict === filter);
  }, [data, filter, sort]);

  if (isPending) return <Skeleton className="w-2/3" />;
  if (isError) {
    return (
      <Callout tone="danger" role="alert" className="flex flex-wrap items-center gap-2">
        <span>2항 판정을 불러오지 못했습니다.</span>
        <Button onClick={() => void refetch()}>다시 불러오기</Button>
      </Callout>
    );
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
        <p className="text-mut">
          {unresolvedNote(unresolvedByVerdict(2), "2항")}
        </p>
        <Button variant="primary" size="lg" onClick={onSave}>
          저장하기
        </Button>
      </Foot>
    </>
  );
}
