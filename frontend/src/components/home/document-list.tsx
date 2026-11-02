"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { documentListQuery } from "@/api/documents";
import type { DocumentFilter, DocumentSummary } from "@/api/schemas";
import { RetryButton } from "@/components/documents/retry-button";
import { Button, PillTabs, Progress, Skeleton, StatusLabel, Table, TableHead, buttonStyles } from "@/components/ui";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";
import { routes } from "@/lib/routes";
import { allSectionsFailed, progressLabel, statusLabel } from "@/lib/status";

const FILTERS: { id: DocumentFilter; label: string }[] = [
  { id: "all", label: "전체" },
  { id: "active", label: "진행 중" },
  { id: "done", label: "완료" },
  { id: "failed", label: "실패" },
];

const EMPTY: Record<DocumentFilter, string> = {
  all: "작업한 문서가 아직 없습니다. 위에서 PDF를 올려 주세요.",
  active: "진행 중인 문서가 없습니다.",
  done: "완료된 문서가 없습니다.",
  failed: "실패하거나 멈춘 문서가 없습니다.",
};

/** 표의 칸 너비. 머리줄과 행이 같이 쓴다 (templates 1.1) */
const COL = {
  doc: "min-w-0 flex-3",
  status: "w-22",
  progress: "min-w-0 flex-2",
  layer: "w-28",
  updated: "w-35",
  action: "flex w-25 justify-end",
};

const ROW = "flex items-center gap-3 border-b border-line2 px-5 py-3.5 last:border-b-0";

/** 1.1 작업한 문서: 보기 전환, 목록, 행마다 다음 행동. */
export function DocumentList() {
  const [view, setView] = useState<DocumentFilter>("all");
  // 보기를 바꾸는 동안 이전 목록을 남겨 깜빡이지 않게 한다
  const list = useQuery({ ...documentListQuery(view), placeholderData: keepPreviousData });
  const counts = list.data?.counts;

  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-xl font-bold">작업한 문서</h2>
        <PillTabs
          label="문서 보기"
          value={view}
          onChange={(id) => setView(id as DocumentFilter)}
          items={FILTERS.map((f) => ({ id: f.id, label: counts ? `${f.label} ${counts[f.id]}` : f.label }))}
        />
      </div>
      <Table>
        <div className="min-w-210" aria-busy={list.isFetching}>
          <TableHead className="px-5 py-2.5">
            <span className={COL.doc}>문서</span>
            <span className={COL.status}>단계</span>
            <span className={COL.progress}>진행</span>
            <span className={COL.layer}>텍스트층</span>
            <span className={COL.updated}>마지막 작업</span>
            <span className={COL.action} />
          </TableHead>
          {list.isPending ? (
            [0, 1, 2].map((i) => (
              <div key={i} aria-hidden="true" className={ROW}>
                <span className={COL.doc}><Skeleton className="w-40" /></span>
                <span className={COL.status}><Skeleton className="w-14" /></span>
                <span className={COL.progress}><Skeleton className="w-24" /></span>
                <span className={COL.layer}><Skeleton className="w-12" /></span>
                <span className={COL.updated}><Skeleton className="w-28" /></span>
                <span className={COL.action} />
              </div>
            ))
          ) : list.isError ? (
            <div role="alert" className="flex flex-col items-center gap-3 px-5 py-8 text-center">
              <p className="text-mut">문서 목록을 불러오지 못했습니다. 서버가 켜져 있는지 확인해 주세요.</p>
              <Button onClick={() => void list.refetch()}>다시 불러오기</Button>
            </div>
          ) : list.data.items.length === 0 ? (
            <p className="px-5 py-8 text-center text-mut">{EMPTY[view]}</p>
          ) : (
            list.data.items.map((doc) => <DocumentRow key={doc.id} doc={doc} />)
          )}
        </div>
      </Table>
    </section>
  );
}

function DocumentRow({ doc }: { doc: DocumentSummary }) {
  const status = statusLabel(doc);
  const progress = progressLabel(doc);

  return (
    <div className={ROW}>
      <div className={COL.doc}>
        <div className="truncate font-medium">{doc.filename}</div>
        <div className="truncate text-sm text-mut">
          {doc.id}
          {doc.page_count != null && ` · ${doc.page_count}쪽`}
        </div>
        {doc.error && (doc.status === "failed" || doc.status === "interrupted") && (
          <div className="truncate text-sm text-red" title={doc.error}>
            {doc.error}
          </div>
        )}
      </div>
      <div className={COL.status}>
        <StatusLabel tone={status.tone} className="text-base">
          {status.label}
        </StatusLabel>
        {doc.status === "done" && doc.review_stage && <div className="mt-1 text-sm text-mut">{doc.review_stage}</div>}
      </div>
      <div className={COL.progress}>
        <div className="mb-1 text-sm">
          {progress.text}
          {doc.counts.needs_review > 0 && <span className="text-amb-text"> · 확인 {doc.counts.needs_review}항</span>}
        </div>
        <Progress value={progress.percent} label={`${doc.filename} 진행률`} />
        {doc.queue_position != null && (
          <div className="mt-1 text-sm text-mut">
            대기 {doc.queue_position}번째{doc.eta_seconds != null && ` · 약 ${Math.max(1, Math.ceil(doc.eta_seconds / 60))}분`}
          </div>
        )}
      </div>
      <div className={cn(COL.layer, "text-sm", doc.text_layer && doc.text_layer !== "정상" ? "text-amb-text" : "text-sub")}>
        {doc.text_layer ?? <span className="text-mut">판정 전</span>}
      </div>
      <div className={cn(COL.updated, "text-sm text-mut")}>{formatDateTime(doc.updated_at)}</div>
      <div className={COL.action}>
        <RowAction doc={doc} />
      </div>
    </div>
  );
}

/** 상태마다 다음 행동 하나: 진행 보기 · 검수하기 · 다시 시도 */
function RowAction({ doc }: { doc: DocumentSummary }) {
  // 모든 항이 실패한 문서는 검수할 값이 없다
  if (doc.status === "done" && !allSectionsFailed(doc)) {
    return (
      <Link href={routes.reviewMode(doc.id)} className={buttonStyles({ variant: "primary" })}>
        검수하기
      </Link>
    );
  }
  if (doc.can_retry) return <RetryButton docId={doc.id} filename={doc.filename} />;
  return (
    <Link href={routes.extract(doc.id)} className={buttonStyles()}>
      진행 보기
    </Link>
  );
}
