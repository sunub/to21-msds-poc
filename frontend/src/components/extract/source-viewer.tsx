"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { pageImageUrl, pageLinesQuery } from "@/api/documents";
import type { DocumentDetail } from "@/api/schemas";
import { Pane } from "@/components/shell/layout";
import { Button, Paper, Progress, Skeleton, Spinner } from "@/components/ui";
import { cn } from "@/lib/cn";

/**
 * 원문 칸. 텍스트층이 정상이면 쪽 글을, 아니면(또는 아직 모르면) 쪽 이미지를 보여 준다.
 * 전처리가 끝난 쪽만 요청한다 (그 전에는 404). 추출이 끝나지 않아도 읽을 수 있다.
 */
export function SourceViewer({
  doc,
  page,
  onPage,
  highlight,
  className,
}: {
  doc: DocumentDetail;
  page: number;
  onPage: (page: number) => void;
  /** 근거 글. 이 글에 들어 있는 줄을 강조한다 (근거에 줄 번호가 없어 글로 찾으므로 같은 글이 여러 줄이면 모두 강조된다) */
  highlight?: string | null;
  className?: string;
}) {
  const total = doc.page_count ?? doc.preprocess.total ?? 0;
  const ready = page <= doc.preprocess.done;

  return (
    <Pane
      title="원문"
      className={cn("basis-115 print:hidden", className)}
      aside={
        total > 0 && (
          <div className="flex items-center gap-2">
            <Button disabled={page <= 1} onClick={() => onPage(page - 1)}>
              이전 쪽
            </Button>
            <span className="text-sm text-mut tabular-nums">
              {page} / {total}쪽
            </span>
            <Button disabled={page >= total} onClick={() => onPage(page + 1)}>
              다음 쪽
            </Button>
          </div>
        )
      }
    >
      {ready ? (
        doc.text_layer === "정상" ? (
          <Paper>
            <PageLines id={doc.id} page={page} highlight={highlight} />
          </Paper>
        ) : (
          <PageImage key={`${doc.id}-${page}`} id={doc.id} page={page} />
        )
      ) : (
        <Paper className="items-center justify-center gap-4">
          <Spinner label="쪽 이미지를 만드는 중" />
          <span className="text-base">
            {doc.status === "queued" ? "차례를 기다리고 있습니다" : "쪽 이미지를 만드는 중입니다"}
          </span>
          {total > 0 && (
            <div className="w-full">
              <Progress value={(doc.preprocess.done / total) * 100} label="쪽 이미지 진행" />
              <p className="mt-2 text-center text-mut tabular-nums">
                {doc.preprocess.done} / {total}쪽
              </p>
            </div>
          )}
        </Paper>
      )}
    </Pane>
  );
}

function PageLines({ id, page, highlight }: { id: string; page: number; highlight?: string | null }) {
  const { data, isPending, isError } = useQuery(pageLinesQuery(id, page));
  const firstHit = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    firstHit.current?.scrollIntoView({ block: "nearest" });
  }, [highlight, data]);
  if (isPending) {
    return (
      <div aria-hidden="true" className="grid gap-2.5">
        <Skeleton className="w-full" />
        <Skeleton className="w-4/5" />
        <Skeleton className="w-2/3" />
      </div>
    );
  }
  if (isError) return <p className="text-mut">이 쪽의 글을 읽지 못했습니다.</p>;
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

function PageImage({ id, page }: { id: string; page: number }) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return (
      <Paper className="items-center justify-center">
        <p className="text-mut">이 쪽의 이미지를 불러오지 못했습니다.</p>
      </Paper>
    );
  }
  return (
    <div className="rounded-sm bg-paper p-3">
      <img
        src={pageImageUrl(id, page)}
        alt={`원문 ${page}쪽`}
        onError={() => setFailed(true)}
        className="w-full border border-line bg-white"
      />
    </div>
  );
}
