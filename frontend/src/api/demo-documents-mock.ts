/*
 * 공개 정적 데모(NEXT_PUBLIC_DEMO_MODE=1) 전용 문서·추출·검수 API 대역.
 * 100% 가상 합성 시료(DEMO-CHEM-001~003)만 사용하며 원본 기업 PoC 데이터를 포함하지 않는다 (D-47).
 * 기본 온프레미스 빌드(NEXT_PUBLIC_DEMO_MODE 미설정)에서는 동적 import 가 트리 쉐이킹되어 번들에 포함되지 않는다.
 */
import { ApiRequestError } from "./client";
import type {
  DocumentDetail,
  DocumentFilter,
  FieldReviewRequest,
  PageBoxesResponse,
  PageLinesResponse,
  RegeneratedResponse,
  ResultResponse,
  ReviewResponse,
  ReviewStage,
  SectionProgress,
  SectionResultResponse,
  SectionReviewRequest,
  ValidationSummary,
} from "./schemas";

const SYNTHETIC_PDF_BYTES = 4_512;
const BASE_AT = "2026-11-03T08:30:00+09:00";
const UPDATED_AT = "2026-11-03T08:52:00+09:00";

const SECTION_META: { section: number; title: string; pages: number[] }[] = [
  { section: 1, title: "화학제품과 회사에 관한 정보", pages: [1] },
  { section: 2, title: "유해성·위험성", pages: [1] },
  { section: 3, title: "구성성분의 명칭 및 함유량", pages: [1] },
  { section: 8, title: "노출방지 및 개인보호구", pages: [2] },
  { section: 9, title: "물리화학적 특성", pages: [2] },
  { section: 11, title: "독성에 관한 정보", pages: [2] },
  { section: 12, title: "환경에 미치는 영향", pages: [2] },
  { section: 14, title: "운송에 필요한 정보", pages: [2] },
  { section: 15, title: "법적 규제현황", pages: [2] },
];

const PASSED_VALIDATION: ValidationSummary = {
  status: "passed",
  schema_errors: 0,
  validator_errors: 0,
  validator_warnings: 0,
  validator_exceptions: 0,
  failed_sections: [],
  needs_review: [],
  unmapped_findings: [],
};

const WARNING_VALIDATION: ValidationSummary = {
  status: "needs_review",
  schema_errors: 0,
  validator_errors: 0,
  validator_warnings: 1,
  validator_exceptions: 0,
  failed_sections: [],
  needs_review: [{ msds_index: 0, section: 2 }],
  unmapped_findings: [],
};

function makeSections(mode: "done" | "needs_review" | "running"): SectionProgress[] {
  return SECTION_META.map((m, idx) => {
    if (mode === "running") {
      const status = idx < 5 ? "done" : idx < 7 ? "running" : "queued";
      return {
        msds_index: 0,
        section: m.section,
        title: m.title,
        pages: m.pages,
        status,
        needs_review: false,
        reextracted: false,
        seconds: status === "done" ? Number((1.1 + idx * 0.2).toFixed(1)) : null,
        errors: [],
      };
    }
    const needs = mode === "needs_review" && m.section === 2;
    return {
      msds_index: 0,
      section: m.section,
      title: m.title,
      pages: m.pages,
      status: "done",
      needs_review: needs,
      reextracted: m.section === 3,
      seconds: Number((1.2 + idx * 0.15).toFixed(1)),
      errors: [],
    };
  });
}

