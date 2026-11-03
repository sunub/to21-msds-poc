"use client";

/*
 * 머리줄·단계 띠·요약 줄이 읽는 판정 쪽 값을 한곳에서 읽는다.
 * 판정 상태와 판정 보기는 판정 탭과 같은 쿼리 키(judgmentStatusQuery, judgmentViewQuery)라 요청이 겹치지 않는다.
 * 판정 서비스가 없거나(404) 판정이 아직 없으면 값이 없을 뿐 오류를 내지 않는다: 호출한 쪽은 그 칸을 숨긴다.
 */
import { useQuery } from "@tanstack/react-query";
import { judgmentStatusQuery, judgmentViewQuery } from "@/api/judgment";
import { judgmentSummaryQuery } from "@/api/judgment-extra";
import { unreviewedFindings } from "@/lib/save";

export function useJudgmentGlance(docId: string | null, { extractionDone, withView }: { extractionDone: boolean; withView: boolean }) {
  const id = docId ?? "";
  const on = !!docId && extractionDone;
  const status = useQuery({ ...judgmentStatusQuery(id), enabled: on });
  // 등급은 서버 요약의 data_grade 만 쓴다 (화면에서 추정하지 않는다)
  const summary = useQuery({ ...judgmentSummaryQuery(docId ? [docId] : []), enabled: on });
  const latest = status.data?.latest_version ?? null;
  const view = useQuery({ ...judgmentViewQuery(id, latest ?? 1), enabled: on && withView && latest !== null });
  return {
    status: status.data,
    grade: summary.data?.[0]?.data_grade ?? null,
    view: view.data,
    // 판정 보기가 있으면 탭·저장 화면과 같은 규칙(lib/regulation.ts)으로, 없으면 서버가 센 값
    unreviewed: view.data ? unreviewedFindings(view.data).length : (status.data?.unreviewed ?? null),
    savedSnapshot: status.data?.saved_snapshot ?? null,
  };
}
