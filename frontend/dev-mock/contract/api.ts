/*
 * 계약 5-api.schema.json (약속 ⑤ 화면 API에 새로 생기는 모양) 과
 * 1-handoff.schema.json 의 field_status 를 zod 로 옮긴 것.
 * 계약과 한 글자도 다르지 않게 옮긴다. 계약에 없는 필드는 만들지 않는다.
 * 기준: docs/superpowers/specs/contracts/ (consistency/2 이후). 시험: pnpm test:contract (samples/*.json 을 이 zod 로 파싱)
 */
import { z } from "zod";
import * as c from "./common";
import { consistency, summary } from "./consistency";

/** 1-handoff 의 field_status: 사람의 추출값 검수 상태. 기록이 없는 칸은 미검수. B는 판정 화면 근거 옆 표시에만 쓴다 */
export const fieldStatus = z.array(
  z.strictObject({
    msds_index: c.msdsIndex,
    field: c.fieldPath,
    status: z.enum(["확인함", "수정됨"]),
  }),
);

/** [A1] GET /api/documents, GET /api/documents/{id} 응답에 더하는 칸 */
export const queueFields = z.strictObject({
  /** 대기 중이면 1부터, 아니면 null */
  queue_position: z.int().min(1).nullable(),
  /** 결과까지 예상 초. 모르면 null */
  eta_seconds: z.int().min(0).nullable(),
  /** [A2] 사람 구간 상태. 화면이 어디서 이어 열지 정한다. 판정 검수·저장 상태는 B의 judgment_status 를 본다 */
  review_stage: z.enum(["검수 대기", "추출값 확인 중", "판정으로 넘김"]).nullable(),
});

/** [A2] POST /api/documents/{id}/to-judgment — 추출값 확인을 마치고 판정으로 넘긴다 (넘김②를 만든다). 판정 검수 중 추출값 수정은 기존 PUT /review/fields 가 넘김②를 자동으로 만든다 */
export const toJudgmentRequest = z.strictObject({ reviewer: c.reviewer });

export const toJudgmentResponse = z.strictObject({
  job_id: c.jobId,
  handoff_seq: z.int().min(1),
});

/** [B2] GET /api/judgments/{job_id}/status — 판정 화면에 들어가기 전 확인 */
export const judgmentStatus = z.strictObject({
  job_id: c.jobId,
  /** 판정 없음 = 넘김 기록이 아직 없음 / 판정 중 = 최신 넘김 기록을 계산하는 중 / 판정 있음 */
  state: z.enum(["판정 없음", "판정 중", "판정 있음", "판정 실패"]),
  latest_version: z.int().min(1).nullable(),
  /** 아직 판정하지 않은 더 새 넘김 기록이 있으면 그 번호 */
  pending_handoff: z.int().nullable(),
  explanations: z.strictObject({ done: z.int().min(0), total: z.int().min(0) }),
  /** 가장 최근 저장본 번호. 저장 전이면 null */
  saved_snapshot: z.int().nullable(),
  error: z.string().nullable().optional(),
  /** 최신 판정에서 처리할 항목 수 (6-screens 0절 머리줄의 미검토 수) */
  unreviewed: z.int().min(0),
});

export const reviewState = z.strictObject({
  status: z.enum(["미검토", "불일치 확정", "예외 승인", "확인"]),
  comment: z.string().nullable(),
  reviewer: c.reviewer.nullable(),
  at: c.datetime.nullable(),
  history_count: z.int().min(0),
  /** 마지막 처리 뒤에 판정 값(verdict·msds·expected, 원문 조각 제외)이 바뀌었으면 true. 의견으로는 지워지지 않는다. 지금 판정이 처리 대상이면 미검토 수에 다시 들어간다 */
  stale: z.boolean(),
  /** 이 항목의 마지막 검토 이벤트. seen_event_id 로 돌려보내면 다른 검토자와의 충돌을 409로 알 수 있다. 기록이 없으면 항목 자체가 없다 */
  last_event_id: z.int().min(1),
});

/** finding_id → 설명. needs_explanation 인 항목만. 아직이면 status=작성 중 */
export const explanationEntry = z.union([
  z.strictObject({ status: z.literal("작성 중") }),
  z.strictObject({
    status: z.literal("완료"),
    by: z.enum(["llm", "template"]),
    checked: z.boolean(),
    summary: z.string(),
    reasons: z.array(z.string()),
    basis: z.array(z.string()),
  }),
]);

