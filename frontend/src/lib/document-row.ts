/*
 * 목록(1.1) 한 줄: 단계·진행·다음 행동 (contracts/6-screens.md 1.1).
 * A 의 문서 한 줄과 B 의 판정 요약(judgment_batch_item)을 작업 번호로 합친 값에서 정한다.
 *
 * - 단계 칸은 작업 흐름(추출 → 검수 → 저장)의 위치다. 추출 직후 자동 검사 결과는 단계가 아니라 보조 문구(note)로 둔다.
 *   자동 검사는 모델이 뽑은 원래 값에 대한 것이라 사람이 검수해도 바뀌지 않는다. 문구는 lib/status.ts validationLabel 을 그대로 쓴다.
 * - 판정 쪽 요약이 없으면(판정 API 없음·실패) 저장했다고 단정하지 않는다.
 */
import type { JudgmentBatchItem } from "@/api/judgment";
import type { DocumentSummary, JobStage } from "@/api/schemas";
import type { Tone } from "@/components/ui";
import { routes } from "./routes.ts";

/** lib/status.ts validationLabel 의 결과. status.ts 는 "@/" 값을 불러 node 시험에서 읽을 수 없어 부르는 쪽이 넘긴다 */
export type CheckLabel = { tone: Tone; label: string; detail: string };

type Label = { tone: Tone; label: string };

export type RowAction =
  | { kind: "link"; label: string; href: string; primary: boolean }
  | { kind: "retry" };

export type DocumentRowView = {
  /** 제품명을 알면 제품명, 모르면 파일명 */
  title: string;
  subtitle: string;
  stage: Label;
  /** 단계 아래 작은 글. title 은 마우스를 올렸을 때 보이는 설명 */
  note: { tone: Tone; text: string; title: string } | null;
  progress: { text: string; percent: number; detail: string | null };
  action: RowAction;
};

const STAGE_LABEL: Record<JobStage, string> = {
  preprocess: "전처리",
  sections: "항목 나누기",
  extract: "추출 중",
  finalize: "정리 중",
  done: "완료",
};

const CHECK_TITLE = "추출 직후 모델이 뽑은 값을 자동으로 검사한 결과입니다. 사람이 검수해도 이 결과는 바뀌지 않습니다.";

export function documentRow(doc: DocumentSummary, judgment: JudgmentBatchItem | undefined, check: CheckLabel): DocumentRowView {
  return { ...names(doc), ...stateOf(doc, judgment, check) };
}

function names(doc: DocumentSummary): Pick<DocumentRowView, "title" | "subtitle"> {
  const product = doc.document_extras?.product_name?.trim();
  const meta = [doc.id, doc.page_count != null ? `${doc.page_count}페이지` : null].filter(Boolean).join(" · ");
  return product ? { title: product, subtitle: `${doc.filename} · ${meta}` } : { title: doc.filename, subtitle: meta };
}

function stateOf(doc: DocumentSummary, judgment: JudgmentBatchItem | undefined, check: CheckLabel): Omit<DocumentRowView, "title" | "subtitle"> {
  const allFailed = doc.counts.total > 0 && doc.counts.failed === doc.counts.total;
  if (doc.status !== "done" || allFailed) {
    return {
      stage: allFailed ? { tone: "danger", label: "모든 항 실패" } : workingStage(doc),
      note: null,
      progress: allFailed ? { ...workingProgress(doc), detail: null } : workingProgress(doc),
      action: doc.can_retry ? { kind: "retry" } : { kind: "link", label: "진행 보기", href: routes.extract(doc.id), primary: false },
    };
  }
  // 저장본 번호는 작업 전체에서 센다. 다시 추출하면 넘김 상태가 풀리므로(review_stage) 그때는 지난 저장본으로 '완료'라 하지 않는다
  const saved = judgment?.saved_snapshot != null && doc.review_stage === "판정으로 넘김";
  return {
    stage: saved ? { tone: "success", label: "완료" } : { tone: "info", label: "검수 중" },
    // 저장까지 끝낸 문서에 추출 직후 검사 문구를 붙이면 아직 할 일이 남은 것처럼 읽힌다
    note: saved ? null : checkNote(doc, check),
    progress: {
      text: `${doc.counts.done} / ${doc.counts.total}항`,
      percent: doc.counts.total > 0 ? (doc.counts.done / doc.counts.total) * 100 : 0,
      detail: reviewDetail(doc, judgment),
    },
    action: saved ? { kind: "link", label: "열기", href: routes.save(doc.id), primary: false } : continueAction(doc),
  };
}

