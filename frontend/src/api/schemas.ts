/*
 * 추출 API 계약: 백엔드 응답 모양의 단일 원본.
 *
 * - 백엔드는 backend/src/msds/api/extract_app.py (FastAPI) 이고, 응답 모양은
 *   backend/src/msds/service/progress.py 의 summary_view·view 가 정한다. 이 파일은 그 모양을 그대로 옮긴다.
 * - 타입은 손으로 쓰지 않고 스키마에서 z.infer 로 뽑는다. 스키마와 타입이 따로 놀 수 없다.
 * - 이름은 서버가 보내는 그대로(snake_case) 둔다. 화면용 이름으로 바꾸는 층을 두지 않는다.
 * - 응답은 client.ts 가 이 스키마로 parse 한 뒤에만 화면에 넘긴다 (모르는 필드는 버리고,
 *   빠졌거나 모양이 다른 필드는 그 자리에서 오류로 알린다).
 * - 나중에 FastAPI 의 OpenAPI(/openapi.json) 와 이 파일을 맞대는 계약 시험으로 바꾼다.
 *
 * 진행의 기본 단위는 항목(MSDS 건 × 추출 대상 9개 항: 1·2·3·8·9·11·12·14·15)이다. 추출은 항별로 동시에 돌아 쪽 단위 진행은 실제와 맞지 않는다.
 * 항이 걸친 쪽(pages)은 원문 이동용으로만 같이 온다.
 */
import { z } from "zod";

/* ── 공통 값 ─────────────────────────────────────────────── */

/** 작업 상태. 끝난 상태(done·failed·interrupted)에 이르면 폴링을 멈춘다. */
export const jobStatusSchema = z.enum(["queued", "running", "done", "failed", "interrupted"]);
export type JobStatus = z.infer<typeof jobStatusSchema>;

/**
 * 작업 단계: 1 전처리, 2 항목 나누기, 3 모델 추출, 4 정리·검증. 끝나면 done, 시작 전이면 null.
 * 화면의 추출·검수·저장 단계(components/shell 의 Stage)와 다른 것이라 이름을 달리한다.
 */
export const jobStageSchema = z.enum(["preprocess", "sections", "extract", "finalize", "done"]);
export type JobStage = z.infer<typeof jobStageSchema>;

/** 항 상태. 사람이 볼 항인지는 needs_review 로 따로 온다 (성공했지만 검토가 필요한 항이 있다). */
export const sectionStatusSchema = z.enum(["queued", "running", "done", "failed"]);
export type SectionStatus = z.infer<typeof sectionStatusSchema>;

export const textLayerSchema = z.enum(["정상", "글꼴깨짐", "없음", "혼합"]);
export type TextLayer = z.infer<typeof textLayerSchema>;

const count = z.int().nonnegative();
const pageNo = z.int().positive();
/** MSDS 항 번호. 추출 대상은 9개 항뿐이지만, 예전에 16항으로 돌린 문서도 읽히도록 1~16을 받는다 */
const sectionNo = z.int().min(1).max(16);
/** 한 PDF 안의 MSDS 순번 (0부터) */
const msdsIndex = z.int().nonnegative();
/** ISO-8601, 시간대 포함 (KST 라 +09:00) */
const timestamp = z.iso.datetime({ offset: true });
/** 기준일 YYYY-MM-DD */
const day = z.iso.date();

/** 끝난 상태. 폴링을 멈추는 기준. */
export const FINAL_STATUSES: readonly JobStatus[] = ["done", "failed", "interrupted"];

/**
 * 4xx·5xx 오류 응답 (FastAPI 기본 모양).
 * HTTPException 은 detail 이 문장 하나, 쿼리·경로 값이 틀린 422 는 detail 이 항목 목록이다.
 */
export const apiErrorSchema = z.object({
  detail: z.union([
    z.string(),
    z.array(z.looseObject({ loc: z.array(z.union([z.string(), z.number()])), msg: z.string() })),
  ]),
});
export type ApiError = z.infer<typeof apiErrorSchema>;

/* ── GET /api/health ────────────────────────────────────── */

export const healthResponseSchema = z.object({
  ok: z.boolean(),
  /** configs/models.yaml 태그. 시험 단계 기본값은 qwen36_35b_runpod */
  model_tag: z.string(),
});
export type HealthResponse = z.infer<typeof healthResponseSchema>;

