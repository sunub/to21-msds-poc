"use client";

import { useQuery } from "@tanstack/react-query";
import { memo, useMemo } from "react";
import { sectionResultQuery } from "@/api/documents";
import type { DocumentDetail, JobStatus, SectionProgress } from "@/api/schemas";
import { Skeleton, StatusLabel, Table, TableHead, TableRow } from "@/components/ui";
import { describeProblem } from "@/lib/problem-text";
import { flattenValues } from "@/lib/section-values";
import { pagesLabel, sectionLabel } from "@/lib/status";

export type SectionKey = { msds_index: number; section: number };

const same = (a: SectionKey | null, b: SectionProgress) =>
  a?.msds_index === b.msds_index && a?.section === b.section;

/** 항별 진행 표. 항 구분은 (MSDS 순번, 항 번호)다. 항의 진행은 서버가 동시에 돌리고 화면은 응답 하나로 그린다 */
export function SectionProgressTable({
  doc,
  selected,
  onSelect,
}: {
  doc: DocumentDetail;
  selected: SectionKey | null;
  onSelect: (section: SectionProgress) => void;
}) {
  const groups = useMemo(() => {
    const map = new Map<number, SectionProgress[]>();
    for (const s of doc.sections) map.set(s.msds_index, [...(map.get(s.msds_index) ?? []), s]);
    return [...map.entries()];
  }, [doc.sections]);

  return (
    <Table className="overflow-y-auto rounded-sm max-lg:max-h-130 lg:min-h-40 lg:flex-1">
      <TableHead className="sticky top-0 px-3.5 py-2">
        <span className="w-8">항</span>
        <span className="min-w-0 flex-1">제목</span>
        <span className="w-14">쪽</span>
        <span className="w-20">상태</span>
      </TableHead>
      {groups.map(([index, sections]) => (
        <div key={index} role="group" aria-label={`MSDS ${index + 1}건`}>
          {groups.length > 1 && (
            <div className="border-b border-line2 bg-tint px-3.5 py-1.5 text-sm font-medium">MSDS {index + 1}건</div>
          )}
          {sections.map((s) => (
            <SectionRow key={s.section} section={s} docStatus={doc.status} selected={same(selected, s)} onSelect={onSelect} />
          ))}
        </div>
      ))}
    </Table>
  );
}

/** 응답의 구조 공유로 안 바뀐 항은 같은 객체가 와서 다시 그리지 않는다 */
const SectionRow = memo(function SectionRow({
  section,
  docStatus,
  selected,
  onSelect,
}: {
  section: SectionProgress;
  docStatus: JobStatus;
  selected: boolean;
  onSelect: (section: SectionProgress) => void;
}) {
  const { tone, label } = sectionLabel(section, docStatus);
  return (
    <TableRow selected={selected} className="px-3.5 py-2" onClick={() => onSelect(section)}>
      <span className="w-8 tabular-nums">{section.section}</span>
      <span className="min-w-0 flex-1 truncate text-sm">
        {section.title ?? `${section.section}항`}
        {section.reextracted && <span className="ml-1.5 text-xs text-mut">재추출</span>}
      </span>
      <span className="w-14 text-sm text-mut tabular-nums">{pagesLabel(section.pages)}</span>
      <span className="w-20">
        <StatusLabel tone={tone}>{label}</StatusLabel>
      </span>
    </TableRow>
  );
});

/** 고른 항의 값 미리 보기. 끝난 항만 그때 받는다. 펼치기 전 값이라 검수 기준이 아니다 */
export function SectionValues({ docId, section }: { docId: string; section: SectionProgress }) {
  const finished = section.status === "done" || section.status === "failed";
  const { data, isPending, isError } = useQuery({
    ...sectionResultQuery(docId, section.msds_index, section.section, section.reextracted),
    enabled: finished,
  });

  if (!finished) return <p className="text-sm text-mut">{section.section}항은 아직 끝나지 않았습니다. 끝나면 값을 볼 수 있습니다.</p>;
  if (isPending) return <Skeleton className="w-2/3" />;
  if (isError) return <p className="text-sm text-mut">이 항의 값을 불러오지 못했습니다.</p>;

  const rows = flattenValues(data.parsed);
  const problems = [...data.errors, ...data.check_problems];
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-bold">{section.section}항 값 미리 보기</h3>
        {section.seconds !== null && <span className="text-sm text-mut tabular-nums">{section.seconds.toFixed(1)}초</span>}
      </div>
      {problems.length > 0 && (
        <ul className="m-0 list-none p-0 text-sm text-amb-text">
          {problems.slice(0, 5).map((p, i) => {
            const d = describeProblem(p);
            return (
              <li key={i} className="break-words">
                {d.where && <b className="font-bold">{d.where} </b>}
                {d.summary}
              </li>
            );
          })}
          {problems.length > 5 && <li>외 {problems.length - 5}건</li>}
        </ul>
      )}
      {rows.length > 0 ? (
        <dl className="m-0 max-h-60 overflow-y-auto text-sm">
          {rows.map((r) => (
            <div key={r.path} className="flex gap-3 border-b border-line2 py-1 last:border-b-0">
              <dt className="w-2/5 flex-none break-all text-mut">{r.path}</dt>
              <dd className="m-0 min-w-0 break-words">{r.value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="text-sm text-mut">이 항에는 받은 값이 없습니다.</p>
      )}
    </div>
  );
}
