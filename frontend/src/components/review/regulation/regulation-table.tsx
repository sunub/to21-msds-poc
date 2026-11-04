"use client";

import { useState } from "react";
import type { Finding, JudgmentView } from "@/api/judgment";
import { Button, PillTabs, ScrollTable, StatusLabel, TableHead, TableRow } from "@/components/ui";
import { cn } from "@/lib/cn";
import { buildTable, lawCounts, noteBreakdown, regulationCounts, reviewText, verdictText, verdictTone } from "@/lib/regulation";

/** 검토 화면 세 표가 같이 쓰는 "떠 있는 행" 스타일. 컨테이너·머리줄·행·고른 행 */
export const FLOAT_TABLE = "gap-0 rounded-xl border-blue-line bg-tint p-1.5";
// 머리줄은 위에 붙어 스크롤하므로 완전 투명 대신 컨테이너와 같은 색으로 (겹쳐 비치지 않게)
export const FLOAT_HEAD = "rounded-[10px] border-b-0 bg-tint";
// 행 구분선: 각 행(과 접힘 줄) 위에 좌우 12px 안쪽의 1px 선. 머리줄과 첫 행 사이·접힘 줄 위도 이 선이고, 마지막 행 아래에는 없다.
// 고른 행의 위 선과, 고른 행 바로 다음 행의 위 선은 숨겨 고른 행이 떠 보이게 한다.
export const FLOAT_ROW =
  "relative rounded-[10px] border-b-0 bg-transparent hover:bg-white/60 before:pointer-events-none before:absolute before:inset-x-3 before:top-0 before:h-px before:bg-line2 [[aria-current]+&]:before:hidden";
const FLOAT_ROW_ON = "bg-white before:hidden shadow-[0_2px_10px_rgba(37,99,235,.18),0_0_0_1px_#cfe0ff] hover:bg-white";
export const floatRow = (selected: boolean, ...more: string[]) => cn(FLOAT_ROW, selected && FLOAT_ROW_ON, ...more);

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
        className={floatRow(f.id === selectedId, "max-lg:flex-wrap")}
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
          className={cn("block w-full px-4 py-2.5 text-left text-mut", FLOAT_ROW)}
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
      <ScrollTable follow={selectedId} className={FLOAT_TABLE}>
        <TableHead sticky className={cn("max-lg:hidden", FLOAT_HEAD)}>
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