/* ── 문서 한 줄 (목록) ─────────────────────────────────── */

export const sectionCountsSchema = z.object({
  /** MSDS 건수 × 9 (추출 대상 항). 항목을 나누기 전에는 0 */
  total: count,
  queued: count,
  running: count,
  done: count,
  failed: count,
  needs_review: count,
});
export type SectionCounts = z.infer<typeof sectionCountsSchema>;

export const documentSummarySchema = z.object({
  /** U-<날짜>-<순번> */
  id: z.string(),
  filename: z.string(),
  /** 바이트 */
  size: count,
  as_of: day.nullable(),
  model_tag: z.string(),
  created_at: timestamp,
  updated_at: timestamp,
  status: jobStatusSchema,
  stage: jobStageSchema.nullable(),
  /** 실패·멈춤 사유 */
  error: z.string().nullable(),
  /** null 이면 "쪽 수를 확인하는 중" */
  page_count: count.nullable(),
  /** 문서 전체 텍스트층 판정. 전처리 뒤에 온다 */
  text_layer: textLayerSchema.nullable(),
  /** 문서 안 MSDS 건수. 항목을 나눈 뒤에 온다 */
  msds_count: count.nullable(),
  /** 1~4. 시작 전이면 0, 끝났으면 4 */
  stage_index: z.int().min(0).max(4),
  stage_total: z.literal(4),
  /** "9 / 9항" 은 counts.done / counts.total */
  counts: sectionCountsSchema,
  /** POST /retry 로 다시 돌릴 수 있는가: 실패·멈춘 문서, 또는 끝났지만 실패한 항이 있는 문서 */
  can_retry: z.boolean(),
});
export type DocumentSummary = z.infer<typeof documentSummarySchema>;

/* ── 문서 진행 상태 (상세) ─────────────────────────────── */

export const sectionProgressSchema = z.object({
  msds_index: msdsIndex,
  section: sectionNo,
  /** 명세서의 항 제목 (예: "유해성·위험성") */
  title: z.string().nullable(),
  /** 이 항이 걸친 쪽 (문서 머리 제외) */
  pages: z.array(pageNo),
  status: sectionStatusSchema,
  /** 실패했거나, 줄 번호·코드표 검사에 문제가 남은 항 */
  needs_review: z.boolean(),
  /** 1회 재추출 결과를 썼는가 */
  reextracted: z.boolean(),
  /** 이 항에 쓴 시간 (재추출 포함). 끝나기 전에는 null */
  seconds: z.number().nonnegative().nullable(),
  /** 호출·검증 오류 앞 3개. 전체는 실행 기록에 있다 */
  errors: z.array(z.string()),
});
export type SectionProgress = z.infer<typeof sectionProgressSchema>;

/** 끝난 뒤의 요약 (section_runner.run_document 의 반환값) */
export const runSummarySchema = z.object({
  doc_id: z.string(),
  seconds: z.number().nonnegative(),
  sections_ok: count,
  sections_failed: count,
  reextracted: count,
  schema_errors: count,
});
export type RunSummary = z.infer<typeof runSummarySchema>;

export const documentDetailSchema = documentSummarySchema.extend({
  /** 1단계에서 쪽 이미지·글을 만든 쪽 수. total 이 null 이면 쪽 수를 아직 모른다 */
  preprocess: z.object({ done: count, total: count.nullable() }),
  /** 예: "항목 분할 파일 없음: 임시 분할", 텍스트층 글꼴깨짐 */
  warnings: z.array(z.string()),
  /** 같은 PDF(sha256)를 먼저 올린 문서 번호들 */
  duplicate_of: z.array(z.string()),
  summary: runSummarySchema.nullable(),
  /** 진행의 기본 단위. 항목을 나누기 전에는 빈 목록 */
  sections: z.array(sectionProgressSchema),
});
export type DocumentDetail = z.infer<typeof documentDetailSchema>;

/* ── 1. POST /api/documents ─────────────────────────────── */

/** 본문은 PDF 바이트 그대로. filename·as_of 는 쿼리로 넘긴다 (multipart 의존성을 들이지 않기 위해). 최대 50MB */
export const createDocumentParamsSchema = z.object({
  filename: z.string().min(1).max(255),
  as_of: day.optional(),
});
export type CreateDocumentParams = z.infer<typeof createDocumentParamsSchema>;

