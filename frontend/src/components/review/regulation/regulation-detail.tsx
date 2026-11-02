"use client";

import { useQuery } from "@tanstack/react-query";
import { findingDetailQuery } from "@/api/findings";
import type { FindingSummary } from "@/api/findings-schemas";
import { FindingDetailView, type Decision } from "../hazard/finding-detail";

/**
 * 15항 판정의 상세. 2항과 같은 상세 위에 법령과 기준일을 한 줄로 붙인다.
 * 구버전이면 시행일 기준임을 밝힌다. 같은 상세 요청이라 FindingDetailView 와 캐시를 나눠 쓴다.
 */
export function RegulationDetail({
  docId,
  validationId,
  finding,
  decision,
  onDecide,
}: {
  docId: string;
  validationId: string;
  finding: FindingSummary;
  decision: Decision | null;
  onDecide: (next: Decision | null) => void;
}) {
  const { data } = useQuery(findingDetailQuery(docId, validationId, finding.finding_id));

  return (
    <div className="flex flex-col gap-3">
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-mut">
        {finding.law && <span className="rounded-xs bg-tint px-1.5 py-px font-medium text-sub">{finding.law}</span>}
        {finding.verdict === "outdated" && data?.law_effective_date && (
          <span className="font-medium text-stale">시행일 {data.law_effective_date} 기준 구버전 판정</span>
        )}
        {data && <span>판정 기준일 {data.reference_date}</span>}
      </p>
      <FindingDetailView
        docId={docId}
        validationId={validationId}
        finding={finding}
        decision={decision}
        onDecide={onDecide}
      />
    </div>
  );
}
