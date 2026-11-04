"use client";

import { useState } from "react";
import type { Finding, JudgmentView } from "@/api/judgment";
import { Button, PillTabs, ScrollTable, StatusLabel, TableHead, TableRow } from "@/components/ui";
import { cn } from "@/lib/cn";
import { buildTable, lawCounts, noteBreakdown, regulationCounts, reviewText, verdictText, verdictTone } from "@/lib/regulation";

const CELL = "min-w-0 flex-[2_1_0] max-lg:basis-[45%]";

/** 2.4 아래쪽: 건수, 법령 거르기, 처리 필요 줄과 접힌 일치·참고 묶음 */
export function RegulationTable({
  view,
  findings,
  law,
  todoOnly,
  selectedId,
  onSelect,
  onLaw,
  onTodoOnly,
}: {
  view: JudgmentView;
  findings: Finding[];
  law: string | null;
  todoOnly: boolean;
  selectedId: string | null;
  onSelect: (finding: Finding) => void;
  onLaw: (law: string | null) => void;
  onTodoOnly: (on: boolean) => void;
}) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const { reviews, display } = view;
  const table = buildTable(findings, display, { law, todoOnly });
  const counts = regulationCounts(findings, reviews);

  const isEmpty = !table.todo.length && !table.matches.length && !table.notes.length;

  const row = (f: Finding) => {
    const d = display[f.id];
    const review = reviewText(f, reviews);
    const verdict = verdictText(f);
    return (
      <TableRow
        key={f.id}
        selected={f.id === selectedId}
        onClick={() => onSelect(f)}
        aria-label={`${f.law_label ?? ""} ${f.label}, ${d.component ?? "제품"}, MSDS ${d.msds}, 규제DB ${d.expected}, ${verdict}${review ? `, ${review}` : ""}`}
        className={cn("max-lg:flex-wrap", f.id === selectedId && "shadow-[inset_4px_0_0_var(--blue)]")}
      >
        <div className="w-18 flex-none font-medium max-lg:w-full max-lg:text-sm max-lg:text-mut">{f.law_label ?? "—"}</div>
        <div className={cn(CELL, "font-bold")}>{f.label}</div>
        <div className={CELL}>{d.component ?? "제품"}</div>
        <div className={CELL}>{d.msds}</div>
        <div className={CELL}>{d.expected}</div>
        <div className={cn(CELL, "flex flex-col")}>
          <StatusLabel tone={verdictTone(f)}>{verdict}</StatusLabel>
          {review && <span className={cn("text-xs", review === "다시 확인 필요" ? "text-stale" : "text-mut")}>{review}</span>}
        </div>
      </TableRow>
    );
  };

  /** 고른 줄이 묶음 안에 있으면 처음부터 펼쳐 둔다 (검토 이력에서 바로 온 경우). 2항 표와 같다 */
  const group = (key: string, title: string, rows: Finding[]) => {
    const expanded = open[key] ?? rows.some((f) => f.id === selectedId);
    return (
      <div key={key}>
        <button
          type="button"
          aria-expanded={expanded}
          onClick={() => setOpen((prev) => ({ ...prev, [key]: !expanded }))}
          className="block w-full border-b border-line2 bg-white px-4 py-2.5 text-left text-mut"
        >
          {expanded ? "▾" : "▸"} {title}
        </button>
        {expanded && rows.map(row)}
      </div>
    );
  };

  return (
    <section className="flex flex-col gap-3" aria-label="15항 판정 표">
      <p className="text-sm">
        불일치 <strong>{counts.mismatch}</strong> · 경계 <strong>{counts.border}</strong> · 근거부족 <strong>{counts.lacking}</strong>
        {counts.warning > 0 && (
          <>
            {" "}
            · 경고 <strong>{counts.warning}</strong>
          </>
        )}{" "}
        · 일치 <strong>{counts.match}</strong> · 참고 <strong>{counts.note}</strong>
        <span className="text-mut"> | </span>
        미처리 <strong className={counts.unreviewed ? "text-red" : "text-grn"}>{counts.unreviewed}</strong>
      </p>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PillTabs
          label="법령 거르기"
          value={law ?? "all"}
          onChange={(id) => onLaw(id === "all" ? null : id)}
          items={[
            { id: "all", label: `전체 ${findings.length}` },
            ...lawCounts(findings).map((c) => ({ id: c.law, label: `${c.law} ${c.count}` })),
          ]}
        />
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={todoOnly} onChange={(e) => onTodoOnly(e.target.checked)} />
          처리 필요만
        </label>
      </div>
      <ScrollTable follow={selectedId}>
        <TableHead sticky className="max-lg:hidden">
          <div className="w-18 flex-none">법령</div>
          <div className={CELL}>규제 항목</div>
          <div className={CELL}>성분 (함량)</div>
          <div className={CELL}>MSDS 기재</div>
          <div className={CELL}>규제DB 결과 (기준)</div>
          <div className={CELL}>판정 · 처리</div>
        </TableHead>
        {table.todo.map(row)}
        {table.matches.map((m) => group(`match:${m.component}`, `${m.component}: 일치 ${m.items.length}건`, m.items))}
        {table.notes.length > 0 && group("notes", `참고 · 판정 제외 ${table.notes.length}건 (${noteBreakdown(table.notes)})`, table.notes)}
        {isEmpty && (
          <div className="flex flex-col items-center gap-2 px-4 py-8 text-center text-mut">
            {findings.length === 0 ? (
              <p>15항에서 판정할 항목이 없습니다.</p>
            ) : (
              <>
                <p>이 조건에 처리할 항목이 없습니다.</p>
                <Button
                  onClick={() => {
                    onLaw(null);
                    onTodoOnly(false);
                  }}
                >
                  거르기 지우기
                </Button>
              </>
            )}
          </div>
        )}
      </ScrollTable>
    </section>
  );
}
