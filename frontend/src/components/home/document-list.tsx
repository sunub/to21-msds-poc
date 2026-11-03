"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { documentListQuery } from "@/api/documents";
import { judgmentSummaryQuery, type JudgmentSummaryItem } from "@/api/judgment-extra";
import type { DocumentFilter, DocumentSummary } from "@/api/schemas";
import { RetryButton } from "@/components/documents/retry-button";
import { Button, PillTabs, Progress, Skeleton, StatusLabel, Table, TableHead, buttonStyles } from "@/components/ui";
import { cn } from "@/lib/cn";
import { documentStage, gradeLabel, type DocStage } from "@/lib/doc-stage";
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
  grade: "w-16",
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
  // 추출이 끝난 문서만 판정 요약을 묻는다 (200개씩, 한 번에). 판정 서버가 없거나 실패하면 추출 정보만으로 그리고 판정 칸은 "-"다
  const doneIds = (list.data?.items ?? []).filter((d) => d.status === "done").map((d) => d.id);
  const summary = useQuery(judgmentSummaryQuery(doneIds)).data;
  const judgmentOf = new Map((summary ?? []).map((s) => [s.job_id, s]));

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
            <span className={COL.grade}>등급</span>
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
                <span className={COL.grade}><Skeleton className="w-8" /></span>
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
            list.data.items.map((doc) => <DocumentRow key={doc.id} doc={doc} judgment={judgmentOf.get(doc.id)} />)
          )}
        </div>
      </Table>
    </section>
  );
}

function DocumentRow({ doc, judgment }: { doc: DocumentSummary; judgment?: JudgmentSummaryItem }) {
  const base = statusLabel(doc);
  const stage = documentStage(doc, judgment, doc.status === "done" && allSectionsFailed(doc));
  // 단계 칸: 합친 단계. 추출 쪽 이상 상태(모든 항 실패)는 기존 문구를 그대로 둔다. 완료 문서의 추출 검증 문구는 아래 줄에 남긴다
  const status = stage.normal ? stage : { ...stage, label: base.label, tone: base.tone };
  const extractionNote = doc.status === "done" && stage.normal && base.tone !== "success" ? base.label : null;
  const progress = progressLabel(doc);

  return (
    <div className={ROW}>
      <div className={COL.doc}>
        <div className="truncate font-medium">{doc.filename}</div>
        <div className="truncate text-sm text-mut">
          {[doc.product_name, doc.doc_code, doc.id].filter(Boolean).join(" · ")}
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
        {extractionNote && <div className="mt-1 text-sm text-mut">{extractionNote}</div>}
      </div>
      <div className={COL.progress}>
        <div className="mb-1 text-sm">
          {progress.text}
          {doc.counts.needs_review > 0 && <span className="text-amb-text"> · 확인 {doc.counts.needs_review}항</span>}
        </div>
        <Progress value={progress.percent} label={`${doc.filename} 진행률`} />
      </div>
      <div className={cn(COL.layer, "text-sm", doc.text_layer && doc.text_layer !== "정상" ? "text-amb-text" : "text-sub")}>
        {doc.text_layer ?? <span className="text-mut">판정 전</span>}
      </div>
      <div className={cn(COL.grade, "text-sm", judgment?.data_grade === "골드" ? "font-bold text-amb-text" : "text-sub")}>{gradeLabel(judgment)}</div>
      <div className={cn(COL.updated, "text-sm text-mut")}>{formatDateTime(doc.updated_at)}</div>
      <div className={COL.action}>
        <RowAction doc={doc} stage={stage} />
      </div>
    </div>
  );
}

/** 목록의 이동 주소: 이어서 하기는 기존 검수 진입(방식 선택)이나 사람 구간이 멈춘 탭, 열기는 판정 탭 */
const HREF: Record<DocStage["target"], (id: string) => string> = {
  extract: (id) => routes.extract(id),
  mode: (id) => routes.reviewMode(id),
  values: (id) => routes.review(id, "values"),
  hazard: (id) => routes.review(id, "hazard"),
};

/** 상태마다 다음 행동 하나: 진행 보기 · 이어서 하기 · 열기. 실패한 문서는 기존대로 다시 시도 */
function RowAction({ doc, stage }: { doc: DocumentSummary; stage: DocStage }) {
  if (stage.action === "진행 보기" && doc.can_retry) return <RetryButton docId={doc.id} filename={doc.filename} />;
  return (
    <Link href={HREF[stage.target](doc.id)} className={buttonStyles(stage.action === "진행 보기" ? undefined : { variant: "primary" })}>
      {stage.action}
    </Link>
  );
}
