"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { isJudgmentApiMissing, type Finding, type JudgmentView } from "@/api/judgment";
import { downloadJudgmentReport, type ReportFormat } from "@/api/judgment-report";
import { Button, PillTabs, ScrollTable, StatusLabel, TableHead, TableRow } from "@/components/ui";
import { cn } from "@/lib/cn";
import { buildHazardTable, hazardFilterItems, type HazardFilter } from "@/lib/hazard";
import { noteBreakdown, regulationCounts, reviewText, verdictText, verdictTone } from "@/lib/regulation";

const WIDE = "min-w-0 flex-[3_1_0] max-lg:basis-[45%]";
const NARROW = "min-w-0 flex-[2_1_0] max-lg:basis-[45%]";

/** 2.3 아래쪽: 건수 알약, 리포트, 처리 필요 줄과 접힌 일치·범위 외 묶음 */
export function HazardTable({
  docId,
  view,
  findings,
  filter,
  selected,
  onSelect,
  onFilter,
}: {
  docId: string;
  view: JudgmentView;
  findings: Finding[];
  filter: HazardFilter | null;
  selected: Finding | null;
  onSelect: (finding: Finding) => void;
  onFilter: (filter: HazardFilter | null) => void;
}) {
  const [toggled, setToggled] = useState<Record<string, boolean>>({});
  const { reviews, display } = view;
  const table = buildHazardTable(findings, filter);
  const counts = regulationCounts(findings, reviews);

  const row = (f: Finding) => {
    const d = display[f.id];
    const review = reviewText(f, reviews);
    const verdict = verdictText(f);
    const isSelected = f.id === selected?.id;
    return (
      <TableRow
        key={f.id}
        selected={isSelected}
        onClick={() => onSelect(f)}
        aria-label={`${f.label}, MSDS ${d.msds}, 검증 결과 ${d.expected}, ${f.method}, ${verdict}${review ? `, ${review}` : ""}`}
        className={cn(
          "max-lg:flex-wrap",
          isSelected && (f.verdict === "불일치" ? "shadow-[inset_4px_0_0_var(--red)]" : "shadow-[inset_4px_0_0_var(--blue)]"),
        )}
      >
        <div className={cn(WIDE, "font-bold")}>{f.label}</div>
        <div className={NARROW}>{d.msds}</div>
        <div className={WIDE}>{d.expected}</div>
        <div className={cn(NARROW, "text-sm text-mut")}>{f.method}</div>
        <div className={cn(NARROW, "flex flex-col")}>
          <StatusLabel tone={verdictTone(f)}>{verdict}</StatusLabel>
          {review && <span className={cn("text-xs", review === "다시 확인 필요" ? "text-stale" : "text-mut")}>{review}</span>}
        </div>
      </TableRow>
    );
  };

  /** 고른 줄이 묶음 안에 있으면 처음부터 펼쳐 둔다 (검토 이력에서 바로 온 경우) */
  const group = (key: string, title: string, rows: Finding[]) => {
    const open = toggled[key] ?? rows.some((f) => f.id === selected?.id);
    return (
      <div key={key}>
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setToggled((prev) => ({ ...prev, [key]: !open }))}
          className="block w-full border-b border-line2 bg-white px-4 py-2.5 text-left text-mut"
        >
          {open ? "▾" : "▸"} {title}
        </button>
        {open && rows.map(row)}
      </div>
    );
  };

  const isEmpty = !table.rows.length && !table.matches.length && !table.notes.length;

  return (
    <section className="flex flex-col gap-3" aria-label="2항 판정 표">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <PillTabs
            label="판정 종류로 거르기"
            value={filter ?? "all"}
            onChange={(id) => onFilter(id === "all" ? null : (id as HazardFilter))}
            items={hazardFilterItems(findings)}
          />
          <span className="text-sm">
            미처리 <strong className={counts.unreviewed ? "text-red" : "text-grn"}>{counts.unreviewed}</strong>
          </span>
        </div>
        <ReportButtons docId={docId} />
      </div>
      <ScrollTable follow={selected?.id}>
        <TableHead sticky className="max-lg:hidden">
          <div className={WIDE}>유해성 항목</div>
          <div className={NARROW}>MSDS 기재</div>
          <div className={WIDE}>검증 결과</div>
          <div className={NARROW}>판정 방법</div>
          <div className={NARROW}>판정 · 처리</div>
        </TableHead>
        {table.rows.map(row)}
        {table.matches.length > 0 && group("matches", `일치 ${table.matches.length}건`, table.matches)}
        {table.notes.length > 0 && group("notes", `범위 외 · 비교 제외 ${table.notes.length}건 (${noteBreakdown(table.notes)})`, table.notes)}
        {isEmpty && (
          <div className="flex flex-col items-center gap-2 px-4 py-8 text-center text-mut">
            {findings.length === 0 ? (
              <p>2항에서 판정할 항목이 없습니다.</p>
            ) : (
              <>
                <p>이 판정 종류에 해당하는 항목이 없습니다.</p>
                <Button onClick={() => onFilter(null)}>전체 보기</Button>
              </>
            )}
          </div>
        )}
      </ScrollTable>
    </section>
  );
}

function ReportButtons({ docId }: { docId: string }) {
  const report = useMutation({ mutationFn: (format: ReportFormat) => downloadJudgmentReport(docId, format) });
  const button = (format: ReportFormat, label: string) => (
    <Button disabled={report.isPending} onClick={() => report.mutate(format)}>
      {report.isPending && report.variables === format ? "만드는 중…" : label}
    </Button>
  );
  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex gap-2">
        {button("html", "리포트 (HTML)")}
        {button("xlsx", "리포트 (Excel)")}
      </div>
      {report.isError && (
        <p role="alert" className="text-sm break-words text-red">
          {isJudgmentApiMissing(report.error) ? "리포트 서버 기능이 아직 연결되지 않았습니다." : `리포트를 만들지 못했습니다: ${report.error.message}`}
        </p>
      )}
    </div>
  );
}
