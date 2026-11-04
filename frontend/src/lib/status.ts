/*
 * 문서 상태·단계를 화면 문구와 색으로 바꾼다 (명세 3. 상태 값).
 * 색만으로 뜻을 전하지 않도록 StatusLabel 과 함께 글자를 쓴다.
 */
import { FINAL_STATUSES, type DocumentSummary, type JobStage, type JobStatus, type SectionProgress, type ValidationSummary } from "@/api/schemas";
import type { Tone } from "@/components/ui";

const STAGE_LABEL: Record<JobStage, string> = {
  preprocess: "전처리",
  sections: "항목 나누기",
  extract: "추출 중",
  finalize: "정리 중",
  done: "완료",
};

/** 추출값 검증과 이후 정합성 판정은 서로 다른 단계다. */
export function validationLabel(validation: ValidationSummary | null | undefined): { tone: Tone; label: string; detail: string } {
  if (!validation || validation.status === "unavailable") {
    return { tone: "warning", label: "검증 미확인", detail: "추출값 검증 결과를 확인할 수 없습니다." };
  }
  const { schema_errors, validator_errors, validator_warnings, validator_exceptions, failed_sections, needs_review, unmapped_findings } = validation;
  if ([schema_errors, validator_errors, validator_warnings, validator_exceptions].some((value) => value === undefined)
      || !failed_sections || !needs_review || !unmapped_findings) {
    if (validation.status === "invalid") {
      return { tone: "danger", label: "추출 오류", detail: "검증 오류가 보고됐지만 세부 결과를 확인할 수 없습니다." };
    }
    if (validation.status === "needs_review") {
      return { tone: "warning", label: "검토 필요", detail: "검토가 필요하지만 세부 결과를 확인할 수 없습니다." };
    }
    return { tone: "warning", label: "검증 미확인", detail: "추출값 검증 결과가 완전하지 않습니다." };
  }
  const detail = `스키마 오류 ${schema_errors}건 · TO21 오류 ${validator_errors}건 · 경고 ${validator_warnings}건 · 검사 예외 ${validator_exceptions}건 · 추출 실패 ${failed_sections.length}항`;
  // invalid 는 누락·깨진 항 기록, 잘못된 MSDS 때문에도 온다. TO21 오류 때문이 아니면 추출 오류로 본다
  if (schema_errors! > 0 || validator_exceptions! > 0 || failed_sections.length > 0 || (validation.status === "invalid" && validator_errors === 0)) {
    return { tone: "danger", label: "추출 오류", detail };
  }
  if (validator_errors! > 0) {
    return { tone: "warning", label: `값 확인 ${validator_errors! + validator_warnings!}건`, detail };
  }
  if (validator_warnings! > 0 || needs_review.length > 0 || unmapped_findings.length > 0) {
    return { tone: "warning", label: "검토 필요", detail };
  }
  return { tone: "success", label: "검증 통과", detail };
}

/** 추출이 끝난 문서의 추출 상태 (방식 선택·진행 화면). 목록은 lib/document-row.ts 가 따로 정한다 */
export function statusLabel(doc: Pick<DocumentSummary, "status" | "stage" | "counts" | "validation">): { tone: Tone; label: string } {
  switch (doc.status) {
    case "queued":
      return { tone: "neutral", label: "대기" };
    case "running":
      return { tone: "info", label: doc.stage ? STAGE_LABEL[doc.stage] : "처리 중" };
    case "done":
      // 항이 실패해도 문서는 done 으로 끝난다. 모두 실패했으면 결과가 비어 있다
      if (allSectionsFailed(doc)) return { tone: "danger", label: "모든 항 실패" };
      if (doc.counts.failed > 0) return { tone: "warning", label: `완료 (실패 ${doc.counts.failed}항)` };
      if (doc.counts.total === 0 || doc.counts.done !== doc.counts.total || doc.counts.queued > 0 || doc.counts.running > 0) {
        return { tone: "warning", label: "추출 결과 미확인" };
      }
      {
        const validation = validationLabel(doc.validation);
        if (doc.counts.needs_review > 0 && validation.tone === "success") {
          return { tone: "warning", label: "검토 필요" };
        }
        return validation;
      }
    case "failed":
      return { tone: "danger", label: "실패" };
    case "interrupted":
      return { tone: "warning", label: "멈춤" };
  }
}

export function allSectionsFailed(doc: Pick<DocumentSummary, "counts">) {
  return doc.counts.total > 0 && doc.counts.failed === doc.counts.total;
}

/** 단계 표시 옆 문구 */
export function stageNote(doc: Pick<DocumentSummary, "status" | "stage" | "stage_index" | "stage_total" | "counts" | "validation">) {
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