function makeDetail(spec: {
  id: string;
  filename: string;
  productName: string;
  status: "done" | "running";
  textLayer: "정상" | "혼합";
  validationMode: "done" | "needs_review" | "running";
  updatedAt: string;
  reviewStage?: ReviewStage | null;
  warnings?: string[];
}): DocumentDetail {
  const sections = makeSections(spec.validationMode);
  const done = sections.filter((s) => s.status === "done").length;
  const running = sections.filter((s) => s.status === "running").length;
  const queued = sections.filter((s) => s.status === "queued").length;
  const needsReview = sections.filter((s) => s.needs_review).length;
  const validation =
    spec.validationMode === "running"
      ? null
      : spec.validationMode === "needs_review"
        ? WARNING_VALIDATION
        : PASSED_VALIDATION;

  return {
    id: spec.id,
    filename: spec.filename,
    size: SYNTHETIC_PDF_BYTES,
    as_of: "2026-11-03",
    model_tag: "synthetic-demo-v1",
    created_at: BASE_AT,
    updated_at: spec.updatedAt,
    status: spec.status,
    stage: spec.status === "done" ? "done" : "extract",
    error: null,
    page_count: 2,
    text_layer: spec.textLayer,
    msds_count: 1,
    stage_index: spec.status === "done" ? 4 : 3,
    stage_total: 4,
    counts: {
      total: sections.length,
      queued,
      running,
      done,
      failed: 0,
      needs_review: needsReview,
    },
    can_retry: false,
    validation,
    queue_position: null,
    eta_seconds: spec.status === "running" ? 18 : null,
    review_stage: spec.status === "done" ? (spec.reviewStage ?? "판정으로 넘김") : null,
    document_extras:
      spec.status === "done"
        ? {
            product_name: spec.productName,
            doc_code: spec.id,
            msds_revision_date: "2022-01-01",
            composition: { type: "혼합물", component_count: 2 },
            values_review: {
              state: "일부",
              sections_confirmed: 2,
              sections_total: 4,
              fields_checked: 8,
              fields_edited: 1,
              fields_total: 11,
            },
          }
        : null,
    preprocess: { done: 2, total: 2 },
    warnings: spec.warnings ?? [],
    duplicate_of: [],
    summary:
      spec.status === "done"
        ? {
            doc_id: spec.id,
            seconds: 14.2,
            sections_ok: sections.length,
            sections_failed: 0,
            reextracted: 1,
            schema_errors: 0,
            validation,
          }
        : null,
    sections,
  };
}

const docs = new Map<string, DocumentDetail>([
  [
    "DEMO-CHEM-001",
    makeDetail({
      id: "DEMO-CHEM-001",
      filename: "DEMO-CHEM-001_합성데모시료A.pdf",
      productName: "합성 데모 시료 A",
      status: "done",
      textLayer: "정상",
      validationMode: "needs_review",
      reviewStage: "판정으로 넘김",
      updatedAt: UPDATED_AT,
    }),
  ],
  [
    "DEMO-CHEM-002",
    makeDetail({
      id: "DEMO-CHEM-002",
      filename: "DEMO-CHEM-002_합성데모시료B.pdf",
      productName: "합성 데모 시료 B",
      status: "done",
      textLayer: "정상",
      validationMode: "done",
      reviewStage: "검수 대기",
      updatedAt: "2026-11-03T08:15:00+09:00",
    }),
  ],
  [
    "DEMO-CHEM-003",
    makeDetail({
      id: "DEMO-CHEM-003",
      filename: "DEMO-CHEM-003_합성추출진행C.pdf",
      productName: "합성 데모 시료 C",
      status: "running",
      textLayer: "혼합",
      validationMode: "running",
      updatedAt: "2026-11-03T08:55:00+09:00",
      warnings: ["일부 쪽이 이미지 기반 텍스트로 감지되어 추출값 확인을 권장합니다."],
    }),
  ],
]);

