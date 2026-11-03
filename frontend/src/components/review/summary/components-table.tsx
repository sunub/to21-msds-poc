"use client";

import type { ComponentSummary } from "@/api/components-schemas";
import { StatusLabel, Table, TableHead, TableRow } from "@/components/ui";
import { cn } from "@/lib/cn";
import { classificationChip, confidenceView, formatConcentration } from "./format";

const COLS = {
  name: "min-w-0 basis-0 grow-[10] [word-break:keep-all] break-words",
  cas: "min-w-0 basis-0 grow-[12] break-keep",
  conc: "min-w-0 basis-0 grow-[8] break-keep",
  cls: "min-w-0 basis-0 grow-30 [word-break:keep-all] break-words",
  ate: "min-w-0 basis-0 grow-30 [word-break:keep-all] break-words",
  legal: "min-w-0 basis-0 grow-[12] break-keep",
  conf: "min-w-0 basis-0 grow-[10]",
} as const;

/** 구성성분별 판단 요약 표. 행을 누르면 위의 성분 상세가 바뀐다 */
export function ComponentsTable({
  items,
  selectedId,
  onSelect,
}: {
  items: ComponentSummary[];
  selectedId: string | undefined;
  onSelect: (id: string) => void;
}) {
  return (
    <Table>
      <div className="min-w-180">
        <TableHead>
          <span className={COLS.name}>성분</span>
          <span className={COLS.cas}>CAS</span>
          <span className={COLS.conc}>함량 %</span>
          <span className={COLS.cls}>기준 분류 (출처)</span>
          <span className={COLS.ate}>사용 ATE (단계)</span>
          <span className={COLS.legal}>15항 해당</span>
          <span className={COLS.conf}>자료 신뢰도</span>
        </TableHead>
        {items.map((c) => {
          const selected = c.component_id === selectedId;
          const conf = confidenceView(c.confidence);
          // 칩이 출처마다 겹치므로 한 번씩만 적는다
          const chips = [...new Set(c.classifications.map(classificationChip))];
          return (
            <TableRow
              key={c.component_id}
              selected={selected}
              onClick={() => onSelect(c.component_id)}
              className={cn("items-start border-l-4", selected ? "border-l-blue" : "border-l-transparent")}
            >
              <span className={cn(COLS.name, "font-bold")}>{c.name}</span>
              <span className={COLS.cas}>{c.cas_no ?? "—"}</span>
              <span className={COLS.conc}>{formatConcentration(c.concentration)}</span>
              <span className={COLS.cls}>
                {chips.join(" · ")}
                {c.classifications[0] && ` (${c.classifications[0].basis})`}
              </span>
              <span className={cn(COLS.ate, !c.used_ate.applicable && "text-mut")}>{c.used_ate.reason}</span>
              <span className={COLS.legal}>{c.regulation_hits > 0 ? `${c.regulation_hits}건 해당` : "없음"}</span>
              <span className={COLS.conf}>
                <StatusLabel tone={conf.tone} className="text-base">
                  {conf.label}
                </StatusLabel>
              </span>
            </TableRow>
          );
        })}
      </div>
    </Table>
  );
}
