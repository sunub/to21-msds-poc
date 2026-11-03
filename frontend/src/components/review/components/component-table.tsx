"use client";

import type { ComponentSummary } from "@/api/judgment";
import { StatusLabel, Table, TableHead, TableRow } from "@/components/ui";
import { cn } from "@/lib/cn";
import { ateSummary, classesText, formatContent, hitsText, reliabilityTone } from "@/lib/components";

/** 시안 '구성성분별 판단 요약' 표. 줄을 누르면 위 성분 상세가 그 성분으로 바뀐다 */
export function ComponentTable({
  components,
  productType,
  selected,
  onSelect,
}: {
  components: ComponentSummary[];
  productType: string;
  selected: string | null;
  onSelect: (compRef: string) => void;
}) {
  return (
    <section aria-labelledby="component-table-title" className="flex flex-col gap-2.5">
      <h2 id="component-table-title" className="text-base font-bold">
        구성성분별 판단 요약
      </h2>
      <Table>
        <div className="min-w-[960px]">
          <TableHead>
            <div className="flex-[1_1_0]">성분</div>
            <div className="flex-[1.2_1_0]">CAS</div>
            <div className="flex-[0.8_1_0]">함량 %</div>
            <div className="flex-[3_1_0]">기준 분류 (출처)</div>
            <div className="flex-[3_1_0]">사용 ATE (단계)</div>
            <div className="flex-[1.2_1_0]">15항 해당</div>
            <div className="flex-[1_1_0]">자료 신뢰도</div>
          </TableHead>
          {components.map((c) => {
            const on = c.comp_ref === selected;
            return (
              <TableRow
                key={c.comp_ref}
                selected={on}
                onClick={() => onSelect(c.comp_ref)}
                className={cn("items-start", on && "border-l-4 border-l-blue")}
              >
                <div className="flex-[1_1_0] font-bold break-words">{c.name ?? `성분 ${c.comp_ref}`}</div>
                <div className="flex-[1.2_1_0] break-words">{c.cas ?? "-"}</div>
                <div className="flex-[0.8_1_0]">{formatContent(c.content)}</div>
                <div className="flex-[3_1_0] break-words">{classesText(c.reference_classes)}</div>
                <div className="flex-[3_1_0] break-words">{ateSummary(c.ate, productType)}</div>
                <div className="flex-[1.2_1_0]">{hitsText(c.regulation_hits)}</div>
                <div className="flex-[1_1_0]">
                  <StatusLabel tone={reliabilityTone(c.reliability)} className="text-base text-ink">
                    {c.reliability}
                  </StatusLabel>
                </div>
              </TableRow>
            );
          })}
        </div>
      </Table>
    </section>
  );
}
