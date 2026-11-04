"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";
import { documentListQuery } from "@/api/documents";
import { judgmentSummaryQuery, type JudgmentBatchItem } from "@/api/judgment";
import type { DocumentFilter, DocumentSummary } from "@/api/schemas";
import { RetryButton } from "@/components/documents/retry-button";
import { Button, PillTabs, Progress, Skeleton, StatusLabel, Table, TableHead, buttonStyles } from "@/components/ui";
import { cn } from "@/lib/cn";
import { documentRow, failureMessage, type RowAction as RowActionView } from "@/lib/document-row";
import { formatDateTime } from "@/lib/format";
import { inputType, validationLabel } from "@/lib/status";

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
  status: "w-28",
  progress: "min-w-0 flex-2",
  layer: "w-32",
  updated: "w-35",
  action: "flex w-32 justify-end",
};

const ROW = "flex items-center gap-3 border-b border-line2 px-5 py-3.5 last:border-b-0";

const HIDDEN_KEY = "msds.hiddenDocs";

/** 숨긴 문서 id. 저장소를 못 써도 화면은 동작해야 하므로 읽기·쓰기 모두 try/catch */
function readHidden(): string[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(HIDDEN_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function writeHidden(ids: string[]) {
  try {
    localStorage.setItem(HIDDEN_KEY, JSON.stringify(ids));
  } catch {
    // 저장하지 못하면 새로고침 때 다시 보인다
  }
}

/** 1.1 작업한 문서: 보기 전환, 목록, 행마다 다음 행동. */
export function DocumentList() {
  const [view, setView] = useState<DocumentFilter>("all");
  // 보기를 바꾸는 동안 이전 목록을 남겨 깜빡이지 않게 한다
  const list = useQuery({ ...documentListQuery(view), placeholderData: keepPreviousData });
  // 화면에서만 숨긴다 (서버 데이터는 그대로). 서버 렌더와 어긋나지 않게 마운트 뒤에 읽는다
  const [hidden, setHidden] = useState<string[]>([]);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  useEffect(() => setHidden(readHidden()), []);
  const updateHidden = (ids: string[]) => {
    setHidden(ids);
    writeHidden(ids);
  };
  // 집계에서 숨긴 문서를 빼려면 어느 보기에서든 전체 목록이 필요하다 (보기가 전체면 같은 요청이다)
  const all = useQuery({ ...documentListQuery("all"), placeholderData: keepPreviousData, enabled: hidden.length > 0 });
  const visibleAll = all.data?.items.filter((d) => !hidden.includes(d.id));
  const counts =
    hidden.length > 0 && visibleAll
      ? {
          all: visibleAll.length,
          active: visibleAll.filter((d) => d.status === "queued" || d.status === "running").length,
          done: visibleAll.filter((d) => d.status === "done").length,
          failed: visibleAll.filter((d) => d.status === "failed" || d.status === "interrupted").length,
        }
      : list.data?.counts;
  const items = list.data?.items.filter((d) => !hidden.includes(d.id));
  // 끝난 문서의 판정·저장 상태는 B 가 갖고 있다. 한 번에 묻고 작업 번호로 합친다 (6-screens 1.1)
  const doneIds = (items ?? []).filter((d) => d.status === "done").map((d) => d.id);
  // 끝난 문서가 늘어 키가 바뀌는 동안 이전 판정 상태를 남겨 '완료'가 잠깐 '검수 중'으로 바뀌지 않게 한다
  const judgments = useQuery({ ...judgmentSummaryQuery(doneIds), placeholderData: keepPreviousData });
  const judgmentOf = new Map((judgments.data ?? []).map((j) => [j.job_id, j]));

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
            <span className={COL.layer}>PDF 종류</span>
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
          ) : !items || items.length === 0 ? (
            <p className="px-5 py-8 text-center text-mut">{EMPTY[view]}</p>
          ) : (
            items.map((doc) => (
              <DocumentRow
                key={doc.id}
                doc={doc}
                judgment={judgmentOf.get(doc.id)}
                confirming={confirmId === doc.id}
                onAskHide={() => setConfirmId(doc.id)}
                onCancelHide={() => setConfirmId(null)}
                onHide={() => {
                  updateHidden([...hidden, doc.id]);
                  setConfirmId(null);
                }}
              />
            ))
          )}
        </div>
      </Table>
      {hidden.length > 0 && (
        <div className="flex justify-end text-sm text-mut">
          <span className="self-center">숨긴 문서 {hidden.length}건</span>
          <button type="button" className={buttonStyles({ variant: "link" })} onClick={() => updateHidden([])}>
            모두 다시 보이기
          </button>
        </div>
      )}
    </section>
  );
}