function makeInitialReview(productName: string): ReviewResponse {
  const sections: ReviewResponse["msds"][number]["sections"] = [
    {
      section: 1,
      title: "화학제품과 회사에 관한 정보",
      status: "done",
      pages: [1],
      needs_review: false,
      problems: [],
      confirmed: { reviewer: "가상 검토자", at: "2026-11-03T08:36:00+09:00" },
      field_count: 2,
      checked_count: 2,
      groups: [
        {
          path: "product",
          title: "제품 정보",
          fields: [
            {
              path: "product.name",
              label: "제품명",
              value: productName,
              display: null,
              original: null,
              state: "confirmed",
              reviewer: "가상 검토자",
              at: "2026-11-03T08:35:00+09:00",
              page: 1,
              source_text: "Product Name: Demo Sample A",
              problems: [],
            },
            {
              path: "product.revision_date",
              label: "최종 개정일",
              value: "2022-01-01",
              display: null,
              original: null,
              state: "confirmed",
              reviewer: "가상 검토자",
              at: "2026-11-03T08:35:00+09:00",
              page: 1,
              source_text: "Revision Date: 2022-01-01",
              problems: [],
            },
          ],
        },
      ],
    },
    {
      section: 2,
      title: "유해성·위험성",
      status: "done",
      pages: [1],
      needs_review: true,
      problems: ["신호어(경고)가 피부 부식성 구분과 어긋나는지 2항 판정에서 확인 필요"],
      confirmed: null,
      field_count: 3,
      checked_count: 1,
      groups: [
        {
          path: "hazard",
          title: "GHS 분류 및 표시 요소",
          fields: [
            {
              path: "hazard.classes[0].raw",
              label: "피부 부식성/자극성",
              value: "구분 2",
              display: null,
              original: null,
              state: "unchecked",
              reviewer: null,
              at: null,
              page: 1,
              source_text: "피부 부식성/자극성 : 구분 2",
              problems: [],
            },
            {
              path: "hazard.classes[1].raw",
              label: "급성 독성(흡입)",
              value: "구분 2 (증기)",
              display: null,
              original: null,
              state: "unchecked",
              reviewer: null,
              at: null,
              page: 1,
              source_text: "급성 독성(흡입: 증기) : 구분 2",
              problems: [],
            },
            {
              path: "hazard.signal_word",
              label: "신호어",
              value: "경고",
              display: null,
              original: null,
              state: "confirmed",
              reviewer: "가상 검토자",
              at: "2026-11-03T08:40:00+09:00",
              page: 1,
              source_text: "신호어 : 경고",
              problems: [],
            },
          ],
        },
      ],
    },
    {
      section: 3,
      title: "구성성분의 명칭 및 함유량",
      status: "done",
      pages: [1],
      needs_review: false,
      problems: [],
      confirmed: null,
      field_count: 4,
      checked_count: 3,
      groups: [
        {
          path: "components[0]",
          title: "구성성분 1",
          fields: [
            {
              path: "components[0].name",
              label: "물질명",
              value: "가상물질 A",
              display: null,
              original: null,
              state: "confirmed",
              reviewer: "가상 검토자",
              at: "2026-11-03T08:45:00+09:00",
              page: 1,
              source_text: "1. Demo Substance A | CAS: 0000-00-1 | Content: 93~98%",
              problems: [],
            },
            {
              path: "components[0].cas_no",
              label: "CAS 번호",
              value: "0000-00-1",
              display: null,
              original: null,
              state: "confirmed",
              reviewer: "가상 검토자",
              at: "2026-11-03T08:45:00+09:00",
              page: 1,
              source_text: "CAS: 0000-00-1",
              problems: [],
            },
            {
              path: "components[0].content.raw",
              label: "함유량(%)",
              value: "95~98",
              display: null,
              original: "93~98",
              state: "edited",
              reviewer: "가상 검토자",
              at: "2026-11-03T08:52:00+09:00",
              page: 1,
              source_text: "Content: 93~98%",
              problems: [],
            },
          ],
        },
        {
          path: "components[1]",
          title: "구성성분 2",
          fields: [
            {
              path: "components[1].cas_no",
              label: "가상물질 B CAS",
              value: "0000-00-2",
              display: null,
              original: null,
              state: "unchecked",
              reviewer: null,
              at: null,
              page: 1,
              source_text: "2. Demo Substance B | CAS: 0000-00-2 | Content: 2~7%",
              problems: [],
            },
          ],
        },
      ],
    },
    {
      section: 15,
      title: "법적 규제현황",
      status: "done",
      pages: [2],
      needs_review: false,
      problems: [],
      confirmed: { reviewer: "가상 검토자", at: "2026-11-03T08:41:00+09:00" },
      field_count: 2,
      checked_count: 2,
      groups: [
        {
          path: "regulations",
          title: "국내 법령 기재",
          fields: [
            {
              path: "regulations[0].applicable",
              label: "산안법 관리대상유해물질",
              value: "해당 (1% 이상)",
              display: null,
              original: null,
              state: "confirmed",
              reviewer: "가상 검토자",
              at: "2026-11-03T08:41:00+09:00",
              page: 2,
              source_text: "관리대상유해물질 : 해당 (1% 이상)",
              problems: [],
            },
            {
              path: "regulations[1].applicable",
              label: "화평법 등록대상기존화학물질",
              value: "비해당",
              display: null,
              original: null,
              state: "confirmed",
              reviewer: "가상 검토자",
              at: "2026-11-03T08:41:00+09:00",
              page: 2,
              source_text: "화학물질의 등록 및 평가 등에 관한 법률 : 비해당",
              problems: [],
            },
          ],
        },
      ],
    },
  ];
  return recountReview({
    summary: { sections_total: 0, sections_confirmed: 0, fields_total: 0, fields_checked: 0, fields_edited: 0 },
    msds: [
      {
        msds_index: 0,
        info: {
          product_name: productName,
          last_revision_date: "2022-01-01",
          composition_type: "혼합물",
          component_count: 2,
        },
        sections,
      },
    ],
  });
}

