"use client";

import { useState } from "react";
import { PRODUCT_GROUP_ID, type FindingsResponse, type FindingSummary } from "@/api/findings-schemas";
import { StatusLabel } from "@/components/ui";
import { ProcessedMark } from "../hazard/findings-table";
import { SEVERITY_LABEL, VERDICT_LABEL, VERDICT_TONE } from "../hazard/verdict";
import { NoBreakDates } from "../shared/nowrap-dates";
import { Cell, GridBody, GridHead, GridRow, GridTable, HeadCell, SpanRow } from "../shared/grid-table";

/*
 * 열: 법령 | 규제 항목 | MSDS 기재 | 규제DB 결과 | 판정.
 * 표 칸이 좁으면(1024px 폭) 낱말이 쪼개지지 않도록 법령과 "MSDS 기재"를 항목 아래 작은 글씨로 옮긴다.
 * "판정" 열은 늘 보인다.
 */
const COLS =
  "grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)_7.25rem] @[34rem]:grid-cols-[4.5rem_minmax(0,3fr)_minmax(0,2fr)_minmax(0,3fr)_7.25rem]";
const WIDE = "hidden @[34rem]:block";

function Row({ r, selected, onSelect }: { r: FindingSummary; selected: boolean; onSelect: (id: string) => void }) {
  return (
    <GridRow cols={COLS} selected={selected} onSelect={() => onSelect(r.finding_id)}>
      <Cell className={WIDE}>
        <span className="font-medium">{r.law}</span>
      </Cell>
      <Cell className={r.verdict !== "match" ? "font-bold" : undefined}>
        <button type="button" className="text-left [word-break:keep-all] break-words">
          {r.item}
        </button>
        <span className="block text-xs font-normal text-mut @[34rem]:hidden">
          {r.law} · MSDS: {r.msds_value.text}
        </span>
        <ProcessedMark findingId={r.finding_id} />
      </Cell>
      <Cell className={WIDE}><NoBreakDates text={r.msds_value.text} /></Cell>
      <Cell><NoBreakDates text={r.expected_value.text} /></Cell>
      <Cell className="flex flex-wrap items-center gap-x-1.5">
        <StatusLabel tone={VERDICT_TONE[r.verdict]} className="text-sm">
          {VERDICT_LABEL[r.verdict]}
        </StatusLabel>
        {r.severity && <span className="text-xs text-amb-text">· {SEVERITY_LABEL[r.severity]}</span>}
      </Cell>
    </GridRow>
  );
}

/** 15항 판정 표: 성분별로 묶어 접고 펼 수 있다. 행을 누르면 고른다. */
export function RegulationTable({
  rows,
  groups,
  filtered,
  selectedId,
  onSelect,
}: {
  rows: FindingSummary[];
  groups: FindingsResponse["groups"];
  /** 법령·불일치 거르기를 쓰는 중이면 머리줄에 표시한 건수와 전체 건수를 나란히 보여 준다 */
  filtered: boolean;
  selectedId: string | undefined;
  onSelect: (id: string) => void;
}) {
  const [closed, setClosed] = useState<Record<string, boolean>>({});
  const groupOf = (r: FindingSummary) => r.component_id ?? PRODUCT_GROUP_ID;
  const known = new Set(groups.map((g) => g.component_id));
  // 묶음 정보가 없는 행은 맨 아래에 따로 둔다
  const loose = rows.filter((r) => !known.has(groupOf(r)));

  return (
    <GridTable label="15항 판정 표">
      <GridHead cols={COLS}>
        <HeadCell className={WIDE}>법령</HeadCell>
        <HeadCell>규제 항목</HeadCell>
        <HeadCell className={WIDE}>MSDS 기재</HeadCell>
        <HeadCell>규제DB 결과 (기준)</HeadCell>
        <HeadCell>판정</HeadCell>
      </GridHead>
      {rows.length === 0 && <SpanRow className="block px-3 py-3 text-sm text-mut">조건에 맞는 항목이 없습니다.</SpanRow>}
      {groups.map((g) => {
        const items = rows.filter((r) => groupOf(r) === g.component_id);
        if (items.length === 0) return null;
        const open = !closed[g.component_id];
        const panelId = `reg-group-${g.component_id}`;
        return (
          <GridBody key={g.component_id} aria-label={g.title}>
            <SpanRow className="block border-b border-line2 bg-tint">
              <button
                type="button"
                aria-expanded={open}
                aria-controls={panelId}
                onClick={() => setClosed({ ...closed, [g.component_id]: open })}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm"
              >
                <span aria-hidden="true">{open ? "▾" : "▸"}</span>
                <span className="font-medium">{g.title}</span>
                <span className="text-mut">
                  {filtered ? `${items.length}건 표시 · 전체 ${g.total}건` : `${g.total}건 · 일치 ${g.matching_count}건`}
                </span>
              </button>
            </SpanRow>
            {open && (
              <div id={panelId} role="presentation">
                {items.map((r) => (
                  <Row key={r.finding_id} r={r} selected={r.finding_id === selectedId} onSelect={onSelect} />
                ))}
              </div>
            )}
          </GridBody>
        );
      })}
      {loose.length > 0 && (
        <GridBody>
          {loose.map((r) => (
            <Row key={r.finding_id} r={r} selected={r.finding_id === selectedId} onSelect={onSelect} />
          ))}
        </GridBody>
      )}
    </GridTable>
  );
}
