/*
 * 저장 요청의 데모 응답 (개발용). 문서 번호가 "demo" 일 때만 save.ts 가 이 값을 돌려준다.
 * 짧은 지연 뒤 성공하고, 주소에 &fail=1 이 있으면 실패한다.
 */
import { ApiRequestError } from "./client";
import type { SaveResponse, SaveSummary } from "./save";

const DELAY_MS = 900;

export async function demoSave(summary: SaveSummary, fail: boolean): Promise<SaveResponse> {
  await new Promise((resolve) => setTimeout(resolve, DELAY_MS));
  if (fail) throw new ApiRequestError(500, "http_500", "서버가 저장을 마치지 못했습니다.");
  // 한국 시간(+09:00) ISO
  const kst = new Date(Date.now() + 9 * 60 * 60 * 1000).toISOString().slice(0, 19);
  return {
    snapshot_id: `snap_demo_${Date.now().toString(36)}`,
    saved_at: `${kst}+09:00`,
    included: { confirmed: summary.confirmed, exception: summary.exception, unreviewed: summary.unresolved },
  };
}