function recountReview(data: ReviewResponse): ReviewResponse {
  let sectionsTotal = 0;
  let sectionsConfirmed = 0;
  let fieldsTotal = 0;
  let fieldsChecked = 0;
  let fieldsEdited = 0;
  for (const m of data.msds) {
    for (const s of m.sections) {
      sectionsTotal += 1;
      if (s.confirmed) sectionsConfirmed += 1;
      let count = 0;
      let checked = 0;
      for (const g of s.groups) {
        for (const f of g.fields) {
          count += 1;
          fieldsTotal += 1;
          if (f.state !== "unchecked") {
            checked += 1;
            fieldsChecked += 1;
          }
          if (f.state === "edited") fieldsEdited += 1;
        }
      }
      s.field_count = count;
      s.checked_count = checked;
    }
  }
  data.summary = {
    sections_total: sectionsTotal,
    sections_confirmed: sectionsConfirmed,
    fields_total: fieldsTotal,
    fields_checked: fieldsChecked,
    fields_edited: fieldsEdited,
  };
  return structuredClone(data);
}

const reviewStore = new Map<string, ReviewResponse>();

function getReview(id: string): ReviewResponse {
  let existing = reviewStore.get(id);
  if (!existing) {
    const label = id === "DEMO-CHEM-002" ? "합성 데모 시료 B" : "합성 데모 시료 A";
    existing = makeInitialReview(label);
    reviewStore.set(id, existing);
  }
  return existing;
}

function syncDocExtras(id: string, review: ReviewResponse) {
  const doc = docs.get(id);
  if (!doc || !doc.document_extras) return;
  const s = review.summary;
  doc.document_extras = {
    ...doc.document_extras,
    values_review: {
      state: s.sections_confirmed >= s.sections_total ? "완료" : s.fields_checked > 0 ? "일부" : "미검수",
      sections_confirmed: s.sections_confirmed,
      sections_total: s.sections_total,
      fields_checked: s.fields_checked,
      fields_edited: s.fields_edited,
      fields_total: s.fields_total,
    },
  };
}

