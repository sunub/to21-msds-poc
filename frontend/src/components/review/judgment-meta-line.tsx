"use client";

import { useQuery } from "@tanstack/react-query";
import { documentDetailQuery } from "@/api/documents";
import { judgmentViewQuery } from "@/api/judgments";
import { DocSummaryLine } from "./doc-summary-line";
import { useValidationId } from "./shared/use-validation-id";

/**
 * 판정 탭 위 요약 줄: 개정일 · 혼합물(성분 n) · 기준일 · 지식 provider / version (계약 6-screens 0절).
 * 개정일·혼합물은 문서 정보(document_extras)를, 없으면 판정 결과(consistency)를 쓰고, 기준일과 지식은 판정 결과에서 읽는다.
 * 판정을 아직 못 받았으면 추출 쪽 요약 줄을 대신 보인다.
 */
export function JudgmentMetaLine({ docId }: { docId: string }) {
  const validation = useValidationId(docId);
  const { data: doc } = useQuery(documentDetailQuery(docId));
  const meta = useQuery({
    ...judgmentViewQuery(docId, validation),
    select: (v) => {
      const r = v.consistency.results[0];
      return {
        asOf: v.consistency.as_of,
        knowledge: v.consistency.knowledge,
        revised: r?.msds_revision_date ?? null,
        productType: r?.product_type.value ?? null,
        components: r?.components.length ?? 0,
      };
    },
  }).data;

  if (!meta) return <DocSummaryLine docId={docId} />;
  const composition = doc?.composition ?? (meta.productType && meta.productType !== "불명확" ? { type: meta.productType, component_count: meta.components } : null);
  const parts = [
    (doc?.msds_revision_date ?? meta.revised) && `개정일 ${doc?.msds_revision_date ?? meta.revised}`,
    composition?.type && `${composition.type}(성분 ${composition.component_count})`,
    `기준일 ${meta.asOf}`,
    `지식 ${meta.knowledge.provider} / ${meta.knowledge.version}`,
  ].filter(Boolean);
  return <p className="text-sm text-mut">{parts.join(" · ")}</p>;
}