function workingStage(doc: DocumentSummary): Label {
  switch (doc.status) {
    case "queued":
      return { tone: "neutral", label: doc.stage === "extract" ? "추출 대기" : "대기" };
    case "running":
      return { tone: "info", label: doc.stage ? STAGE_LABEL[doc.stage] : "처리 중" };
    case "failed":
      return { tone: "danger", label: "실패" };
    case "interrupted":
      return { tone: "warning", label: "멈춤" };
    case "done":
      return { tone: "danger", label: "모든 항 실패" };
  }
}

/** 막대는 끝낸 단계(또는 항)만큼만 찬다. 지금 하는 단계를 끝난 것처럼 채우지 않는다 */
function workingProgress(doc: DocumentSummary): DocumentRowView["progress"] {
  const { done, total, needs_review } = doc.counts;
  if (total > 0) {
    return { text: `${done} / ${total}항`, percent: (done / total) * 100, detail: needs_review > 0 ? `검토 필요 ${needs_review}항` : null };
  }
  const finished = Math.max(0, doc.stage_index - 1);
  const percent = (finished / doc.stage_total) * 100;
  const waiting = doc.queue_position != null ? `대기 ${doc.queue_position}번째` : "대기 중";
  if (doc.status === "queued") {
    return { text: finished > 0 ? `${finished} / ${doc.stage_total}단계 끝 · ${waiting}` : waiting, percent, detail: null };
  }
  if (doc.status === "failed" || doc.status === "interrupted") {
    return { text: `${doc.stage_index} / ${doc.stage_total}단계에서 멈춤`, percent, detail: null };
  }
  return { text: `${doc.stage_index} / ${doc.stage_total}단계`, percent, detail: null };
}

/** 추출 직후 자동 검사 결과. 통과면 적지 않는다 (목록 단계 칸이 쓰던 문구·규칙과 같다) */
function checkNote(doc: DocumentSummary, v: CheckLabel): DocumentRowView["note"] {
  if (v.tone === "success" && doc.counts.needs_review === 0) return null;
  const label = v.tone === "success" ? "검토 필요" : v.label;
  return { tone: v.tone === "danger" ? "danger" : "warning", text: label, title: `${v.detail}\n${CHECK_TITLE}` };
}

function reviewDetail(doc: DocumentSummary, judgment: JudgmentBatchItem | undefined): string | null {
  const parts: string[] = [];
  const values = doc.document_extras?.values_review;
  if (values) {
    parts.push(
      values.state === "미검수" ? "추출값 미검수"
        : values.state === "완료" && values.fields_checked >= values.fields_total ? "추출값 확인 완료"
          // 항은 모두 확인했어도 손대지 않은 칸이 남으면 저장 화면은 '일부 확인'이다 (judge/service.py value_counts)
          : values.state === "완료" ? `추출값 ${values.sections_confirmed} / ${values.sections_total}항 확인 · ${values.fields_checked} / ${values.fields_total}칸 확인`
          : `추출값 확인 ${values.sections_confirmed} / ${values.sections_total}항`,
    );
  }
  if (judgment && judgment.unreviewed > 0) parts.push(`판정 미검토 ${judgment.unreviewed}건`);
  return parts.length ? parts.join(" · ") : null;
}

function continueAction(doc: DocumentSummary): RowAction {
  switch (doc.review_stage) {
    case "판정으로 넘김":
      return { kind: "link", label: "이어서 하기", href: routes.review(doc.id, "hazard"), primary: true };
    case "추출값 확인 중":
      return { kind: "link", label: "이어서 하기", href: routes.review(doc.id, "values"), primary: true };
    default:
      return { kind: "link", label: "검수하기", href: routes.reviewMode(doc.id), primary: true };
  }
}

const SERVER = "서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.";

/** 서버 오류 원문은 개발자용이다. 사용자에게는 원인과 할 일을 말하고, 원문은 detail 로 따로 둔다 */
export function failureMessage(error: string | null, status: DocumentSummary["status"]): { text: string; detail: string } | null {
  if (!error) return null;
  const text =
    status === "interrupted" ? "서버가 재시작되어 처리가 중단되었습니다. 다시 시도해 주세요."
      : /\.env에 .+ 없습니다|connect|connection|refused|unreachable|503|502/i.test(error) ? SERVER
        : /timeout|timed out|시간 초과/i.test(error) ? "서버 응답이 지연되고 있습니다. 잠시 후 다시 시도해 주세요."
          : /pdf|encrypt|암호/i.test(error) ? "PDF 파일을 열 수 없습니다. 파일이 손상되었거나 비밀번호가 걸려 있는지 확인해 주세요."
            : "처리 중 오류가 발생했습니다. 다시 시도해 주세요.";
  return { text, detail: error };
}
