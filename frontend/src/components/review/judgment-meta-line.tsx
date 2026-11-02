"use client";

import { useQuery } from "@tanstack/react-query";
import { documentDetailQuery } from "@/api/documents";
import { judgmentViewQuery } from "@/api/judgments";
import { DocSummaryLine } from "./doc-summary-line";
import { useValidationId } from "./shared/use-validation-id";

const stem = (filename: string) => filename.replace(/\.pdf$/i, "");

/**
 * 판정 탭 위 메타 줄: 문서명 · MSDS 개정일 · 기준일 · 지식 버전.
 * 값은 판정(judgment_view)의 consistency 에서 가져온다. 판정을 아직 못 받았으면 추출 쪽 요약 줄을 대신 보인다.
 */
export function JudgmentMetaLine({ docId }: { docId: string }) {
  const validation = useValidationId(docId);
  const { data: doc } = useQuery(documentDetailQuery(docId));
  const meta = useQuery({
    ...judgmentViewQuery(docId, validation),
    select: (v) => ({
      asOf: v.consistency.as_of,
      knowledge: v.consistency.knowledge.version,
      revised: v.consistency.results[0]?.msds_revision_date ?? null,
    }),
  }).data;

  if (!meta) return <DocSummaryLine docId={docId} />;
  const parts = [
    doc && stem(doc.filename),
    meta.revised && `MSDS 개정일 ${meta.revised}`,
    `기준일 ${meta.asOf}`,
    `지식 버전 ${meta.knowledge}`,
  ].filter(Boolean);
  return <p className="text-sm text-mut">{parts.join(" · ")}</p>;
}