function getOrFallbackDoc(id: string): DocumentDetail {
  const found = docs.get(id);
  if (found) return found;
  if (id.startsWith("DEMO-")) {
    const generated = makeDetail({
      id,
      filename: `${id}_합성데모시료.pdf`,
      productName: `합성 데모 시료 (${id})`,
      status: "done",
      textLayer: "정상",
      validationMode: "needs_review",
      updatedAt: UPDATED_AT,
    });
    docs.set(id, generated);
    return generated;
  }
  throw new ApiRequestError(404, "http_404", `${id} 데모 문서를 찾을 수 없습니다.`);
}

const PAGE_LINES: Record<number, PageLinesResponse> = {
  1: {
    page: 1,
    lines: [
      { id: "p1:L1", no: 1, text: "MATERIAL SAFETY DATA SHEET (SYNTHETIC DEMO SAMPLE)" },
      { id: "p1:L2", no: 2, text: "1. 화학제품과 회사에 관한 정보" },
      { id: "p1:L3", no: 3, text: "제품명 : 합성 데모 시료 A (DEMO-CHEM-001)" },
      { id: "p1:L4", no: 4, text: "제조자 : 가상 데모 연구소 | 개정일 : 2022-01-01" },
      { id: "p1:L5", no: 5, text: "2. 유해성·위험성" },
      { id: "p1:L6", no: 6, text: "피부 부식성/자극성 : 구분 2" },
      { id: "p1:L7", no: 7, text: "급성 독성(흡입: 증기) : 구분 2" },
      { id: "p1:L8", no: 8, text: "신호어 : 경고" },
      { id: "p1:L9", no: 9, text: "만성 수생환경 유해성 : 구분 3 | 금속부식성 : 구분 1" },
      { id: "p1:L10", no: 10, text: "3. 구성성분의 명칭 및 함유량" },
      { id: "p1:L11", no: 11, text: "1. 가상물질 A (Demo Substance A) | CAS 0000-00-1 | 93~98%" },
      { id: "p1:L12", no: 12, text: "2. 가상물질 B (Demo Substance B) | CAS 0000-00-2 | 2~7%" },
    ],
  },
  2: {
    page: 2,
    lines: [
      { id: "p2:L1", no: 1, text: "9. 물리화학적 특성" },
      { id: "p2:L2", no: 2, text: "외관 : 무색 액체 (합성 데모 시료) | 인화점 : 자료없음" },
      { id: "p2:L3", no: 3, text: "11. 독성에 관한 정보" },
      { id: "p2:L4", no: 4, text: "가상물질 A (0000-00-1) 흡입 독성(분진·미스트) LC50 : 0.375 mg/L" },
      { id: "p2:L5", no: 5, text: "가상물질 B (0000-00-2) : 무독성 참고 성분" },
      { id: "p2:L6", no: 6, text: "12. 환경에 미치는 영향" },
      { id: "p2:L7", no: 7, text: "수생환경 분류 기준정보 없음 (합성 샘플)" },
      { id: "p2:L8", no: 8, text: "15. 법적 규제현황" },
      { id: "p2:L9", no: 9, text: "관리대상유해물질 : 해당 (1% 이상)" },
      { id: "p2:L10", no: 10, text: "화학물질의 등록 및 평가 등에 관한 법률 : 비해당" },
      { id: "p2:L11", no: 11, text: "위험물안전관리법 : 자료없음" },
    ],
  },
};

