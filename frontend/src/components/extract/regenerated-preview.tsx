"use client";

import { useQuery } from "@tanstack/react-query";
import { ApiRequestError } from "@/api/client";
import { regeneratedQuery } from "@/api/documents";
import type { DocumentDetail, RegeneratedResponse } from "@/api/schemas";
import { Pane } from "@/components/shell/layout";
import { Button, Skeleton, StatusLabel } from "@/components/ui";
import { cn } from "@/lib/cn";

type RegenSection = RegeneratedResponse["msds"][number]["sections"][number];

/**
 * 끝난 문서의 재생성 MSDS. 추출값으로 문서를 다시 만든 것으로(추출 대상 1·2·3·8·9·11·12·14·15항만 담긴다), 모델을 다시 부르지 않는다.
 * PDF 는 브라우저 인쇄로 저장한다 (인쇄할 때는 이 칸만 남는다).
 */
export function RegeneratedPreview({
  doc,
  onSection,
}: {
  doc: DocumentDetail;
  onSection: (msdsIndex: number, section: number) => void;
}) {
  const { data, isPending, isError, error, refetch } = useQuery(regeneratedQuery(doc.id));

  return (
    <Pane
      title="재생성 MSDS"
      className="basis-105 print:border-0 print:p-0"
      aside={
        <Button disabled={!data} onClick={() => window.print()} className="print:hidden">
          PDF로 저장
        </Button>
      }
    >
      <p className="text-sm text-mut print:hidden">
        추출값만으로 다시 만든 문서입니다. 검수 전이라 원문과 다를 수 있습니다. 항 제목을 누르면 원문이 그 페이지로 옮겨 갑니다.
      </p>
      {isPending ? (
        <div aria-hidden="true" className="grid gap-2.5">
          <Skeleton className="w-full" />
          <Skeleton className="w-4/5" />
          <Skeleton className="w-2/3" />
        </div>
      ) : isError ? (
        <div role="alert" className="flex flex-col items-start gap-2 text-sm">
          <p className="text-red">{error instanceof ApiRequestError ? error.message : "재생성 결과를 받지 못했습니다."}</p>
          <Button onClick={() => void refetch()}>
            다시 불러오기
          </Button>
        </div>
      ) : (
        <div className="max-h-200 overflow-y-auto rounded-sm bg-paper p-3 print:max-h-none print:overflow-visible print:bg-white print:p-0">
          {data.msds.map((m) => (
            <article
              key={m.msds_index}
              className="mb-3 border border-line bg-white px-6 py-5 text-sm last:mb-0 print:mb-0 print:break-after-page print:border-0 print:p-0 print:last:break-after-auto"
            >
              {data.msds.length > 1 && <p className="mb-2 text-mut">MSDS {m.msds_index + 1}건</p>}
              {m.header.map((line, i) => (
                <p key={i} className={cn(i === 0 && "text-lg font-bold")}>
                  {line}
                </p>
              ))}
              {m.sections.map((s) => (
                <RegenSectionBlock key={s.section} section={s} onOpen={() => onSection(m.msds_index, s.section)} />
              ))}
            </article>
          ))}
        </div>
      )}
    </Pane>
  );
}

function RegenSectionBlock({ section, onOpen }: { section: RegenSection; onOpen: () => void }) {
  const failed = section.status === "failed";
  return (
    <section className="mt-4">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-1">
        <h3 className="m-0 font-bold">
          <button type="button" onClick={onOpen} className="cursor-pointer text-left font-bold print:cursor-auto">
            {section.section}. {section.title}
          </button>
        </h3>
        {failed ? (
          <StatusLabel tone="danger">추출 실패</StatusLabel>
        ) : (
          section.needs_review && <StatusLabel tone="warning">검토 필요</StatusLabel>
        )}
      </div>
      {failed && <p className="mt-1 text-red">이 항은 추출하지 못해 아래 내용이 비어 있습니다.</p>}
      <div className="mt-1.5 flex flex-col gap-0.5">
        {section.lines.map((line, i) =>
          line.kind === "item" ? (
            <p key={i} className="ml-3 break-words">
              {line.text}
            </p>
          ) : (
            <p key={i} className="mt-1 font-medium break-words">
              {line.text}
            </p>
          ),
        )}
      </div>
    </section>
  );
}
