"use client";

import { useState } from "react";
import type { FindingsResponse, FindingSummary } from "@/api/findings-schemas";
import { StatusLabel, Table, TableHead, TableRow } from "@/components/ui";
import { cn } from "@/lib/cn";
import { SEVERITY_LABEL, VERDICT_LABEL, VERDICT_TONE } from "../hazard/verdict";

const COLS = {
  law: "w-18 flex-none",
  item: "basis-0 grow-2",
  msds: "basis-0 grow-2",
  expected: "basis-0 grow-3",
  verdict: "w-28 flex-none",
} as const;

/** 성분 묶음이 없는 제품 단위 판정의 묶음 번호 (demo-findings 의 PRODUCT_GROUP_ID 와 같다) */
const PRODUCT_GROUP = "product";

function Row({ r, selected, onSelect }: { r: FindingSummary; selected: boolean; onSelect: (id: string) => void }) {
  return (
    <TableRow
      selected={selected}
      onClick={() => onSelect(r.finding_id)}
      className={cn("border-l-4", selected ? "border-l-stale" : "border-l-transparent")}
    >
      <span className={cn(COLS.law, "font-medium")}>{r.law}</span>
      <span className={cn(COLS.item, r.verdict !== "match" && "font-bold")}>{r.item}</span>
      <span className={COLS.msds}>{r.msds_value.text}</span>
      <span className={COLS.expected}>{r.expected_value.text}</span>
      <span className={cn(COLS.verdict, "flex flex-wrap items-center gap-x-1.5")}>
        <StatusLabel tone={VERDICT_TONE[r.verdict]} className="text-base">
          {VERDICT_LABEL[r.verdict]}
        </StatusLabel>
        {r.severity && <span className="text-xs text-amb-text">· {SEVERITY_LABEL[r.severity]}</span>}
      </span>
    </TableRow>
  );
}

/** 15항 판정 표: 성분별로 묶어 접고 펼 수 있다. 행을 누르면 고른다. */
export function RegulationTable({
  rows,
  groups,
  selectedId,
  onSelect,
}: {
  rows: FindingSummary[];
  groups: FindingsResponse["groups"];
  selectedId: string | undefined;
  onSelect: (id: string) => void;
}) {
  const [closed, setClosed] = useState<Record<string, boolean>>({});
  const groupOf = (r: FindingSummary) => r.component_id ?? PRODUCT_GROUP;
  const known = new Set(groups.map((g) => g.component_id));
  // 묶음 정보가 없는 행은 맨 아래에 따로 둔다
  const loose = rows.filter((r) => !known.has(groupOf(r)));

  return (
    <Table>
      <div className="min-w-120">
        <TableHead>
          <span className={COLS.law}>법령</span>
          <span className={COLS.item}>규제 항목</span>
          <span className={COLS.msds}>MSDS 기재</span>
          <span className={COLS.expected}>규제DB 결과 (기준)</span>
          <span className={COLS.verdict}>판정</span>
        </TableHead>
        {rows.length === 0 && <p className="px-4 py-3 text-sm text-mut">조건에 맞는 항목이 없습니다.</p>}
        {groups.map((g) => {
          const items = rows.filter((r) => groupOf(r) === g.component_id);
          if (items.length === 0) return null;
          const open = !closed[g.component_id];
          const panelId = `reg-group-${g.component_id}`;
          return (
            <div key={g.component_id}>
              <button
                type="button"
                aria-expanded={open}
                aria-controls={panelId}
                onClick={() => setClosed({ ...closed, [g.component_id]: open })}
                className="flex w-full items-center gap-2 border-b border-line2 bg-tint px-4 py-2 text-left text-sm"
              >
                <span aria-hidden="true">{open ? "▾" : "▸"}</span>
                <span className="font-medium">{g.title}</span>
                <span className="text-mut">
                  {g.total}건 · 일치 {g.matching_count}건
                </span>
              </button>
              {open && (
                <div id={panelId}>
                  {items.map((r) => (
                    <Row key={r.finding_id} r={r} selected={r.finding_id === selectedId} onSelect={onSelect} />
                  ))}
                </div>
              )}
            </div>
          );
        })}
        {loose.map((r) => (
          <Row key={r.finding_id} r={r} selected={r.finding_id === selectedId} onSelect={onSelect} />
        ))}
      </div>
    </Table>
  );
}
