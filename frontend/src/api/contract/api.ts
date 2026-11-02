/*
 * 계약 5-api.schema.json (약속 ⑤ 화면 API에 새로 생기는 모양) 과
 * 1-handoff.schema.json 의 field_status 를 zod 로 옮긴 것.
 * 계약과 한 글자도 다르지 않게 옮긴다. 계약에 없는 필드는 만들지 않는다.
 */
import { z } from "zod";
import * as c from "./common";
import { consistency, summary } from "./consistency";

/** 1-handoff 의 field_status: 사람의 추출값 검수 상태. 기록이 없는 칸은 미검수 */
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

/** [A2] POST /api/documents/{id}/to-judgment — 추출값 확인을 마치고 판정으로 넘긴다 (넘김②를 만든다) */
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
});

export const reviewState = z.strictObject({
  status: z.enum(["미검토", "불일치 확정", "예외 승인", "확인"]),
  comment: z.string().nullable(),
  reviewer: c.reviewer.nullable(),
  at: c.datetime.nullable(),
  history_count: z.int().min(0),
  /** 마지막 검토 뒤에 판정 값(verdict·expected)이 바뀌었으면 true. 화면이 판정이 바뀌어 다시 확인 필요를 띄운다 */
  stale: z.boolean(),
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

/** [B2] GET /api/judgments/{job_id}?version=N (없으면 최신) — 판정 화면 2.3·2.4 가 읽는다 */
export const judgmentView = z.strictObject({
  job_id: c.jobId,
  version: z.int().min(1),
  is_latest: z.boolean(),
  handoff_seq: z.int().min(1),
  judged_at: c.datetime,
  consistency,
  explanations: z.record(z.string(), explanationEntry),
  /** finding_id → 그 항목의 현재 검토 상태 (버전과 무관하게 이어진다). 기록이 없으면 미검토로 본다 */
  reviews: z.record(z.string(), reviewState),
  /** 넘김 기록의 field_status 그대로 (근거 옆 미검수/확인함/수정됨 표시) */
  field_status: fieldStatus,
});

const reviewAction = z.enum(["불일치 확정", "예외 승인", "확인", "의견", "되돌리기"]);

/** [B2] POST /api/judgments/{job_id}/reviews — 판정 검토 남기기. 확인 = 일치 판정을 확인함, 되돌리기 = 미검토로 */
export const reviewEventRequest = z
  .strictObject({
    finding_id: c.findingId,
    action: reviewAction,
    comment: z.string().max(2000).nullable().optional(),
    reviewer: c.reviewer,
    /** 검토자가 보고 있던 판정 버전. 더 새 버전이 있으면 409 */
    seen_version: z.int().min(1),
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

/** [B2] POST /api/judgments/{job_id}/snapshots — 저장. 미검토가 남아도 받는다 */
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
  /** 바로 앞 버전과 verdict·expected 가 달라진 finding_id */
  changed_findings: z.array(c.findingId),
});

export type FieldStatus = z.infer<typeof fieldStatus>;
export type QueueFields = z.infer<typeof queueFields>;
export type ToJudgmentResponse = z.infer<typeof toJudgmentResponse>;
export type JudgmentStatus = z.infer<typeof judgmentStatus>;
export type ReviewState = z.infer<typeof reviewState>;
export type ExplanationEntry = z.infer<typeof explanationEntry>;
export type JudgmentView = z.infer<typeof judgmentView>;
export type ReviewEventRequest = z.infer<typeof reviewEventRequest>;
export type ReviewEvent = z.infer<typeof reviewEvent>;
export type SaveRequest = z.infer<typeof saveRequest>;
export type Snapshot = z.infer<typeof snapshot>;
export type VersionListItem = z.infer<typeof versionListItem>;
