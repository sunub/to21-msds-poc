/*
 * 리포트 내려받기: POST /api/judgments/{job_id}/reports (contracts/5-api report_request). 응답은 파일이라 JSON 입구를 쓰지 않는다.
 * 서버 경로가 없으면 ApiRequestError(404) 가 그대로 올라가 isJudgmentApiMissing 으로 "연결 전"을 가려낸다.
 */
import { ApiRequestError, apiUrl, toRequestError } from "./client";

export type ReportFormat = "html" | "xlsx";

export async function downloadJudgmentReport(id: string, format: ReportFormat) {
  if (process.env.NEXT_PUBLIC_DEMO_MODE === "1") {
    const body =
      format === "html"
        ? `<!doctype html><html lang="ko"><meta charset="utf-8"><title>${id} 판정 리포트</title><body><h1>${id} 합성 데모 판정 리포트</h1><p>합성 샘플 데이터 기반 공개 데모 출력입니다.</p></body></html>`
        : "finding_id\tsection\tlabel\tverdict\nm0/F2:HH_SKIN_CORR:-\t2\t피부 부식성/자극성\t불일치\n";
    const type = format === "html" ? "text/html;charset=utf-8" : "text/tab-separated-values;charset=utf-8";
    const url = URL.createObjectURL(new Blob([body], { type }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${id}-데모판정리포트.${format}`;
    link.click();
    URL.revokeObjectURL(url);
    return;
  }
  if (process.env.NODE_ENV === "development") {
    const mock = await import("./judgment-mock");
    if (mock.mockActive()) throw new ApiRequestError(404, "unknown", "Not Found");
  }
  const res = await fetch(apiUrl(`/api/judgments/${encodeURIComponent(id)}/reports`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      format,
      snapshot_no: null,
      include: { regenerated_msds: false, findings_2: true, findings_15: true, components: true, history: true },
    }),
  });
  if (!res.ok) throw await toRequestError(res);

  const url = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = `${id}-판정리포트.${format}`;
  link.click();
  URL.revokeObjectURL(url);
}
