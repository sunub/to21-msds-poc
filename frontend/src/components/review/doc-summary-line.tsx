"use client";

import { useQuery } from "@tanstack/react-query";
import { documentDetailQuery, reviewQuery } from "@/api/documents";

/** 검수 탭 위 요약 줄: 개정일, 혼합물·단일물질, 기준일. 끝난 문서만 값이 있다 */
export function DocSummaryLine({ docId }: { docId: string }) {
  const { data: doc } = useQuery(documentDetailQuery(docId));
  // 서버가 문서 정보(document_extras)를 주면 그것을 쓰고, 아직 안 주면 추출값 검수 응답에서 읽는다
  const { data } = useQuery({ ...reviewQuery(docId), enabled: doc?.status === "done" && !doc.values_review, retry: false });
  const info = data?.msds[0]?.info;
  const revision = doc?.msds_revision_date ?? info?.last_revision_date;
  const composition = doc?.composition ? { type: doc.composition.type, count: doc.composition.component_count } : info ? { type: info.composition_type, count: info.component_count } : null;
  const parts = [
    revision && `개정일 ${revision}`,
    composition?.type && `${composition.type}(성분 ${composition.count})`,
    doc?.as_of && `기준일 ${doc.as_of}`,
    data && data.msds.length > 1 && `MSDS ${data.msds.length}건`,
  ].filter(Boolean);
  if (parts.length === 0) return null;
  return <p className="text-sm text-mut">{parts.join(" · ")}</p>;
}
