/*
 * 목록의 단계 칸·등급·버튼을 정한다: 추출 서버(A)의 문서 상태와 판정 서버(B)의 요약을 합친다 (계약 6-screens 1.1).
 * 화면과 분리한 순수 함수라 서버 없이 시험한다 (doc-stage.test.ts).
 *
 * | A status           | B 저장 | 단계 칸                                   | 버튼        |
 * | queued             | —      | 대기 n번째 (순번을 줄 때만, 아니면 대기)   | 진행 보기   |
 * | running            | —      | 추출 중 n/단계수 (응답의 stage_total)      | 진행 보기   |
 * | failed·interrupted | —      | 실패(멈춤)                                 | 진행 보기   |
 * | done               | 없음   | 검수 중 · 미검수/일부/완료 (모르면 생략)   | 이어서 하기 |
 * | done               | 있음   | 완료                                       | 열기        |
 * 판정 서버가 없거나 대답하지 않았으면(judgment 없음) 저장본이 없는 것으로 보고, 등급은 "-"다. 등급은 서버 값만 쓴다.
 * 진입 경로는 기존 검수 진입(방식 선택 2.1)과 판정 탭이다: 이어서 하기는 사람 구간(review_stage)에 따라 이어 열 곳을 고른다.
 */
export type DocLike = {
  id: string;
  status: "queued" | "running" | "done" | "failed" | "interrupted";
  stage_index: number;
  stage_total: number;
  queue_position?: number | null;
  review_stage?: "검수 대기" | "추출값 확인 중" | "판정으로 넘김" | null;
  values_review?: { state: "미검수" | "일부" | "완료" } | null;
};

export type JudgmentLike = {
  saved_snapshot: number | null;
  data_grade?: "실버" | "골드" | null;
};

export type Tone = "neutral" | "info" | "success" | "warning" | "danger";
export type DocStage = {
  label: string;
  tone: Tone;
  action: "진행 보기" | "이어서 하기" | "열기";
  /** 버튼이 가는 곳 */
  target: "extract" | "mode" | "values" | "hazard";
  /** 단계 칸을 이 라벨로 바꿔도 되는가 (추출 쪽 이상 상태는 기존 문구를 그대로 둔다) */
  normal: boolean;
};

/**
 * @param extractionFailed 완료됐지만 모든 항이 실패해 검수할 값이 없는 문서 (lib/status.ts 의 allSectionsFailed)
 */
export function documentStage(doc: DocLike, judgment?: JudgmentLike | null, extractionFailed = false): DocStage {
  switch (doc.status) {
    case "queued":
      return { label: doc.queue_position != null ? `대기 ${doc.queue_position}번째` : "대기", tone: "neutral", action: "진행 보기", target: "extract", normal: true };
    case "running":
      return { label: `추출 중 ${doc.stage_index}/${doc.stage_total}`, tone: "info", action: "진행 보기", target: "extract", normal: true };
    case "failed":
      return { label: "실패", tone: "danger", action: "진행 보기", target: "extract", normal: true };
    case "interrupted":
      return { label: "멈춤", tone: "warning", action: "진행 보기", target: "extract", normal: true };
    case "done": {
      if (extractionFailed) return { label: "실패", tone: "danger", action: "진행 보기", target: "extract", normal: false };
      if (judgment && judgment.saved_snapshot !== null) return { label: "완료", tone: "success", action: "열기", target: "hazard", normal: true };
      const target = doc.review_stage === "추출값 확인 중" ? "values" : doc.review_stage === "판정으로 넘김" ? "hazard" : "mode";
      const values = doc.values_review?.state;
      return { label: values ? `검수 중 · ${values}` : "검수 중", tone: "info", action: "이어서 하기", target, normal: true };
    }
  }
}

/** 등급 칸: 서버가 준 값만. 없으면 "-" (화면에서 추정하지 않는다) */
export const gradeLabel = (judgment?: JudgmentLike | null) => judgment?.data_grade ?? "-";

/** 판정 요약 호출은 서버가 200개까지만 받는다: 200개씩 나눈다 */
export function chunk<T>(items: T[], size = 200): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

/** 서버의 판정 요약은 작업 번호(U-날짜-순번)만 받는다. 그 밖의 번호를 섞으면 한 번에 422 가 된다 */
export const isJobId = (id: string) => /^U-\d{8}-\d{3,}$/.test(id);
