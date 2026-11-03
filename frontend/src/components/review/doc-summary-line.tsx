"use client";

import { useQuery } from "@tanstack/react-query";
import { documentDetailQuery, reviewQuery } from "@/api/documents";
import { useJudgmentGlance } from "@/hooks/use-judgment-glance";
import { summaryParts } from "@/lib/doc-glance";

/**
 * 검수 탭 위 요약 줄: 개정일 · 혼합물(성분 n) · 기준일 · 지식 provider / version (계약 6-screens 0절).
 * 개정일·혼합물은 문서 정보(document_extras)를, 아직 안 오면 추출값 검수 응답에서 읽는다.
 * 지식은 판정 보기(consistency.knowledge)에서 읽고, 판정이 없거나 서비스가 없으면 그 칸만 숨긴다.
 */
export function DocSummaryLine({ docId }: { docId: string }) {
  const { data: doc } = useQuery(documentDetailQuery(docId));
  const { data } = useQuery({ ...reviewQuery(docId), enabled: doc?.status === "done" && !doc.composition });
  const { view } = useJudgmentGlance(docId, { extractionDone: doc?.status === "done", withView: true });
  const info = data?.msds[0]?.info;
  const parts = summaryParts({
    revisionDate: doc?.msds_revision_date ?? info?.last_revision_date,
    composition: doc?.composition ? { type: doc.composition.type, count: doc.composition.component_count } : info ? { type: info.composition_type, count: info.component_count } : null,
    asOf: doc?.as_of,
    msdsCount: data?.msds.length,
    knowledge: view?.consistency.knowledge ?? null,
  });
  if (parts.length === 0) return null;
  return <p className="text-sm text-mut">{parts.join(" · ")}</p>;
}
