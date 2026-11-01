"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { pageImageUrl, pageLinesQuery } from "@/api/documents";
import type { DocumentDetail } from "@/api/schemas";
import { Pane } from "@/components/shell/layout";
import { Button, Paper, Progress, Skeleton, Spinner } from "@/components/ui";

/**
 * 원문 칸. 텍스트층이 정상이면 쪽 글을, 아니면(또는 아직 모르면) 쪽 이미지를 보여 준다.
 * 전처리가 끝난 쪽만 요청한다 (그 전에는 404). 추출이 끝나지 않아도 읽을 수 있다.
 */
export function SourceViewer({
  doc,
  page,
  onPage,
}: {
  doc: DocumentDetail;
  page: number;
  onPage: (page: number) => void;
}) {
  const total = doc.page_count ?? doc.preprocess.total ?? 0;
  const ready = page <= doc.preprocess.done;

  return (
    <Pane
      title="원문"
      className="basis-115 print:hidden"
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
            <PageLines id={doc.id} page={page} />
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

function PageLines({ id, page }: { id: string; page: number }) {
  const { data, isPending, isError } = useQuery(pageLinesQuery(id, page));
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
  return data.lines.map((line) => (
    <p key={line.id} data-line-id={line.id}>
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
