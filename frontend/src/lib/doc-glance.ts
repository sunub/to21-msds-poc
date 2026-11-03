/*
 * 머리줄·단계 띠에 적는 문구 (계약 6-screens 0절). 화면과 분리한 순수 함수라 서버 없이 시험한다 (doc-glance.test.ts).
 * 값이 없으면 그 칸은 쓰지 않는다. 판정 서버가 없으면(judgment 없음) 추출 쪽 정보만 쓴다.
 */
export type GlanceDoc = {
  filename: string;
  page_count: number | null;
  review_stage?: "검수 대기" | "추출값 확인 중" | "판정으로 넘김" | null;
  doc_code?: string | null;
  values_review?: { state: "미검수" | "일부" | "완료" } | null;
};

export type GlanceJudgment = {
  state: "판정 없음" | "판정 중" | "판정 있음" | "판정 실패";
  unreviewed?: number | null;
  saved_snapshot?: number | null;
};

const VALUES = { 미검수: "미검수", 일부: "일부 검수", 완료: "검수 완료" } as const;

/** 판정 상태 한 칸: 판정 있음이면 미검토 수까지 */
export function judgmentLabel(j?: GlanceJudgment | null, unreviewed?: number | null): string | null {
  if (!j) return null;
  const n = unreviewed ?? j.unreviewed ?? null;
  if (j.state === "판정 있음") return n == null ? "판정 있음" : n > 0 ? `판정 미검토 ${n}건` : "판정 모두 처리";
  return j.state;
}

/**
 * 머리줄 옆 글: 파일 · 쪽 수 · 데이터 등급 · 추출값 검수 · 판정 상태. 문서 번호·제품명은 제목에 있다.
 * 문서 코드(document_extras)가 있으면 파일 이름 앞에 붙는다.
 */
export function headerNote(doc: GlanceDoc, grade: string | null, judgment: string | null) {
  const pages = doc.page_count ? `${doc.page_count}쪽` : "쪽 수 확인 중";
  return [doc.doc_code, doc.filename, pages, grade, doc.values_review && VALUES[doc.values_review.state], judgment].filter(Boolean).join(" · ");
}

/**
 * 단계 띠의 검수 칸: 추출값 확인 건너뜀 여부 + 판정 확인 중. 추출이 안 끝났으면 undefined (호출한 쪽이 안내를 둔다).
 * 추출값 쪽은 사람 구간 상태(review_stage)와 검수 진행(values_review)이 있을 때만 말한다.
 */
export function reviewNote(doc: GlanceDoc, judgment?: GlanceJudgment | null, unreviewed?: number | null) {
  const values =
    doc.review_stage === "추출값 확인 중"
      ? "추출값 확인 중"
      : doc.values_review?.state === "완료"
        ? "추출값 확인함"
        : doc.values_review?.state === "일부"
          ? "추출값 일부 확인"
          : doc.review_stage === "판정으로 넘김"
            ? "추출값 확인 건너뜀"
            : null;
  let verdict: string | null = null;
  if (judgment) {
    const n = unreviewed ?? judgment.unreviewed ?? null;
    verdict =
      judgment.state === "판정 중"
        ? "판정 중"
        : judgment.state === "판정 실패"
          ? "판정 실패"
          : judgment.state === "판정 없음"
            ? "판정 전"
            : n != null && n === 0
              ? "판정 모두 처리"
              : "판정 확인 중";
  }
  const text = [values, verdict].filter(Boolean).join(" · ");
  return text ? `· ${text}` : undefined;
}

/** 단계 띠의 저장 칸 */
export const saveNote = (judgment?: GlanceJudgment | null) => (judgment?.saved_snapshot != null ? `· 저장본 ${judgment.saved_snapshot}` : undefined);

/** 요약 줄: 개정일 · 혼합물(성분 n) · 기준일 · 지식 provider / version. 지식은 판정 보기가 있을 때만 */
export function summaryParts(input: {
  revisionDate?: string | null;
  composition?: { type: string | null; count: number } | null;
  asOf?: string | null;
  knowledge?: { provider: string; version: string } | null;
  msdsCount?: number | null;
}) {
  return [
    input.revisionDate && `개정일 ${input.revisionDate}`,
    input.composition?.type && `${input.composition.type}(성분 ${input.composition.count})`,
    input.asOf && `기준일 ${input.asOf}`,
    input.msdsCount != null && input.msdsCount > 1 && `MSDS ${input.msdsCount}건`,
    input.knowledge && `지식 ${input.knowledge.provider} / ${input.knowledge.version}`,
  ].filter(Boolean) as string[];
}
