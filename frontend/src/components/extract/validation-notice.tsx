import type { JobStatus, SectionCounts, ValidationSummary } from "@/api/schemas";
import { StatusLabel } from "@/components/ui";
import { validationLabel } from "@/lib/status";

/** 추출 완료와 추출값 검증 통과를 구분한다. */
export function ValidationNotice({ status, counts, validation }: {
  status: JobStatus;
  counts: SectionCounts;
  validation?: ValidationSummary | null;
}) {
  if (status !== "done") return null;
  const incomplete = counts.total === 0 || counts.done !== counts.total || counts.queued > 0 || counts.running > 0 || counts.failed > 0;
  const base = validationLabel(validation);
  const info = incomplete
    ? { tone: "warning" as const, label: "추출 결과 미확인", detail: "완료되지 않은 항목이 있어 추출값 검증 통과로 표시할 수 없습니다." }
    : counts.needs_review > 0 && base.tone === "success"
      ? { tone: "warning" as const, label: "추출값 검토 필요", detail: `검토가 필요한 항목이 ${counts.needs_review}개 있습니다.` }
      : base;
  // validationLabel 의 건수 요약(스키마 오류 N건 · …)은 여기서 보이지 않게 한다. 이 파일에서 정한 문구는 그대로 둔다
  const showDetail = info !== base || !/^(추출 오류|값 확인 \d+건|검토 필요|검증 통과)$/.test(base.label);
  return (
    <div className="flex flex-col gap-1.5 rounded-md border border-line bg-white px-5 py-3.5 text-sm print:hidden"
         role={info.tone === "danger" ? "alert" : "status"}>
      <StatusLabel tone={info.tone}>{info.label}</StatusLabel>
      {showDetail && <p className="text-sub">{info.detail}</p>}
      <p className="text-mut">이 검사는 추출값의 형식과 내용을 확인하며, HTODB 기준 정합성 판정과는 별도입니다.</p>
    </div>
  );
}
