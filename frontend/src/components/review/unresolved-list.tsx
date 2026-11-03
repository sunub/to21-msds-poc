"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo } from "react";
import { findingsQuery } from "@/api/findings";
import type { FindingSummary } from "@/api/findings-schemas";
import { StatusLabel } from "@/components/ui";
import { routes } from "@/lib/routes";
import { SEVERITY_LABEL, VERDICT_LABEL, VERDICT_ORDER, VERDICT_TONE, isActionable, severityRank } from "./hazard/verdict";
import { isResolved, useReviewState } from "./review-state";
import { useValidationId } from "./shared/use-validation-id";

/** 판정이 있는 탭의 주소. 고른 판정은 ?finding= 으로 넘긴다 (판정 패널이 그 판정을 먼저 고른다) */
export const findingHref = (docId: string, f: Pick<FindingSummary, "section" | "finding_id">) =>
  `${routes.review(docId, f.section === 2 ? "hazard" : "regulation")}&finding=${encodeURIComponent(f.finding_id)}`;

/** 처리하지 않은 판정: 2항, 15항 순으로, 같은 항 안에서는 판정 종류와 심각도 순 */
export function useUnresolved(docId: string): FindingSummary[] {
  const { getState } = useReviewState();
  const validation = useValidationId(docId);
  const hazard = useQuery(findingsQuery(docId, validation, { section: 2 })).data;
  const regulation = useQuery(findingsQuery(docId, validation, { section: 15 })).data;
  return useMemo(
    () =>
      [...(hazard?.items ?? []), ...(regulation?.items ?? [])]
        .filter((f) => isActionable(f.verdict) && !isResolved(getState(f.finding_id)))
        .sort(
          (a, b) =>
            a.section - b.section ||
            VERDICT_ORDER.indexOf(a.verdict) - VERDICT_ORDER.indexOf(b.verdict) ||
            severityRank(a.severity) - severityRank(b.severity),
        ),
    [hazard, regulation, getState],
  );
}

/**
 * 처리하지 않은 판정 목록 (검토 이력 탭과 저장 전 경고가 같이 쓴다).
 * "이동"은 그 판정이 있는 탭으로 가고, onNavigate 로 호출한 쪽(예: 대화상자)이 닫을 수 있게 한다.
 */
export function UnresolvedList({ docId, onNavigate }: { docId: string; onNavigate?: () => void }) {
  const items = useUnresolved(docId);
  if (items.length === 0) return <p className="text-sm text-mut">처리하지 않은 판정이 없습니다.</p>;
  return (
    <ul aria-label="처리하지 않은 판정" className="m-0 list-none border-t border-line2 p-0">
      {items.map((f) => (
        <li key={f.finding_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line2 py-2">
          <span className="w-10 flex-none text-sm text-mut tabular-nums">{f.section}항</span>
          <span className="min-w-0 flex-1 basis-32 font-medium break-keep">{f.item}</span>
          <StatusLabel tone={VERDICT_TONE[f.verdict]}>{VERDICT_LABEL[f.verdict]}</StatusLabel>
          {f.severity && <span className="text-xs text-amb-text">· {SEVERITY_LABEL[f.severity]}</span>}
          <Link
            href={findingHref(docId, f)}
            onClick={onNavigate}
            aria-label={`${f.section}항 ${f.item} 판정으로 이동`}
            className="px-1.5 text-sm"
          >
            이동 ›
          </Link>
        </li>
      ))}
    </ul>
  );
}
