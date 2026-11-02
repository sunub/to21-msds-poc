/*
 * 저장 요청. POST /api/judgments/{job_id}/snapshots (계약 save_request → snapshot).
 * 저장 화면의 PDF 옵션(수정 이력 부록·검토자 의견 포함)은 계약의 저장 요청에 없어 서버로 보내지 않는다.
 * 검토자가 보고 있던 판정 버전(seenVersion)을 함께 보내고, 더 새 버전이 있으면 409 가 난다.
 */
import { postSnapshot } from "./judgments";

/** 저장 화면의 옵션 (PDF 에 넣을 것). 서버로 보내지 않는다 */
export type SaveOptions = { includeRevisionAppendix: boolean; includeOpinions: boolean };

export type SaveSummary = { reviewer: string; seenVersion: number };

/** 저장 결과: 저장본 번호·시각과 저장에 담긴 처리 건수 */
export type SaveResponse = {
  snapshot_no: number;
  saved_at: string;
  included: { confirmed: number; exception: number; unreviewed: number };
};

/** demo.fail 은 데모 문서에서만 듣는다 (실패 화면을 백엔드 없이 보려는 용도) */
export async function saveDocument(
  docId: string,
  _options: SaveOptions,
  summary: SaveSummary,
  demo?: { fail?: boolean },
): Promise<SaveResponse> {
  const s = await postSnapshot(docId, { reviewer: summary.reviewer, seen_version: summary.seenVersion }, demo);
  return {
    snapshot_no: s.snapshot_no,
    saved_at: s.saved_at,
    included: { confirmed: s.counts["불일치 확정"] + s.counts.확인, exception: s.counts["예외 승인"], unreviewed: s.counts.미검토 },
  };
}
