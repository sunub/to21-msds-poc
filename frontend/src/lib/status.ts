/*
 * 문서 상태·단계를 화면 문구와 색으로 바꾼다 (명세 3. 상태 값).
 * 색만으로 뜻을 전하지 않도록 StatusLabel 과 함께 글자를 쓴다.
 */
import { FINAL_STATUSES, type DocumentSummary, type JobStage, type JobStatus, type SectionProgress } from "@/api/schemas";
import type { Tone } from "@/components/ui";

const STAGE_LABEL: Record<JobStage, string> = {
  preprocess: "전처리",
  sections: "항목 나누기",
  extract: "추출 중",
  finalize: "정리 중",
  done: "완료",
};

/** 목록의 "단계" 칸 */
export function statusLabel(doc: Pick<DocumentSummary, "status" | "stage" | "counts">): { tone: Tone; label: string } {
  switch (doc.status) {
    case "queued":
      return { tone: "neutral", label: "대기" };
    case "running":
      return { tone: "info", label: doc.stage ? STAGE_LABEL[doc.stage] : "처리 중" };
    case "done":
      // 항이 실패해도 문서는 done 으로 끝난다. 모두 실패했으면 결과가 비어 있다
      if (allSectionsFailed(doc)) return { tone: "danger", label: "모든 항 실패" };
      if (doc.counts.failed > 0) return { tone: "warning", label: `완료 (실패 ${doc.counts.failed}항)` };
      return { tone: "success", label: "완료" };
    case "failed":
      return { tone: "danger", label: "실패" };
    case "interrupted":
      return { tone: "warning", label: "멈춤" };
  }
}

/**
 * 목록의 "진행" 칸: 항을 나누기 전에는 단계("1 / 4단계"), 나눈 뒤에는 항("9 / 16항").
 * percent 는 진행 막대 길이.
 */
export function progressLabel(doc: Pick<DocumentSummary, "stage_index" | "stage_total" | "counts">) {
  const { done, total } = doc.counts;
  if (total > 0) return { text: `${done} / ${total}항`, percent: (done / total) * 100 };
  return { text: `${doc.stage_index} / ${doc.stage_total}단계`, percent: (doc.stage_index / doc.stage_total) * 100 };
}

export function allSectionsFailed(doc: Pick<DocumentSummary, "counts">) {
  return doc.counts.total > 0 && doc.counts.failed === doc.counts.total;
}

/** 단계 표시 옆 문구 */
export function stageNote(doc: Pick<DocumentSummary, "status" | "stage" | "stage_index" | "stage_total" | "counts">) {
  switch (doc.status) {
    case "queued":
      return "· 대기 중";
    case "running":
      return `· ${doc.stage_index} / ${doc.stage_total}단계 처리 중`;
    case "done":
      return `· ${statusLabel(doc).label}`;
    case "failed":
      return "· 실패";
    case "interrupted":
      return "· 멈춤";
  }
}

/** 처리 중일 때 지금 하는 일 */
export function stageMessage(doc: Pick<DocumentSummary, "status" | "stage">) {
  if (doc.status === "queued") return "앞 문서가 끝나기를 기다리고 있습니다";
  switch (doc.stage) {
    case "preprocess":
      return "쪽 이미지와 글자를 만드는 중입니다";
    case "sections":
      return "항목을 나누는 중입니다";
    case "extract":
      return "항목별로 추출하는 중입니다";
    case "finalize":
      return "결과를 정리하고 검사하는 중입니다";
    default:
      return "처리를 시작하는 중입니다";
  }
}

/**
 * 항 한 줄의 상태. 문서가 멈추면 항의 running 이 그대로 남으므로, 문서가 끝났는데 안 끝난 항은 멈춤으로 보여 준다.
 */
export function sectionLabel(section: SectionProgress, docStatus: JobStatus): { tone: Tone; label: string } {
  switch (section.status) {
    case "done":
      return section.needs_review ? { tone: "warning", label: "검토 필요" } : { tone: "success", label: "완료" };
    case "failed":
      return { tone: "danger", label: "실패" };
    case "running":
      return FINAL_STATUSES.includes(docStatus) ? { tone: "warning", label: "멈춤" } : { tone: "info", label: "추출 중" };
    case "queued":
      return FINAL_STATUSES.includes(docStatus) ? { tone: "warning", label: "멈춤" } : { tone: "neutral", label: "대기" };
  }
}

export function pagesLabel(pages: number[]) {
  if (pages.length === 0) return "-";
  const [first, last] = [pages[0], pages[pages.length - 1]];
  return first === last ? `${first}쪽` : `${first}~${last}쪽`;
}

/** 텍스트층을 입력 유형으로 (2.1). 정상이면 글자를 그대로 읽은 PDF 이고, 나머지는 잘못 읽힌 칸이 있을 수 있다 */
export function inputType(textLayer: DocumentSummary["text_layer"]): { label: string; note: string; recommendValues: boolean } {
  switch (textLayer) {
    case "정상":
      return { label: "디지털 PDF", note: "글자를 파일에서 바로 읽어 신뢰도가 높습니다.", recommendValues: false };
    case "없음":
      return { label: "스캔본 (이미지로 된 PDF)", note: "글자를 이미지에서 읽어 잘못 읽힌 칸이 있을 수 있습니다.", recommendValues: true };
    case "글꼴깨짐":
      return { label: "글자가 깨진 PDF", note: "파일의 글자가 깨져 있어 잘못 읽힌 칸이 있을 수 있습니다.", recommendValues: true };
    case "혼합":
      return { label: "글자와 이미지가 섞인 PDF", note: "이미지로 된 쪽에 잘못 읽힌 칸이 있을 수 있습니다.", recommendValues: true };
    case null:
      return { label: "판정 전", note: "입력 유형을 판정하지 못했습니다.", recommendValues: true };
  }
}