const NOTE_TEXT: Partial<Record<string, string>> = { danger: "text-red", warning: "text-amb-text" };

function DocumentRow({
  doc,
  judgment,
  confirming,
  onAskHide,
  onCancelHide,
  onHide,
}: {
  doc: DocumentSummary;
  judgment: JudgmentBatchItem | undefined;
  confirming: boolean;
  onAskHide: () => void;
  onCancelHide: () => void;
  onHide: () => void;
}) {
  const row = documentRow(doc, judgment, validationLabel(doc.validation));
  const failure = doc.status === "failed" || doc.status === "interrupted" ? failureMessage(doc.error, doc.status) : null;
  const pdf = inputType(doc.text_layer);
  // 처리 중인 문서는 숨기지 않는다
  const canHide = doc.status !== "queued" && doc.status !== "running";

  return (
    <div className={ROW}>
      <div className={COL.doc}>
        <div className="truncate font-medium" title={row.title}>{row.title}</div>
        <div className="truncate text-sm text-mut" title={row.subtitle}>{row.subtitle}</div>
        {failure && (
          <div className="text-sm text-red break-keep" title={failure.detail}>
            {failure.text}
          </div>
        )}
        {confirming && (
          <div role="group" aria-label="목록에서 숨기기 확인" className="mt-1 flex flex-wrap items-center gap-x-2 text-sm">
            <span className="text-sub">목록에서 숨길까요? 서버의 데이터는 그대로 남습니다</span>
            <Button
              size="md"
              className="min-h-7 px-2.5"
              onClick={(e) => {
                e.stopPropagation();
                onHide();
              }}
            >
              숨기기
            </Button>
            <Button
              variant="link"
              onClick={(e) => {
                e.stopPropagation();
                onCancelHide();
              }}
            >
              취소
            </Button>
          </div>
        )}
      </div>
      <div className={COL.status}>
        <StatusLabel tone={row.stage.tone} className="text-base">
          {row.stage.label}
        </StatusLabel>
        {row.note && (
          <div className={cn("mt-0.5 text-sm break-keep", NOTE_TEXT[row.note.tone] ?? "text-sub")} title={row.note.title}>
            {row.note.text}
          </div>
        )}
      </div>
      <div className={COL.progress}>
        <div className="mb-1 text-sm break-keep">
          {row.progress.text}
          {row.progress.detail && <span className="text-sub"> · {row.progress.detail}</span>}
        </div>
        <Progress value={row.progress.percent} label={`${doc.filename} 진행률`} />
      </div>
      <div className={cn(COL.layer, "text-sm", doc.text_layer && doc.text_layer !== "정상" ? "text-amb-text" : "text-sub")}>
        <span className="break-keep" title={pdf.note}>{doc.text_layer ? pdf.label : <span className="text-mut">판정 전</span>}</span>
      </div>
      <div className={cn(COL.updated, "text-sm text-mut")}>{formatDateTime(doc.updated_at)}</div>
      <div className={cn(COL.action, "items-center gap-1")}>
        <RowAction doc={doc} action={row.action} />
        {canHide ? (
          <button
            type="button"
            aria-label="목록에서 숨기기"
            title="목록에서 숨기기"
            className="inline-flex size-6 shrink-0 items-center justify-center rounded-md text-[#C0C0C0] hover:bg-tint hover:text-mut"
            onClick={(e) => {
              e.stopPropagation();
              onAskHide();
            }}
          >
            <svg
              width="12"
              height="12"
              viewBox="0 0 12 12"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              aria-hidden="true"
            >
              <path d="M2 2l8 8M10 2L2 10" />
            </svg>
          </button>
        ) : (
          <span className="size-6 shrink-0" aria-hidden="true" />
        )}
      </div>
    </div>
  );
}

/** 상태마다 다음 행동 하나: 진행 보기 · 검수하기 · 이어서 하기 · 열기 · 다시 시도 (lib/document-row.ts) */
function RowAction({ doc, action }: { doc: DocumentSummary; action: RowActionView }) {
  if (action.kind === "retry") return <RetryButton docId={doc.id} filename={doc.filename} />;
  return (
    <Link href={action.href} className={buttonStyles(action.primary ? { variant: "primary" } : undefined)}>
      {action.label}
    </Link>
  );
}