function makeRegenerated(doc: DocumentDetail): RegeneratedResponse {
  return {
    msds: [
      {
        msds_index: 0,
        header: [
          `${doc.id} · ${doc.document_extras?.product_name ?? "합성 데모 시료 A"}`,
          `원본 파일: ${doc.filename} · 개정일 2022-01-01 · 기준일 ${doc.as_of ?? "2026-11-03"}`,
        ],
        sections: [
          {
            section: 1,
            title: "화학제품과 회사에 관한 정보",
            status: "done",
            needs_review: false,
            lines: [
              { kind: "head", text: `제품명: ${doc.document_extras?.product_name ?? "합성 데모 시료 A"} (${doc.id})` },
              { kind: "item", text: "제조·공급자: 가상 데모 연구소 (공개 데모용 합성 데이터)" },
            ],
          },
          {
            section: 2,
            title: "유해성·위험성",
            status: "done",
            needs_review: true,
            lines: [
              { kind: "head", text: "유해성·위험성 분류" },
              { kind: "item", text: "피부 부식성/자극성 : 구분 2" },
              { kind: "item", text: "급성 독성(흡입: 증기) : 구분 2" },
              { kind: "item", text: "신호어 : 경고" },
            ],
          },
          {
            section: 3,
            title: "구성성분의 명칭 및 함유량",
            status: "done",
            needs_review: false,
            lines: [
              { kind: "head", text: "혼합물 (구성성분 2종)" },
              { kind: "item", text: "가상물질 A · CAS 0000-00-1 · 93~98%" },
              { kind: "item", text: "가상물질 B · CAS 0000-00-2 · 2~7%" },
            ],
          },
          {
            section: 15,
            title: "법적 규제현황",
            status: "done",
            needs_review: false,
            lines: [
              { kind: "head", text: "산업안전보건법 · 화학물질관리법 · 화평법" },
              { kind: "item", text: "관리대상유해물질 : 해당 (1% 이상)" },
              { kind: "item", text: "화학물질의 등록 및 평가 등에 관한 법률 : 비해당" },
            ],
          },
        ],
      },
    ],
  };
}

function makeSectionResult(doc: DocumentDetail, sectionNo: number): SectionResultResponse {
  const sec = doc.sections.find((s) => s.section === sectionNo) ?? doc.sections[0];
  const parsedBySection: Record<number, Record<string, unknown>> = {
    1: { product_name: doc.document_extras?.product_name ?? "합성 데모 시료 A", revision_date: "2022-01-01", supplier: "가상 데모 연구소" },
    2: { signal_word: "경고", skin_corrosion: "구분 2", acute_inhalation: "구분 2 (증기)" },
    3: {
      composition_type: "혼합물",
      components: [
        { name: "가상물질 A", cas_no: "0000-00-1", content: "93~98%" },
        { name: "가상물질 B", cas_no: "0000-00-2", content: "2~7%" },
      ],
    },
    9: { appearance: "무색 액체", flash_point: null, ph: "1.8" },
    11: { inhalation_lc50_mg_l: 0.375, route_form: "분진·미스트" },
    15: { osh_managed: "해당 (1% 이상)", kreach_existing: "비해당", dangerous_goods: "자료없음" },
  };
  return {
    ...sec,
    errors: [],
    check_problems: sec.needs_review ? ["2항 신호어와 분류 간 정합성 확인 권장"] : [],
    parsed: parsedBySection[sec.section] ?? { note: "합성 데모 추출값" },
  };
}

function filterDocs(filter: DocumentFilter) {
  const all = [...docs.values()];
  const active = all.filter((d) => d.status === "queued" || d.status === "running");
  const done = all.filter((d) => d.status === "done");
  const failed = all.filter((d) => d.status === "failed" || d.status === "interrupted");
  const map: Record<DocumentFilter, DocumentDetail[]> = { all, active, done, failed };
  return {
    items: map[filter] ?? all,
    counts: { all: all.length, active: active.length, done: done.length, failed: failed.length },
  };
}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
let uploadSeq = 4;