/** 서버가 받는 PDF 최대 크기 (extract_app.MAX_PDF_BYTES 와 같다). 넘으면 413 */
export const MAX_PDF_BYTES = 50 * 1024 * 1024;
/** 서버는 본문이 이 글자로 시작하지 않으면 400 으로 거절한다 */
export const PDF_MAGIC = "%PDF-";

/** 202 Accepted. 대기(queued) 상태의 진행 상태 전체 */
export const createDocumentResponseSchema = documentDetailSchema;
export type CreateDocumentResponse = z.infer<typeof createDocumentResponseSchema>;

/* ── 2. GET /api/documents?status= ──────────────────────── */

/** active 는 queued·running, failed 는 failed·interrupted */
export const documentFilterSchema = z.enum(["all", "active", "done", "failed"]);
export type DocumentFilter = z.infer<typeof documentFilterSchema>;

export const documentListResponseSchema = z.object({
  /** 새로 올린 것부터 */
  items: z.array(documentSummarySchema),
  /** 보기 전환 알약에 쓰는 개수 */
  counts: z.object({ all: count, active: count, done: count, failed: count }),
});
export type DocumentListResponse = z.infer<typeof documentListResponseSchema>;

/* ── 3. GET /api/documents/{id} (1~2초마다 폴링) ────────── */
/* documentDetailSchema. 머리글과 1.2·1.3 진행 화면이 같이 쓴다. */

/* ── 4. GET /api/documents/{id}/pages/{n}/image ─────────── */
/* image/png 바이너리라 스키마가 없다. 주소는 documents.ts 의 pageImageUrl 로 만든다. 전처리 전이면 404. */

/* ── 5. GET /api/documents/{id}/pages/{n}/lines ─────────── */

export const pageLineSchema = z.object({
  /** "p6:L12" — 모델이 근거로 적는 줄 번호와 같다. 근거 줄 강조에 그대로 쓴다 */
  id: z.string().regex(/^p\d+:L\d+$/),
  no: count,
  text: z.string(),
});
export type PageLine = z.infer<typeof pageLineSchema>;

/** 전처리 전이거나 없는 쪽이면 404 */
export const pageLinesResponseSchema = z.object({
  page: pageNo,
  lines: z.array(pageLineSchema),
});
export type PageLinesResponse = z.infer<typeof pageLinesResponseSchema>;

/* ── 6. GET /api/documents/{id}/result ──────────────────── */

export const sectionRefSchema = z.object({ msds_index: msdsIndex, section: sectionNo });
export type SectionRef = z.infer<typeof sectionRefSchema>;

/** 추출이 끝난(status done) 뒤에만 200. 그 전에는 409 */
export const resultResponseSchema = z.object({
  /**
   * TO21 v0.6 문서 (expand.to_to21 결과). 실패한 항은 빈 값.
   * 모양은 TO21 스키마(to21/v0.6, 저장소 밖 D-47)가 정하므로 여기서는 객체인지만 본다.
   */
  to21: z.record(z.string(), z.unknown()),
  /** 사람이 볼 항: 실패, 검사 문제, 펼치기 문제, 그림문자 대조 불일치 */
  needs_review: z.array(sectionRefSchema),
  warnings: z.array(z.string()),
  /** validate_to21 (TO21 스키마 검증 문장) */
  schema_errors: z.array(z.string()),
  /** TO21 검증기 V01~V23 */
  to21_validator: z.array(
    z.object({
      level: z.string(),
      rule: z.string().nullable(),
      field: z.string().nullable(),
      message: z.string(),
    }),
  ),
});
export type ResultResponse = z.infer<typeof resultResponseSchema>;

/* ── GET /api/documents/{id}/sections/{m}/{no} ─────────── */

/** 끝난 항 하나. 문서가 끝나기 전에도 받는다 (아직 안 끝난 항이면 409) */
export const sectionResultResponseSchema = sectionProgressSchema.extend({
  /** 호출·검증 오류 전부 (진행 상태의 errors 는 앞 3개) */
  errors: z.array(z.string()),
  /** 줄 번호·코드표 검사 문제 */
  check_problems: z.array(z.string()),
  /**
   * 펼치기 전 중간 형식. 실패한 항은 null.
   * 프롬프트에 묶인 모양이라 항별로 스키마를 고정하지 않고 객체인지만 본다. 검수·수정의 기준은 /result 의 to21 이다.
   */
  parsed: z.record(z.string(), z.unknown()).nullable(),
});
export type SectionResultResponse = z.infer<typeof sectionResultResponseSchema>;