/** [B2] 판정 표·상세에 그대로 찍는 문장. 숫자·부등호 표기 규칙을 서버 한 곳에 둔다. 예: msds 구분2 (증기), expected 구분2 (분진·미스트) / msds 해당 (10% 이상), expected 해당 (≥ 10%) */
export const findingDisplay = z.strictObject({
  msds: z.string(),
  expected: z.string(),
  /** 15항 성분 (함량) 열. 예: 황산 (93~98). 제품 전체면 제품 */
  component: z.string().nullable(),
  /** 상세의 판단 근거 줄들 */
  basis_lines: z.array(z.string()),
  /** 상세의 계산 과정 줄들. 예: 상한 98%: 100 / (98 / 0.375) = 0.383 */
  calc_lines: z.array(z.string()),
  /** 원문 탭 (2항 p.4, 11항 p.9). 첫 번째가 기본으로 열린다 */
  source_pages: z.array(z.strictObject({ section: z.int().min(1).max(16), page: z.int().min(1) })),
});

/** [B2] GET /api/judgments/{job_id}?version=N (없으면 최신) — 판정 화면 2.3·2.4 가 읽는다. consistency 는 약속 ③ 그대로이고, 설명·검토는 finding_id 로 옆에 붙인다 */
export const judgmentView = z.strictObject({
  job_id: c.jobId,
  version: z.int().min(1),
  is_latest: z.boolean(),
  handoff_seq: z.int().min(1),
  judged_at: c.datetime,
  consistency,
  /** finding_id → 설명. needs_explanation 인 항목만. 아직이면 status=작성 중 */
  explanations: z.record(z.string(), explanationEntry),
  /** finding_id → 그 항목의 현재 검토 상태 (버전과 무관하게 이어진다). 기록이 없으면 미검토로 본다 */
  reviews: z.record(z.string(), reviewState),
  /** 넘김 기록의 field_status 그대로 (근거 옆 미검수/확인함/수정됨 표시) */
  field_status: fieldStatus,
  /** finding_id → 화면 표시 문장 */
  display: z.record(z.string(), findingDisplay),
});

const reviewAction = z.enum(["불일치 확정", "예외 승인", "확인", "의견", "되돌리기"]);

/**
 * [B2] POST /api/judgments/{job_id}/reviews — 판정 검토 남기기. 확인 = 일치 판정을 확인함, 되돌리기 = 미검토로.
 * 확인은 일치·참고·범위 외에만, 불일치 확정·예외 승인은 불일치·경계·근거부족·경고에만 된다 (그 밖은 422). 최신 넘김을 판정하기 전이면 409. 응답은 review_event 한 건 (201)
 */
export const reviewEventRequest = z
  .strictObject({
    finding_id: c.findingId,
    action: reviewAction,
    comment: z.string().max(2000).nullable().optional(),
    reviewer: c.reviewer,
    /** 검토자가 보고 있던 판정 버전. 더 새 버전이 있으면 409 */
    seen_version: z.int().min(1),
    /** 선택. 보고 있던 그 항목의 last_event_id. 기록이 없는 것을 봤으면 null. 칸을 보내지 않으면 충돌을 검사하지 않는다. 다르면 409 */
    seen_event_id: z.int().min(1).nullable().optional(),
  })
  .refine((v) => (v.action === "예외 승인" || v.action === "의견" ? typeof v.comment === "string" && v.comment.length >= 1 : true));

/** [B2] judge 스키마에 쌓는 검토 이벤트 한 건. 지우거나 고치지 않는다 */
export const reviewEvent = z.strictObject({
  event_id: z.int().min(1),
  job_id: c.jobId,
  finding_id: c.findingId,
  action: reviewAction,
  comment: z.string().nullable(),
  reviewer: c.reviewer,
  at: c.datetime,
  version: z.int().min(1),
  /** 검토 당시 판정 (stale 판단에 쓴다) */
  verdict_seen: c.verdict,
});

/** [B2] POST /api/judgments/{job_id}/snapshots — 저장. 미검토가 남아도 받는다. 최신 넘김을 판정하기 전이면 409 */
export const saveRequest = z.strictObject({
  reviewer: c.reviewer,
  seen_version: z.int().min(1),
  note: z.string().max(2000).nullable().optional(),
});

/** [B2] 저장본. 그 순간의 넘김 기록·판정 버전·검토 상태를 가리킨다. 다시 저장하면 새 번호 */
export const snapshot = z.strictObject({
  contract: z.literal("snapshot/1"),
  job_id: c.jobId,
  snapshot_no: z.int().min(1),
  handoff_seq: z.int().min(1),
  version: z.int().min(1),
  /** 이 번호까지의 검토 이벤트가 저장본에 포함된다. 없으면 null */
  last_review_event_id: z.int().nullable(),
  counts: z.strictObject({
    findings: z.int().min(0),
    미검토: z.int().min(0),
    "불일치 확정": z.int().min(0),
    "예외 승인": z.int().min(0),
    확인: z.int().min(0),
    /** field_status 에 없는(미검수) 추출값 칸 수 */
    "미검수 칸": z.int().min(0),
  }),
  saved_by: c.reviewer,
  saved_at: c.datetime,
  note: z.string().nullable(),
});

