"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";
import { findingsQuery } from "@/api/findings";
import { judgmentErrorText } from "@/api/judgments";
import type { FindingSummary } from "@/api/findings-schemas";
import { Foot, Pane } from "@/components/shell/layout";
import { Button, PillTabs, Table, TableHead } from "@/components/ui";
import { cn } from "@/lib/cn";
import { VERDICT_LABEL } from "../hazard/verdict";
import { useReviewState, type HistoryEntry, type HistoryKind } from "../review-state";
import { LoadError } from "../shared/load-error";
import { useValidationId } from "../shared/use-validation-id";
import { UnresolvedList, findingHref, useUnresolved } from "../unresolved-list";

const KIND_LABEL: Record<HistoryKind, string> = { confirm: "확정", exception: "예외 승인", undo: "되돌림" };

const COLS = {
  at: "w-40 flex-none",
  reviewer: "w-20 flex-none",
  kind: "w-20 flex-none",
  target: "min-w-0 basis-0 grow-2 [word-break:keep-all] break-words",
  content: "min-w-0 basis-0 grow-3 [word-break:keep-all] break-words",
  opinion: "min-w-0 basis-0 grow-3 [word-break:keep-all] break-words",
  go: "w-16 flex-none",
} as const;

/** "2026-11-02T13:32:41+09:00" → "2026.11.02 13:32:41" (이력의 시각은 이미 한국 시간이다) */
const formatAt = (at: string) => `${at.slice(0, 10).replaceAll("-", ".")} ${at.slice(11, 19)}`;

/** 처리 내용: 무엇으로 처리했는지. 판정 목록을 못 찾으면 구분만 보여 준다 */
function contentOf(h: HistoryEntry, f: FindingSummary | undefined) {
  if (h.kind === "undo") return "처리 전으로 되돌림";
  const verdict = f ? VERDICT_LABEL[f.verdict] : "";
  const head = h.kind === "confirm" ? `${verdict} 확정`.trim() : `예외 승인${verdict ? ` · ${verdict}` : ""}`;
  if (!f) return head;
  // 기호 없이 풀어 쓴다: "근거부족 확정 · MSDS 구분1 · 기준값 없음"
  const expected = f.expected_value.text.trim().startsWith("—") ? "기준값 없음" : `기준값 ${f.expected_value.text}`;
  return `${head} · MSDS ${f.msds_value.text} · ${expected}`;
}

/** 2 검수 · 검토 이력 탭: 위에 처리하지 않은 판정, 아래에 처리 이력(최근 순) */
export function HistoryPanel({ docId, onSave }: { docId: string; onSave: () => void }) {
  const { history } = useReviewState();
  const unresolved = useUnresolved(docId);
  const validation = useValidationId(docId);
  const hazardQuery = useQuery(findingsQuery(docId, validation, { section: 2 }));
  const hazard = hazardQuery.data;
  const regulation = useQuery(findingsQuery(docId, validation, { section: 15 })).data;
  const byId = useMemo(
    () => new Map([...(hazard?.items ?? []), ...(regulation?.items ?? [])].map((f) => [f.finding_id, f])),
    [hazard, regulation],
  );
  const [filter, setFilter] = useState("all");

  // 최근 처리가 위로 온다
  const rows = useMemo(() => [...history].reverse().filter((h) => filter === "all" || h.kind === filter), [history, filter]);
  const count = (k: HistoryKind) => history.filter((h) => h.kind === k).length;
  const filterItems = [
    { id: "all", label: `전체 ${history.length}` },
    ...(Object.keys(KIND_LABEL) as HistoryKind[]).map((k) => ({ id: k, label: `${KIND_LABEL[k]} ${count(k)}` })),
  ];

  // 판정을 불러오지 못하면 "처리할 판정이 없다"로 보이지 않게 안내한다
  if (hazardQuery.isError) {
    return <LoadError message={judgmentErrorText(hazardQuery.error, "판정을 불러오지 못했습니다.")} onRetry={() => void hazardQuery.refetch()} />;
  }

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
            {history.length === 0 ? "아직 처리한 판정이 없습니다. 판정을 확정하거나 예외 승인하면 여기에 기록됩니다." : "이 구분의 이력이 없습니다."}
          </p>
        ) : (
          <Table>
            <div className="min-w-180">
              <TableHead>
                <span className={COLS.at}>시각</span>
                <span className={COLS.reviewer}>검토자</span>
                <span className={COLS.kind}>구분</span>
                <span className={COLS.target}>대상</span>
                <span className={COLS.content}>처리 내용</span>
                <span className={COLS.opinion}>의견</span>
                <span className={COLS.go}>
                  <span className="sr-only">이동</span>
                </span>
              </TableHead>
              {rows.map((h) => {
                const f = byId.get(h.findingId);
                return (
                  <div key={h.id} className="flex items-start gap-3 border-b border-line2 px-4 py-2.5 text-sm last:border-b-0">
                    <time dateTime={h.at} className={cn(COLS.at, "text-mut tabular-nums")}>
                      {formatAt(h.at)}
                    </time>
                    <span className={cn(COLS.reviewer, "break-words")}>{h.reviewer}</span>
                    <span className={cn(COLS.kind, "font-medium")}>{KIND_LABEL[h.kind]}</span>
                    <span className={cn(COLS.target, "font-medium")}>
                      {h.section}항 · {h.target}
                    </span>
                    <span className={COLS.content}>{contentOf(h, f)}</span>
                    <span className={cn(COLS.opinion, "text-mut")}>{h.opinion || "—"}</span>
                    <span className={COLS.go}>
                      {f && (
                        <Link href={findingHref(docId, f)} aria-label={`${h.section}항 ${h.target} 판정으로 이동`}>
                          이동 ›
                        </Link>
                      )}
                    </span>
                  </div>
                );
              })}
            </div>
          </Table>
        )}
        <p className="text-sm text-mut">이 이력은 이 브라우저 탭에만 남습니다. 되돌린 처리도 이력에 기록됩니다.</p>
      </Pane>

      <Foot>
        <p className="text-mut">
          {unresolved.length === 0
            ? "처리하지 않은 판정이 없습니다."
            : `처리하지 않은 판정 ${unresolved.length}건은 저장하면 미검토로 남습니다.`}
        </p>
        <Button variant="primary" size="lg" onClick={onSave}>
          저장하기
        </Button>
      </Foot>
    </>
  );
}
