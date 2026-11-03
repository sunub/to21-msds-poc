"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";
import { reviewLogQuery } from "@/api/documents";
import { findingsQuery } from "@/api/findings";
import { judgmentErrorText, judgmentHistoryQuery } from "@/api/judgments";
import type { HistoryEntry } from "@/api/contract/api";
import { Foot, Pane } from "@/components/shell/layout";
import { PillTabs, Table, TableHead } from "@/components/ui";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import { LoadError } from "../shared/load-error";
import { FootActions } from "../shared/foot-actions";
import { useValidationId } from "../shared/use-validation-id";
import { UnresolvedList, findingHref, useUnresolved } from "../unresolved-list";

const AREAS = ["추출값", "2항", "15항", "저장"] as const;

const COLS = {
  at: "w-40 flex-none",
  reviewer: "w-20 flex-none",
  area: "w-16 flex-none",
  target: "min-w-0 basis-0 grow-2 [word-break:keep-all] break-words",
  action: "w-24 flex-none",
  detail: "min-w-0 basis-0 grow-2 [word-break:keep-all] break-words",
  comment: "min-w-0 basis-0 grow-3 [word-break:keep-all] break-words",
  go: "w-20 flex-none",
} as const;

/** "2026-11-02T13:32:41+09:00" → "2026.11.02 13:32:41" (이력의 시각은 이미 한국 시간이다) */
const formatAt = (at: string) => `${at.slice(0, 10).replaceAll("-", ".")} ${at.slice(11, 19)}`;

/** 판정 쪽 이력(B)과 추출값 쪽 이력(A)을 시각순으로 합친다 (최근 것이 위). 같은 시각이면 판정 쪽이 먼저 */
export const mergeHistory = (judgment: HistoryEntry[], extraction: HistoryEntry[]) =>
  [...judgment.map((h, i) => ({ h, t: Date.parse(h.at), order: i })), ...extraction.map((h, i) => ({ h, t: Date.parse(h.at), order: 1e6 + i }))]
    .sort((a, b) => b.t - a.t || a.order - b.order)
    .map((x) => x.h);

/** 2 검수 · 검토 이력 탭: 위에 처리하지 않은 판정, 아래에 처리 이력(최근 순). 이력은 서버가 준다 */
export function HistoryPanel({ docId, onSave }: { docId: string; onSave: () => void }) {
  const unresolved = useUnresolved(docId);
  const validation = useValidationId(docId);
  const hazardQuery = useQuery(findingsQuery(docId, validation, { section: 2 }));
  const regulation = useQuery(findingsQuery(docId, validation, { section: 15 })).data;
  const judgment = useQuery(judgmentHistoryQuery(docId));
  const extraction = useQuery(reviewLogQuery(docId));
  const byId = useMemo(
    () => new Map([...(hazardQuery.data?.items ?? []), ...(regulation?.items ?? [])].map((f) => [f.finding_id, f])),
    [hazardQuery.data, regulation],
  );
  const [filter, setFilter] = useState("all");

  const history = useMemo(() => mergeHistory(judgment.data ?? [], extraction.data ?? []), [judgment.data, extraction.data]);
  const rows = history.filter((h) => filter === "all" || h.area === filter);
  const count = (area: string) => history.filter((h) => h.area === area).length;
  const filterItems = [{ id: "all", label: `전체 ${history.length}` }, ...AREAS.map((a) => ({ id: a, label: `${a} ${count(a)}` }))];

  // 판정을 불러오지 못하면 "처리할 판정이 없다"로 보이지 않게 안내한다
  if (hazardQuery.isError) {
    return <LoadError message={judgmentErrorText(hazardQuery.error, "판정을 불러오지 못했습니다.")} onRetry={() => void hazardQuery.refetch()} />;
  }

  /** 이동 링크: 판정이면 그 판정으로(이전 버전 항목이면 이동하지 않는다), 추출값이면 추출값 탭으로 */
  const goTo = (h: HistoryEntry) => {
    const findingId = typeof h.ref?.finding_id === "string" ? h.ref.finding_id : null;
    if (findingId) {
      const f = byId.get(findingId);
      if (f && h.ref?.in_latest !== false) return { href: findingHref(docId, f), text: "이동 ›", label: `${h.target} 판정으로 이동` };
      return { href: null, text: "이전 판정", label: "" };
    }
    if (h.area === "추출값") return { href: routes.review(docId, "values"), text: "이동 ›", label: `${h.target} 추출값으로 이동` };
    return null;
  };

  return (
    <>
      <Pane
        title={`아직 처리하지 않은 판정 ${unresolved.length}건`}
        aside={
          <span className="text-sm text-mut">
            불일치·경계·근거부족·경고·구버전은 확정, 예외 승인 중 하나로 처리하고 저장합니다. 일치는 처리하지 않아도 됩니다.
          </span>
        }
      >
        <UnresolvedList docId={docId} />
      </Pane>

      <Pane title="검토 이력" aside={<span className="text-sm text-mut">최근 처리가 위로 옵니다</span>}>
        <PillTabs label="구분으로 거르기" items={filterItems} value={filter} onChange={setFilter} />
        {rows.length === 0 ? (
          <p className="text-sm text-mut">
            {history.length === 0 ? "아직 처리한 기록이 없습니다. 추출값을 확인하거나 판정을 처리하면 여기에 기록됩니다." : "이 구분의 이력이 없습니다."}
          </p>
        ) : (
          <Table>
            <div className="min-w-200">
              <TableHead>
                <span className={COLS.at}>시각</span>
                <span className={COLS.reviewer}>검토자</span>
                <span className={COLS.area}>구분</span>
                <span className={COLS.target}>대상</span>
                <span className={COLS.action}>처리</span>
                <span className={COLS.detail}>처리 내용</span>
                <span className={COLS.comment}>의견</span>
                <span className={COLS.go}>
                  <span className="sr-only">이동</span>
                </span>
              </TableHead>
              {rows.map((h, i) => {
                const go = goTo(h);
                return (
                  <div key={`${h.at}-${i}`} className="flex items-start gap-3 border-b border-line2 px-4 py-2.5 text-sm last:border-b-0">
                    <time dateTime={h.at} className={cn(COLS.at, "text-mut tabular-nums")}>
                      {formatAt(h.at)}
                    </time>
                    <span className={cn(COLS.reviewer, "break-words")}>{h.reviewer}</span>
                    <span className={cn(COLS.area, "font-medium")}>{h.area}</span>
                    <span className={cn(COLS.target, "font-medium")}>{h.target}</span>
                    <span className={COLS.action}>{h.action}</span>
                    <span className={cn(COLS.detail, "text-mut")}>{h.detail ?? "-"}</span>
                    <span className={cn(COLS.comment, "text-mut")}>{h.comment ?? "-"}</span>
                    <span className={cn(COLS.go, "text-mut")}>
                      {go &&
                        (go.href ? (
                          <Link href={go.href} aria-label={go.label}>
                            {go.text}
                          </Link>
                        ) : (
                          go.text
                        ))}
                    </span>
                  </div>
                );
              })}
            </div>
          </Table>
        )}
        <p className="text-sm text-mut">이력은 서버에 저장됩니다. 되돌린 처리도 이력에 기록됩니다.</p>
      </Pane>

      <Foot>
        <p className="text-mut">
          {unresolved.length === 0
            ? "처리하지 않은 판정이 없습니다."
            : `처리하지 않은 판정 ${unresolved.length}건은 저장하면 미검토로 남습니다.`}
        </p>
        <FootActions docId={docId} onSave={onSave} />
      </Foot>
    </>
  );
}