/** [B2] GET /api/judgments/{job_id}/versions 의 한 줄 */
export const versionListItem = z.strictObject({
  version: z.int().min(1),
  handoff_seq: z.int().min(1),
  judged_at: c.datetime,
  summary,
  /** 바로 앞 버전과 verdict·msds·expected 가 달라진 finding_id (원문 조각 제외) */
  changed_findings: z.array(c.findingId),
});

/** [A1·A2] GET /api/documents 의 items[], GET /api/documents/{id} 에 더하는 칸 (queue_fields 와 함께). 머리줄·목록의 진행·데이터 등급·검수 머리줄에 쓴다 */
export const documentExtras = z.strictObject({
  /** [A2] 추출값 msds[0].product.name (검수 수정 반영). 추출 전이면 null */
  product_name: z.string().nullable(),
  /** [A2] msds[0].meta.doc_code */
  doc_code: z.string().nullable(),
  /** [A2] msds[0].meta.last_revision_date, 없으면 first_issue_date */
  msds_revision_date: c.date.nullable(),
  /** [A2] 혼합물(성분 2) */
  composition: z
    .strictObject({
      type: z.enum(["단일물질", "혼합물"]).nullable(),
      component_count: z.int().min(0),
    })
    .nullable(),
  /** [A2] 추출값 검수 진행. state: 미검수(확인 0) / 일부 / 완료(모든 항 확인) */
  values_review: z.strictObject({
    state: z.enum(["미검수", "일부", "완료"]),
    sections_confirmed: z.int().min(0),
    sections_total: z.int().min(0),
    fields_checked: z.int().min(0),
    fields_edited: z.int().min(0),
    fields_total: z.int().min(0),
  }),
});

/** [B2] GET /api/judgments/summary?job_ids=a,b,c 의 한 줄. 목록 화면이 A의 문서 목록과 작업 번호로 합쳐 단계(검수 중/완료), 데이터 등급, 버튼(이어서 하기/열기)을 정한다 */
export const judgmentBatchItem = z.strictObject({
  job_id: c.jobId,
  state: z.enum(["판정 없음", "판정 중", "판정 있음", "판정 실패"]),
  latest_version: z.int().nullable(),
  /** 미검토이면서 처리가 필요한(불일치·경계·근거부족·경고) 판정 수 */
  unreviewed: z.int().min(0),
  saved_snapshot: z.int().nullable(),
  saved_at: c.datetime.nullable(),
  /** 실버 = 모델 추출 그대로 / 골드 = 최신 저장본이 지금의 값·판정·검토 기록을 그대로 담고 미검수 칸 0·미검토 0. 저장 뒤 바뀌면 다시 저장할 때까지 실버 */
  data_grade: z.enum(["실버", "골드"]),
});

/** 검토 이력 탭의 한 줄. A2(GET /api/documents/{id}/review/log)와 B2(GET /api/judgments/{job_id}/history)가 같은 모양으로 주고, 화면이 시각순으로 합친다 */
export const historyEntry = z.strictObject({
  at: c.datetime,
  reviewer: c.reviewer,
  /** 구분 */
  area: z.enum(["추출값", "2항", "15항", "저장"]),
  /** 대상. 추출값이면 3항 · 황산 함유량, 판정이면 finding label, 저장이면 저장본 2 */
  target: z.string(),
  /** 처리. 추출값: 확인함·수정·되돌림·항 확인·항 확인 취소 / 판정: 불일치 확정·예외 승인·확인·의견·되돌리기 / 저장: 저장 */
  action: z.string(),
  /** 처리 내용. 수정이면 93~98 → 95~98 */
  detail: z.string().nullable(),
  comment: z.string().nullable(),
  /** 화면 이동용: 추출값이면 {msds_index, path}, 판정이면 {finding_id} */
  ref: z.record(z.string(), z.unknown()).optional(),
});

/** [B2] GET /api/judgments/{job_id}/save-overview — 저장 화면 3.1~3.2 */
export const saveOverview = z.strictObject({
  job_id: c.jobId,
  version: z.int().min(1),
  handoff_seq: z.int().min(1),
  /** 판정 건수 (2항·15항 합계와 항별) */
  verdicts: z.strictObject({
    total: summary,
    by_section: z.strictObject({ "2": summary, "15": summary }),
  }),
  /** 미검토·처리 건수 */
  reviews: z.strictObject({
    미검토: z.int().min(0),
    "불일치 확정": z.int().min(0),
    "예외 승인": z.int().min(0),
    확인: z.int().min(0),
    /** 저장 전 경고(2.5)에 보일 처리 안 된 판정 */
    unreviewed_ids: z.array(c.findingId),
  }),
  /** 추출값 검수 여부와 값의 출처별 칸 수. 넘김 기록의 fields_total·field_status 로 센다 */
  values: z.strictObject({
    state: z.enum(["미검수", "일부", "완료"]),
    /** 미검수 (모델 추출 그대로) */
    model_as_is: z.int().min(0),
    confirmed: z.int().min(0),
    edited: z.int().min(0),
    fields_total: z.int().min(0),
  }),
  /** 지금까지의 저장본, 새 것부터 */
  snapshots: z.array(snapshot),
});

