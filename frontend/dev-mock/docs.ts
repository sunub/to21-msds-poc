/*
 * 임시 서버(judgment-server.mjs)가 추출 서버(A) 쪽 응답으로 내는 데모 문서 (개발용).
 * 문서 목록·상세에 queue_fields(대기 순번·예상 시간·사람 구간 상태)와 document_extras(제품명·코드·검수 진행)가 붙은 모양이다.
 */
/** 목록·상세 한 줄 (화면의 documentDetailSchema 모양, 이 폴더는 src 를 건드리지 않아 느슨하게 둔다) */
type DocumentDetail = Record<string, unknown> & { status: string };

export const DEMO_DETAIL: DocumentDetail = {
  id: "demo",
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
  // 실제 서버는 4단계(preprocess, sections, extract, finalize)다
  stage_index: 4,
  stage_total: 4,
  counts: { total: 16, done: 16, queued: 0, running: 0, failed: 0, needs_review: 0 },
  can_retry: false,
  queue_position: null,
  eta_seconds: null,
  review_stage: "판정으로 넘김",
  // 문서 정보 (계약 document_extras)
  product_name: "황산",
  doc_code: "KZ-A-S004",
  msds_revision_date: "2022-06-29",
  composition: { type: "혼합물", component_count: 2 },
  values_review: { state: "미검수", sections_confirmed: 0, sections_total: 9, fields_checked: 0, fields_edited: 0, fields_total: 120 },
  preprocess: { done: 12, total: 12 },
  warnings: [],
  duplicate_of: [],
  summary: null,
  sections: [],
};


/* ── 홈 목록용 데모 문서 (데모 모드에서만 목록에 섞인다) ───────────────── */

/** 검수 대기: 추출은 끝났고 사람이 아직 추출값을 확인하지 않았다 */
const DEMO_REVIEW_WAIT: DocumentDetail = {
  ...DEMO_DETAIL,
  id: "demo-review",
  filename: "KZ-A-S012 염산.pdf",
  product_name: "염산",
  doc_code: "KZ-A-S012",
  msds_revision_date: "2021-03-15",
  composition: { type: "혼합물", component_count: 3 },
  created_at: "2026-11-02T09:20:00+09:00",
  updated_at: "2026-11-02T09:40:00+09:00",
  review_stage: "검수 대기",
};

/** 대기: 앞에 한 건이 더 있어 두 번째, 약 4분 */
const DEMO_QUEUED: DocumentDetail = {
  ...DEMO_DETAIL,
  id: "demo-queue",
  filename: "KZ-A-S019 질산.pdf",
  created_at: "2026-11-02T10:05:00+09:00",
  updated_at: "2026-11-02T10:05:00+09:00",
  status: "queued",
  stage: null,
  page_count: null,
  text_layer: null,
  msds_count: null,
  stage_index: 0,
  counts: { total: 0, done: 0, queued: 0, running: 0, failed: 0, needs_review: 0 },
  // 추출 전이라 문서 정보가 아직 없다
  product_name: null,
  doc_code: null,
  msds_revision_date: null,
  composition: null,
  values_review: { state: "미검수", sections_confirmed: 0, sections_total: 0, fields_checked: 0, fields_edited: 0, fields_total: 0 },
  queue_position: 2,
  eta_seconds: 240,
  review_stage: null,
  preprocess: { done: 0, total: null },
};

/** 문서 번호별 진행 상태. demo-review·demo-queue 는 홈 목록 예시이고, 그 밖의 demo-… 는 기본 문서와 같다 */
export const demoDetail = (id: string): DocumentDetail =>
  id === DEMO_REVIEW_WAIT.id ? DEMO_REVIEW_WAIT : id === DEMO_QUEUED.id ? DEMO_QUEUED : { ...DEMO_DETAIL, id };

/** 홈 목록의 데모 문서 (새로 올린 것부터): 대기 1건, 검수 대기 1건, 판정으로 넘김 1건 */
export function demoList(status: "all" | "active" | "done" | "failed") {
  const all = [DEMO_QUEUED, DEMO_REVIEW_WAIT, DEMO_DETAIL];
  const group = {
    all,
    active: all.filter((d) => d.status === "queued" || d.status === "running"),
    done: all.filter((d) => d.status === "done"),
    failed: [] as DocumentDetail[],
  };
  return { items: group[status], counts: { all: all.length, active: group.active.length, done: group.done.length, failed: 0 } };
}