/* ── GET /api/documents/{id}/regenerated ───────────────── */

/** 끝난 문서의 재생성 MSDS (끝나기 전에는 409). TO21 제공 스크립트로 만들고 모델을 부르지 않는다 */
export const regeneratedResponseSchema = z.object({
  msds: z.array(
    z.object({
      msds_index: msdsIndex,
      /** 1항 앞의 줄 (MSDS 번호, 제품명, 개정일) */
      header: z.array(z.string()),
      sections: z.array(
        z.object({
          section: sectionNo,
          title: z.string(),
          status: sectionStatusSchema,
          /** 최종 기준 (/result 의 needs_review 와 같다) */
          needs_review: z.boolean(),
          lines: z.array(
            z.object({
              /** head: 소제목·본문 줄, item: 목록 줄 */
              kind: z.enum(["head", "item"]),
              text: z.string(),
            }),
          ),
        }),
      ),
    }),
  ),
});
export type RegeneratedResponse = z.infer<typeof regeneratedResponseSchema>;

/* ── GET·PUT /api/documents/{id}/review ────────────────── */

const reviewValue = z.union([z.string(), z.number(), z.boolean()]).nullable();

export const reviewFieldSchema = z.object({
  /** MSDS 한 건 기준 경로. 예: components[0].cas_no */
  path: z.string(),
  label: z.string(),
  /** 지금 값 (고쳤으면 고친 값) */
  value: reviewValue,
  /** 고치기 전 값. 고치지 않았으면 null */
  original: reviewValue,
  state: z.enum(["unchecked", "confirmed", "edited"]),
  reviewer: z.string().nullable(),
  at: z.string().nullable(),
  /** 근거 쪽과 글. 없을 수 있다 */
  page: pageNo.nullable(),
  source_text: z.string().nullable(),
  /** TO21 검증기 문제 */
  problems: z.array(z.string()),
});
export type ReviewField = z.infer<typeof reviewFieldSchema>;

export const reviewSectionSchema = z.object({
  section: sectionNo,
  title: z.string().nullable(),
  status: sectionStatusSchema,
  pages: z.array(pageNo),
  needs_review: z.boolean(),
  problems: z.array(z.string()),
  confirmed: z.object({ reviewer: z.string(), at: z.string() }).nullable(),
  field_count: z.number().int().nonnegative(),
  checked_count: z.number().int().nonnegative(),
  groups: z.array(z.object({ path: z.string(), title: z.string(), fields: z.array(reviewFieldSchema) })),
});
export type ReviewSection = z.infer<typeof reviewSectionSchema>;

export const reviewResponseSchema = z.object({
  summary: z.object({
    sections_total: z.number().int(),
    sections_confirmed: z.number().int(),
    fields_total: z.number().int(),
    fields_checked: z.number().int(),
    fields_edited: z.number().int(),
  }),
  msds: z.array(
    z.object({
      msds_index: msdsIndex,
      info: z.object({
        product_name: z.string().nullable(),
        last_revision_date: z.string().nullable(),
        composition_type: z.string().nullable(),
        component_count: z.number().int().nonnegative(),
      }),
      sections: z.array(reviewSectionSchema),
    }),
  ),
});
export type ReviewResponse = z.infer<typeof reviewResponseSchema>;

export type FieldReviewRequest = {
  msds_index: number;
  path: string;
  action: "confirm" | "edit" | "reset";
  value?: string;
  reviewer: string;
};
export type SectionReviewRequest = { msds_index: number; section: number; confirmed: boolean; reviewer: string };

/* ── 7. POST /api/documents/{id}/retry ──────────────────── */

/** 202 Accepted. 실패·멈춘 문서만 처음부터 다시 돌린다 (그 밖의 상태면 409). 대기 상태의 진행 상태 전체 */
export const retryResponseSchema = documentDetailSchema;
export type RetryResponse = z.infer<typeof retryResponseSchema>;
