"use client";

import { useState } from "react";
import type { FindingSummary } from "@/api/findings-schemas";
import { PillTabs, StatusLabel } from "@/components/ui";
import { REVIEW_STATE_LABEL, isProcessed, useReviewState } from "../review-state";
import { Cell, GridBody, GridHead, GridRow, GridTable, HeadCell, SpanRow } from "../shared/grid-table";
import { SortToggle } from "../shared/sort-toggle";
import type { SortKey } from "../shared/sort";
import { SEVERITY_LABEL, VERDICT_LABEL, VERDICT_TONE } from "./verdict";

/** 처리한 판정의 표시 (공유 상태에서 읽는다). 처리 전이면 아무것도 그리지 않는다 */
export function ProcessedMark({ findingId }: { findingId: string }) {
  const { state } = useReviewState().getState(findingId);
  if (state === "unreviewed") return null;
  return (
    <span className={isProcessed(state) ? "block text-xs font-medium text-grn" : "block text-xs font-medium text-amb-text"}>
      {REVIEW_STATE_LABEL[state]}
    </span>
  );
}

/*
 * 열: 항목 | MSDS 기재 | 검증 결과 | 판정 방법 | 판정.
 * 표 칸이 좁으면(2항 탭이 1024px 폭일 때) 낱말이 쪼개지지 않도록 "MSDS 기재"는 항목 아래 작은 글씨로 옮기고,
 * "판정 방법"은 숨긴다 (상세 카드의 "판단 근거"에서 본다). "판정" 열은 늘 보인다.
 */
const COLS =
  "grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)_7.25rem] @[34rem]:grid-cols-[minmax(0,3fr)_minmax(0,2fr)_minmax(0,3fr)_minmax(0,2fr)_7.25rem]";
const WIDE = "hidden @[34rem]:block";

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
      <SortToggle sort={sort} onSort={onSort} />

      <GridTable label="2항 판정 표">
        <GridHead cols={COLS}>
          <HeadCell>유해성 항목</HeadCell>
          <HeadCell className={WIDE}>MSDS 기재</HeadCell>
          <HeadCell>검증 결과</HeadCell>
          <HeadCell className={WIDE}>판정 방법</HeadCell>
          <HeadCell>판정</HeadCell>
        </GridHead>
        <GridBody>
          {visible.length === 0 && <SpanRow className="block px-3 py-3 text-sm text-mut">이 판정 종류에 해당하는 항목이 없습니다.</SpanRow>}
          {visible.map((r) => (
            <GridRow key={r.finding_id} cols={COLS} selected={r.finding_id === selectedId} onSelect={() => onSelect(r.finding_id)}>
              <Cell className="font-medium">
                <button type="button" className="text-left font-medium [word-break:keep-all] break-words">
                  {r.item}
                </button>
                <span className="block text-xs font-normal text-mut @[34rem]:hidden">MSDS: {r.msds_value.text}</span>
                <ProcessedMark findingId={r.finding_id} />
              </Cell>
              <Cell className={WIDE}>{r.msds_value.text}</Cell>
              <Cell>{r.expected_value.text}</Cell>
              <Cell className={`${WIDE} text-mut`}>{r.method}</Cell>
              <Cell className="flex flex-wrap items-center gap-x-1.5">
                <StatusLabel tone={VERDICT_TONE[r.verdict]} className="text-sm">
                  {VERDICT_LABEL[r.verdict]}
                </StatusLabel>
                {r.severity && <span className="text-xs text-amb-text">· {SEVERITY_LABEL[r.severity]}</span>}
              </Cell>
            </GridRow>
          ))}
          {collapsible && (
            <SpanRow className="block border-t border-line2">
              <button
                type="button"
                aria-expanded={showMatches}
                onClick={() => setShowMatches(!showMatches)}
                className="w-full px-3 py-2.5 text-left text-sub"
              >
                {showMatches ? "▾" : "▸"} 일치 {matchCount}건 ({showMatches ? "접기" : "펼치기"})
              </button>
            </SpanRow>
          )}
        </GridBody>
      </GridTable>

      {excludedCount > 0 && <p className="text-sm text-mut">범위 외 · 비교 제외 {excludedCount}건</p>}
    </div>
  );
}
