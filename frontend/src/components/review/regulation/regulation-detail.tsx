"use client";

import { useQuery } from "@tanstack/react-query";
import { findingDetailQuery } from "@/api/findings";
import type { FindingSummary } from "@/api/findings-schemas";
import { FindingDetailView } from "../hazard/finding-detail";

/**
 * 15항 판정의 상세. 2항과 같은 상세 위에 법령과 기준일을 한 줄로 붙인다.
 * 구버전이면 시행일 기준임을 밝힌다. 같은 상세 요청이라 FindingDetailView 와 캐시를 나눠 쓴다.
 */
export function RegulationDetail({
  docId,
  validationId,
  finding,
}: {
  docId: string;
  validationId: string;
  finding: FindingSummary;
}) {
  const { data } = useQuery(findingDetailQuery(docId, validationId, finding.finding_id));

  return (
    <div className="flex flex-col gap-3 [word-break:keep-all]">
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-mut">
        {finding.law && <span className="rounded-xs bg-tint px-1.5 py-px font-medium text-sub">{finding.law}</span>}
        {finding.verdict === "outdated" && (
          <span className="font-medium text-stale">시행일 <span className="whitespace-nowrap">{data?.law_effective_date ?? "-"}</span> 기준 구버전 판정</span>
        )}
        {data && <span>판정 기준일 <span className="whitespace-nowrap">{data.reference_date}</span></span>}
      </p>
      <FindingDetailView
        docId={docId}
        validationId={validationId}
        finding={finding}
      />
    </div>
  );
}
