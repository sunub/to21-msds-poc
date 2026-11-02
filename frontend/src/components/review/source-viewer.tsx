"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { documentDetailQuery, pageImageUrl, pageLinesQuery } from "@/api/documents";
import { Pane } from "@/components/shell/layout";
import { Button, Paper, Skeleton } from "@/components/ui";
import { cn } from "@/lib/cn";
import { isDemoDoc } from "@/lib/demo";

/**
 * 2항·15항 탭의 원문 칸. 고른 판정의 근거 쪽(refs)으로 넘어가고, 쪽 이전·다음 이동도 된다.
 * 판정이 바뀌면(resetKey) 새 판정의 첫 근거 쪽으로 가고, 같은 판정 안에서 직접 바꾼 쪽은 그대로 둔다.
 * 새 판정에 근거 쪽이 없으면 보던 쪽에 머문다. 좌표(bbox)가 없어 줄 강조는 하지 않는다.
 */
export function FindingSourceViewer({
  docId,
  refs,
  resetKey,
}: {
  docId: string;
  /** 이 판정의 근거 쪽 (source_refs 의 page_no) */
  refs: number[];
  /** 판정이 바뀌었는지 알아보는 값 (finding_id) */
  resetKey: string | undefined;
}) {
  const { data: doc } = useQuery(documentDetailQuery(docId));
  const total = doc?.page_count ?? 0;
  const pages = [...new Set(refs)];

  // key 가 null 이면 아직 직접 고른 쪽이 없다 (처음 보이는 판정도 그 근거 쪽으로 간다)
  const [chosen, setChosen] = useState<{ key: string | undefined | null; page: number }>({ key: null, page: 1 });
  // 판정이 바뀌면 상태도 그 판정의 첫 근거 쪽으로 바꿔 둔다. 화면에서만 바꾸면, 이전 판정으로 돌아왔을 때 옛 쪽이 되살아난다.
  if (chosen.key !== resetKey) setChosen({ key: resetKey, page: pages[0] ?? chosen.page });
  const page = chosen.key === resetKey ? chosen.page : (pages[0] ?? chosen.page);
  const go = (next: number) => setChosen({ key: resetKey, page: next });

  return (
    <Pane
      title="원문"
      className="basis-115 print:hidden"
      aside={
        <div className="flex items-center gap-2">
          <Button aria-label="이전 쪽" disabled={page <= 1} onClick={() => go(page - 1)}>
            ‹
          </Button>
          <span aria-live="polite" className="text-sm text-mut tabular-nums">
            {page}
            {total > 0 && ` / ${total}`}쪽
          </span>
          <Button aria-label="다음 쪽" disabled={total > 0 && page >= total} onClick={() => go(page + 1)}>
            ›
          </Button>
        </div>
      }
    >
      {pages.length > 1 && (
        <div role="group" aria-label="이 판정의 근거 쪽" className="flex flex-wrap items-center gap-1.5 text-sm">
          <span className="text-mut">근거</span>
          {pages.map((p) => (
            <button
              key={p}
              type="button"
              aria-pressed={p === page}
              onClick={() => go(p)}
              className={cn(
                "rounded-sm px-2 py-0.5",
                p === page ? "bg-blue-soft font-bold text-blue2" : "border border-line text-mut",
              )}
            >
              {p}쪽
            </button>
          ))}
        </div>
      )}
      <Paper>
        {/* 데모 문서에는 쪽 이미지가 없어 요청하지 않는다 (404 로그가 남는다) */}
        {!isDemoDoc(docId) && <PageImage key={`${docId}-${page}`} id={docId} page={page} />}
        <PageLines id={docId} page={page} />
      </Paper>
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
  if (data.lines.length === 0) {
    return (
      <p className="text-mut">
        {isDemoDoc(id) ? "이 쪽의 원문은 데모 데이터에 없습니다." : "이 쪽에는 읽은 글이 없습니다."}
      </p>
    );
  }
  return (
    <ol className="m-0 flex list-none flex-col gap-1 p-0 leading-relaxed">
      {data.lines.map((line) => (
        <li key={line.id} data-line-id={line.id} className="flex gap-3">
          <span aria-hidden="true" className="w-6 flex-none text-right text-mut tabular-nums">
            {line.no}
          </span>
          <span className="min-w-0 [word-break:keep-all] break-words">{line.text}</span>
        </li>
      ))}
    </ol>
  );
}

/** 원본 쪽 이미지. 받아 오기 전·실패하면 숨긴다 (전처리 전이면 404) */
function PageImage({ id, page }: { id: string; page: number }) {
  const [loaded, setLoaded] = useState(false);
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={pageImageUrl(id, page)}
      alt={`원문 ${page}쪽`}
      onLoad={() => setLoaded(true)}
      onError={() => setLoaded(false)}
      className={cn("w-full border border-line bg-white", !loaded && "hidden")}
    />
  );
}
