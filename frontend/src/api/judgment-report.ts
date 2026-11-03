/*
 * 리포트 내려받기: POST /api/judgments/{job_id}/reports (contracts/5-api report_request). 응답은 파일이라 JSON 입구를 쓰지 않는다.
 * 서버 경로가 없으면 ApiRequestError(404) 가 그대로 올라가 isJudgmentApiMissing 으로 "연결 전"을 가려낸다.
 */
import { ApiRequestError, apiUrl, toRequestError } from "./client";

export type ReportFormat = "html" | "xlsx";

export async function downloadJudgmentReport(id: string, format: ReportFormat) {
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
