/*
 * 리포트 내려받기: POST /api/judgments/{job_id}/reports (contracts/5-api report_request). 응답은 파일이라 JSON 입구를 쓰지 않는다.
 * 서버 경로가 없으면 ApiRequestError(404) 가 그대로 올라가 isJudgmentApiMissing 으로 "연결 전"을 가려낸다.
 */
import { ApiRequestError, apiUrl, toRequestError } from "./client";
import { reportFileName, type ReportInclude } from "./judgment-extra";

export type ReportFormat = "html" | "xlsx" | "pdf" | "json";

/**
 * 저장하지 않은 최신 판정(snapshot_no null)으로 리포트를 만들어 내려받는다. 포함 항목은 선택(기본: 재생성 MSDS 만 뺀 나머지).
 * 파일 이름은 서버 헤더가 우선이고, 못 읽으면 예전 이름(작업번호-판정리포트.확장자)이다.
 */
export async function downloadJudgmentReport(id: string, format: ReportFormat, include?: ReportInclude) {
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
      include: include ?? { regenerated_msds: false, findings_2: true, findings_15: true, components: true, history: true },
    }),
  });
  if (!res.ok) throw await toRequestError(res);

  const url = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = reportFileName(res.headers, `${id}-판정리포트.${format}`);
  link.click();
  URL.revokeObjectURL(url);
}
