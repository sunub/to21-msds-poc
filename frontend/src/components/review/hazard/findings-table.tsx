"use client";

import { useState } from "react";
import type { FindingSummary } from "@/api/findings-schemas";
import { PillTabs, StatusLabel, Table, TableHead, TableRow } from "@/components/ui";
import { cn } from "@/lib/cn";
import { useReviewState } from "../review-state";
import { SEVERITY_LABEL, VERDICT_LABEL, VERDICT_TONE } from "./verdict";

export type SortKey = "verdict" | "severity";

const SORTS: { id: SortKey; label: string }[] = [
  { id: "verdict", label: "판정 순" },
  { id: "severity", label: "심각도 순" },
];

/** 처리한 판정의 표시 (공유 상태에서 읽는다). 처리 전이면 아무것도 그리지 않는다 */
export function ProcessedMark({ findingId }: { findingId: string }) {
  const { state } = useReviewState().getState(findingId);
  if (state === "unreviewed") return null;
  return <span className="block text-xs font-medium text-grn">{state === "confirmed" ? "확정함" : "예외 승인함"}</span>;
}

const COLS = {
  item: "min-w-0 basis-0 grow-3 break-keep break-words",
  msds: "min-w-0 basis-0 grow-2 break-keep break-words",
  expected: "min-w-0 basis-0 grow-3 break-keep break-words",
  method: "min-w-0 basis-0 grow-2 break-keep break-words",
  verdict: "min-w-0 basis-0 grow-2 break-keep break-words",
} as const;

/** 2항 판정 표: 판정 종류로 거르고, 행을 눌러 고른다. 일치 행은 전체 보기에서 접어 둔다. */
export function FindingsTable({
  rows,
  filter,
  filterItems,
  onFilter,
  sort,
  onSort,
  selectedId,
  onSelect,
  matchCount,
  excludedCount,
}: {
  rows: FindingSummary[];
  filter: string;
  filterItems: { id: string; label: string }[];
  onFilter: (id: string) => void;
  sort: SortKey;
  onSort: (key: SortKey) => void;
  selectedId: string | undefined;
  onSelect: (id: string) => void;
  /** 전체 보기에서 접어 둘 일치 행의 수 */
  matchCount: number;
  excludedCount: number;
}) {
  const [showMatches, setShowMatches] = useState(false);
  const collapsible = filter === "all" && matchCount > 0;
  const visible = collapsible && !showMatches ? rows.filter((r) => r.verdict !== "match") : rows;

  return (
    <div className="flex flex-col gap-3">
      <PillTabs label="판정 종류로 거르기" items={filterItems} value={filter} onChange={onFilter} />
      <div role="group" aria-label="정렬 기준" className="flex flex-wrap items-center gap-1 text-sm text-mut">
        <span>정렬</span>
        {SORTS.map((s) => (
          <button
            key={s.id}
            type="button"
            aria-pressed={sort === s.id}
            onClick={() => onSort(s.id)}
            className={cn("rounded-sm px-2 py-0.5", sort === s.id ? "bg-blue-soft font-bold text-blue2" : "text-mut")}
          >
            {s.label}
          </button>
        ))}
      </div>

      <Table>
        <div className="min-w-140">
          <TableHead>
            <span className={COLS.item}>유해성 항목</span>
            <span className={COLS.msds}>MSDS 기재</span>
            <span className={COLS.expected}>검증 결과</span>
            <span className={COLS.method}>판정 방법</span>
            <span className={COLS.verdict}>판정</span>
          </TableHead>
          {visible.length === 0 && <p className="px-4 py-3 text-sm text-mut">이 판정 종류에 해당하는 항목이 없습니다.</p>}
          {visible.map((r) => {
            const selected = r.finding_id === selectedId;
            return (
              <TableRow
                key={r.finding_id}
                selected={selected}
                onClick={() => onSelect(r.finding_id)}
                className={cn("border-l-4", selected ? "border-l-blue" : "border-l-transparent")}
              >
                <span className={cn(COLS.item, "font-medium")}>
                  {r.item}
                  <ProcessedMark findingId={r.finding_id} />
                </span>
                <span className={COLS.msds}>{r.msds_value.text}</span>
                <span className={COLS.expected}>{r.expected_value.text}</span>
                <span className={cn(COLS.method, "text-sm text-mut")}>{r.method}</span>
                <span className={cn(COLS.verdict, "flex items-center gap-x-1.5 whitespace-nowrap")}>
                  <StatusLabel tone={VERDICT_TONE[r.verdict]} className="text-base">
                    {VERDICT_LABEL[r.verdict]}
                  </StatusLabel>
                  {r.severity && <span className="text-xs text-amb-text">· {SEVERITY_LABEL[r.severity]}</span>}
                </span>
              </TableRow>
            );
          })}
          {collapsible && (
            <button
              type="button"
              aria-expanded={showMatches}
              onClick={() => setShowMatches(!showMatches)}
              className="w-full border-t border-line2 px-4 py-2.5 text-left text-sub"
            >
              {showMatches ? "▾" : "▸"} 일치 {matchCount}건 ({showMatches ? "접기" : "펼치기"})
            </button>
          )}
        </div>
      </Table>

      {excludedCount > 0 && <p className="text-sm text-mut">범위 외 · 비교 제외 {excludedCount}건</p>}
    </div>
  );
}
