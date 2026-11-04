"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { pageLinesQuery } from "@/api/documents";
import type { DocumentDetail } from "@/api/schemas";
import { Button, Paper, PillTabs, Progress, Skeleton, Spinner } from "@/components/ui";
import { cn } from "@/lib/cn";
import { parsePage, scrollWithin } from "@/lib/viewer";
import { PdfViewer } from "./pdf-viewer";

type Mode = "pdf" | "text";
// 원본/추출 텍스트 선택은 탭을 옮겨도 그대로 둔다
let lastMode: Mode = "pdf";

/**
 * 원문 칸. 기본은 올린 원본 PDF를 그대로 그린다 (pdf-viewer). 근거 글은 원본 글자 위에 강조한다.
 * "추출 텍스트"로 바꾸면 전처리에서 읽은 쪽 글(근거 줄 번호 p2:L23과 같은 번호)을 본다. 이건 전처리가 끝난 쪽만 있다.
 * 넓은 화면에서는 Workspace 칸 높이를 채우고, 위아래로 쌓이는 좁은 화면에서는 본문 높이의 80%를 쓴다.
 */
export function SourceViewer({
  doc,
  page,
  onPage,
  highlight,
  className,
  children,
}: {
  doc: DocumentDetail;
  page: number;
  onPage: (page: number) => void;
  /** 근거 글. 이 글이 들어 있는 곳을 강조한다 (근거에 줄 번호가 없어 글로 찾으므로 같은 글이 여러 곳이면 모두 강조된다) */
  highlight?: string | null;
  className?: string;
  /** 제목과 원문 사이에 넣을 쪽 이동, 안내 */
  children?: ReactNode;
}) {
  const [mode, setModeState] = useState<Mode>(lastMode);
  const [pdfPages, setPdfPages] = useState(0);
  const setMode = (next: Mode) => {
    lastMode = next;
    setModeState(next);
  };
  const total = doc.page_count ?? doc.preprocess.total ?? pdfPages;

  return (
    <section
      aria-label="원문"
      className={cn("flex h-[max(26rem,80cqh)] min-w-0 flex-col gap-2.5 lg:h-full print:hidden", className)}
    >
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-bold">원문</h2>
          <PillTabs
            label="원문 보기 방식"
            items={[
              { id: "pdf", label: "원본 PDF" },
              { id: "text", label: "추출 텍스트" },
            ]}
            value={mode}
            onChange={(id) => setMode(id as Mode)}
          />
        </div>
        {total > 0 && <PageNav page={page} total={total} onPage={onPage} />}
      </div>
      {children}
      {mode === "pdf" ? (
        <PdfViewer docId={doc.id} page={page} onPage={onPage} onPages={setPdfPages} highlight={highlight} />
      ) : (
        <ExtractedText doc={doc} page={page} total={total} highlight={highlight} />
      )}
    </section>
  );
}

function PageNav({ page, total, onPage }: { page: number; total: number; onPage: (page: number) => void }) {
  const [draft, setDraft] = useState<string | null>(null);
  const commit = () => {
    const next = draft === null ? null : parsePage(draft, total);
    if (next !== null && next !== page) onPage(next);
    setDraft(null);
  };
  return (
    <div className="flex items-center gap-1.5">
      <Button disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="이전 페이지">
        ‹ 이전
      </Button>
      <label className="flex items-center gap-1 text-sm text-mut tabular-nums">
        <input
          aria-label="페이지 번호"
          inputMode="numeric"
          value={draft ?? String(page)}
          onChange={(e) => setDraft(e.target.value)}
          onFocus={(e) => e.target.select()}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit();
            if (e.key === "Escape") setDraft(null);
          }}
          className="h-9 w-12 rounded-sm border border-field-line bg-white text-center text-base text-ink"
        />
        / {total}페이지
      </label>
      <Button disabled={page >= total} onClick={() => onPage(page + 1)} aria-label="다음 페이지">
        다음 ›
      </Button>
    </div>
  );
}

/** 전처리에서 읽은 쪽 글. 전처리가 끝나기 전에는 진행만 보여 준다 */
function ExtractedText({ doc, page, total, highlight }: { doc: DocumentDetail; page: number; total: number; highlight?: string | null }) {
  const box = useRef<HTMLDivElement>(null);
  if (page > doc.preprocess.done) {
    return (
      <Paper fill className="items-center justify-center gap-4">
        <Spinner label="텍스트를 읽는 중" />
        <span className="text-base">{doc.status === "queued" ? "차례를 기다리고 있습니다" : "텍스트를 읽는 중입니다"}</span>
        {total > 0 && (
          <div className="w-full">
            <Progress value={(doc.preprocess.done / total) * 100} label="전처리 진행" />
            <p className="mt-2 text-center text-mut tabular-nums">
              {doc.preprocess.done} / {total}페이지
            </p>
          </div>
        )}
      </Paper>
    );
  }
  return (
    <div ref={box} className="flex min-h-0 flex-1 flex-col overflow-y-auto">
      <Paper fill>
        <PageLines id={doc.id} page={page} highlight={highlight} box={box} />
      </Paper>
    </div>
  );
}

function PageLines({
  id,
  page,
  highlight,
  box,
}: {
  id: string;
  page: number;
  highlight?: string | null;
  /** 스크롤할 칸. 바깥 본문은 움직이지 않는다 */
  box: RefObject<HTMLDivElement | null>;
}) {
  const { data, isPending, isError } = useQuery(pageLinesQuery(id, page));
  const firstHit = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    if (firstHit.current && box.current) scrollWithin(box.current, firstHit.current, "nearest");
  }, [highlight, data, box]);
  if (isPending) {
    return (
      <div aria-hidden="true" className="grid gap-2.5">
        <Skeleton className="w-full" />
        <Skeleton className="w-4/5" />
        <Skeleton className="w-2/3" />
      </div>
    );
  }
  if (isError) return <p className="text-mut">이 페이지의 텍스트를 읽지 못했습니다.</p>;
  const isHit = (text: string) => !!highlight && text.trim().length > 1 && highlight.includes(text.trim());
  const first = data.lines.find((l) => isHit(l.text))?.id;
  return data.lines.map((line) => (
    <p
      key={line.id}
      ref={line.id === first ? firstHit : undefined}
      data-line-id={line.id}
      className={cn(isHit(line.text) && "bg-sel")}
    >
      {line.text}
    </p>
  ));
}