export async function demoDocumentResponse(
  path: string,
  init?: RequestInit & { query?: Record<string, string> },
): Promise<unknown> {
  await wait(80);
  const method = (init?.method ?? "GET").toUpperCase();

  if (path === "/api/health") {
    return { ok: true, model_tag: "synthetic-demo-v1" };
  }

  if (path === "/api/documents" && method === "GET") {
    const status = (init?.query?.status ?? "all") as DocumentFilter;
    return filterDocs(status);
  }

  if (path === "/api/documents" && method === "POST") {
    const id = `DEMO-CHEM-${String(uploadSeq++).padStart(3, "0")}`;
    const filename = init?.query?.filename ?? `${id}_합성업로드샘플.pdf`;
    const created = makeDetail({
      id,
      filename,
      productName: `합성 업로드 시료 (${id})`,
      status: "done",
      textLayer: "정상",
      validationMode: "needs_review",
      reviewStage: "검수 대기",
      updatedAt: new Date().toISOString().replace("Z", "+09:00"),
    });
    docs.set(id, created);
    return created;
  }

  const parts = path.split("?")[0].split("/").filter(Boolean);
  // /api/documents/{id}/...
  if (parts[0] === "api" && parts[1] === "documents" && parts[2]) {
    const id = decodeURIComponent(parts[2]);
    const rest = parts.slice(3).join("/");

    if (!rest) return getOrFallbackDoc(id);

    if (rest === "retry" && method === "POST") {
      const doc = getOrFallbackDoc(id);
      return doc;
    }

    if (rest === "result") {
      const doc = getOrFallbackDoc(id);
      const res: ResultResponse = {
        to21: { synthetic_demo: true, doc_id: doc.id },
        needs_review: doc.validation?.needs_review ?? [],
        warnings: doc.warnings,
        validation: doc.validation ?? PASSED_VALIDATION,
        schema_errors: [],
        to21_validator: [],
      };
      return res;
    }

    if (rest === "regenerated") {
      return makeRegenerated(getOrFallbackDoc(id));
    }

    if (rest === "review" && method === "GET") {
      getOrFallbackDoc(id);
      return structuredClone(getReview(id));
    }

    if (rest === "review/fields" && method === "PUT") {
      const body = JSON.parse(String(init?.body)) as FieldReviewRequest;
      const review = getReview(id);
      const targetMsds = review.msds.find((m) => m.msds_index === body.msds_index) ?? review.msds[0];
      for (const s of targetMsds.sections) {
        for (const g of s.groups) {
          for (const f of g.fields) {
            if (f.path !== body.path) continue;
            const now = new Date().toISOString();
            if (body.action === "confirm") {
              f.state = "confirmed";
              f.reviewer = body.reviewer;
              f.at = now;
            } else if (body.action === "edit") {
              if (f.original === null) f.original = f.value;
              f.value = body.value?.trim() ? body.value : null;
              f.state = "edited";
              f.reviewer = body.reviewer;
              f.at = now;
            } else if (body.action === "reset") {
              if (f.original !== null) {
                f.value = f.original;
                f.original = null;
              }
              f.state = "unchecked";
              f.reviewer = null;
              f.at = null;
            }
          }
        }
      }
      const next = recountReview(review);
      syncDocExtras(id, next);
      return next;
    }

    if (rest === "review/sections" && method === "PUT") {
      const body = JSON.parse(String(init?.body)) as SectionReviewRequest;
      const review = getReview(id);
      const targetMsds = review.msds.find((m) => m.msds_index === body.msds_index) ?? review.msds[0];
      const sec = targetMsds.sections.find((s) => s.section === body.section);
      if (sec) {
        sec.confirmed = body.confirmed ? { reviewer: body.reviewer, at: new Date().toISOString() } : null;
      }
      const next = recountReview(review);
      syncDocExtras(id, next);
      return next;
    }

    const linesMatch = /^pages\/(\d+)\/lines$/.exec(rest);
    if (linesMatch) {
      const page = Number(linesMatch[1]);
      return PAGE_LINES[page] ?? PAGE_LINES[1];
    }

    const boxesMatch = /^pages\/(\d+)\/boxes$/.exec(rest);
    if (boxesMatch) {
      const page = Number(boxesMatch[1]);
      const empty: PageBoxesResponse = { page, width: null, height: null, items: [] };
      return empty;
    }

    const secMatch = /^sections\/(\d+)\/(\d+)$/.exec(rest);
    if (secMatch) {
      return makeSectionResult(getOrFallbackDoc(id), Number(secMatch[2]));
    }
  }

  throw new ApiRequestError(404, "http_404", `알 수 없는 데모 경로입니다: ${path}`);
}