/**
 * [B2] POST /api/judgments/{job_id}/reports — 리포트 만들기 (화면 2.3 리포트 (HTML)·(Excel), 저장 화면 PDF로 출력). 응답은 파일.
 * snapshot_no 가 없으면 최신 판정 버전으로 만든다(저장 전 미리 보기). json 은 저장본 + 추출값 + 판정 + 검토 전체라 include 를 쓰지 않는다. 글이 빠진 PDF는 내보내지 않고 422
 */
export const reportRequest = z.strictObject({
  format: z.enum(["html", "xlsx", "pdf", "json"]),
  snapshot_no: z.int().min(1).nullable().optional(),
  include: z.strictObject({
    regenerated_msds: z.boolean(),
    findings_2: z.boolean(),
    findings_15: z.boolean(),
    components: z.boolean(),
    history: z.boolean(),
  }),
});

/** [A2] GET /api/documents/{id}/review 의 칸(reviewField)에 더하는 칸. 화면 2.2 신뢰도 낮음 · 원문 표기를 그대로 옮겼습니다, 검사 실패 · CAS 번호의 확인 숫자가 맞지 않습니다 */
export const reviewFieldExtras = z.strictObject({
  /** 추출스키마 evidence[].confidence */
  confidence: z.number().min(0).max(1).nullable(),
  /** 검사 실패 = 검증기 오류·원문 대조 실패가 이 칸에 있음 / 신뢰도 낮음 = confidence 가 기준(0.9, 작업가이드 v0.6 ⑤) 미만 또는 needs_review */
  flag: z.enum(["검사 실패", "신뢰도 낮음"]).nullable(),
  flag_text: z.string().nullable(),
});

/** [B2] 검토·저장의 409 응답. seen_version·seen_event_id 가 최신이 아니거나 pending_handoff 를 아직 판정하지 않음. 화면은 status 를 다시 읽는다 */
export const conflictResponse = z.strictObject({
  detail: z.strictObject({
    message: z.string(),
    latest_version: z.int().min(1),
    pending_handoff: z.int().nullable(),
  }),
});

/** [B2] report_request format=json 의 파일 내용. extraction 은 TO21 추출스키마 v0.6 문서 전체({doc, msds[]})라 화면이 모양을 보지 않는다 */
export const reportDocument = z.strictObject({
  contract: z.literal("report/1"),
  job_id: c.jobId,
  snapshot: snapshot.nullable(),
  version: z.int().min(1),
  extraction: z.looseObject({ doc: z.unknown(), msds: z.array(z.unknown()) }),
  field_status: fieldStatus,
  consistency,
  reviews: z.record(z.string(), reviewState),
  events: z.array(z.record(z.string(), z.unknown())),
});

export type FieldStatus = z.infer<typeof fieldStatus>;
export type QueueFields = z.infer<typeof queueFields>;
export type ToJudgmentResponse = z.infer<typeof toJudgmentResponse>;
export type JudgmentStatus = z.infer<typeof judgmentStatus>;
export type ReviewState = z.infer<typeof reviewState>;
export type ExplanationEntry = z.infer<typeof explanationEntry>;
export type FindingDisplay = z.infer<typeof findingDisplay>;
export type JudgmentView = z.infer<typeof judgmentView>;
export type ReviewEventRequest = z.infer<typeof reviewEventRequest>;
export type ReviewEvent = z.infer<typeof reviewEvent>;
export type SaveRequest = z.infer<typeof saveRequest>;
export type Snapshot = z.infer<typeof snapshot>;
export type VersionListItem = z.infer<typeof versionListItem>;
export type DocumentExtras = z.infer<typeof documentExtras>;
export type JudgmentBatchItem = z.infer<typeof judgmentBatchItem>;
export type HistoryEntry = z.infer<typeof historyEntry>;
export type SaveOverview = z.infer<typeof saveOverview>;
export type ReportRequest = z.infer<typeof reportRequest>;
export type ReviewFieldExtras = z.infer<typeof reviewFieldExtras>;
export type ConflictResponse = z.infer<typeof conflictResponse>;
