"use client";

import { useQuery } from "@tanstack/react-query";
import { documentDetailQuery, reviewQuery } from "@/api/documents";

/** 검수 탭 위 요약 줄: 개정일, 혼합물·단일물질, 기준일. 끝난 문서만 값이 있다 */
export function DocSummaryLine({ docId }: { docId: string }) {
  const { data: doc } = useQuery(documentDetailQuery(docId));
  const { data } = useQuery({ ...reviewQuery(docId), enabled: doc?.status === "done" });
  const info = data?.msds[0]?.info;
  const parts = [
    info?.last_revision_date && `개정일 ${info.last_revision_date}`,
    info?.composition_type && `${info.composition_type}(성분 ${info.component_count})`,
    doc?.as_of && `기준일 ${doc.as_of}`,
    data && data.msds.length > 1 && `MSDS ${data.msds.length}건`,
  ].filter(Boolean);
  if (parts.length === 0) return null;
  return <p className="text-sm text-mut">{parts.join(" · ")}</p>;
}
