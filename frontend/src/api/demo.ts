/*
 * 백엔드 없이 검수 화면을 볼 때 쓰는 고정 데이터 (개발용).
 * 문서 번호가 DEMO_DOC_ID 일 때만 documents.ts 가 이 값을 돌려준다.
 */
import type { DocumentDetail } from "./schemas";

export const DEMO_DOC_ID = "demo";

export const DEMO_DETAIL: DocumentDetail = {
  id: DEMO_DOC_ID,
  filename: "KZ-A-S004 황산.pdf",
  size: 1048576,
  as_of: "2026-11-02",
  model_tag: "demo",
  created_at: "2026-11-02T10:00:00+09:00",
  updated_at: "2026-11-02T10:00:00+09:00",
  status: "done",
  stage: "done",
  error: null,
  page_count: 12,
  text_layer: "정상",
  msds_count: 1,
  stage_index: 4,
  stage_total: 4,
  counts: { total: 16, done: 16, queued: 0, running: 0, failed: 0, needs_review: 0 },
  can_retry: false,
  preprocess: { done: 12, total: 12 },
  warnings: [],
  duplicate_of: [],
  summary: null,
  sections: [],
};
