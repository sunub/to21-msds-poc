/*
 * 목록·머리줄의 단계 칸과 버튼을 정한다: 추출 서버(A)의 문서 상태와 판정 서버(B)의 요약을 합친다 (계약 6-screens 1.1).
 *
 * | A status              | B 저장 | 단계 칸                              | 버튼         |
 * | queued·running        | —      | 추출 중 n/5단계 (대기 중이면 대기 n번째) | 진행 보기    |
 * | failed·interrupted    | —      | 실패                                  | 진행 보기 (다시 실행) |
 * | done                  | 없음   | 검수 중 · 미검수/일부/완료             | 이어서 하기  |
 * | done                  | 있음   | 완료                                  | 열기         |
 * 판정 서버가 없거나 아직 대답하지 않았으면(judgment 없음) 저장본이 없는 것으로 본다.
 */
import type { JudgmentBatchItem } from "@/api/contract/api";
import type { DocumentSummary } from "@/api/schemas";
import type { Tone } from "@/components/ui";
import { routes } from "./routes";
import { allSectionsFailed, statusLabel } from "./status";

export type DocStage = { label: string; tone: Tone; action: string; href: string };

export function documentStage(doc: DocumentSummary, judgment?: JudgmentBatchItem): DocStage {
  const progress = routes.extract(doc.id);
  switch (doc.status) {
    case "queued":
      return { label: doc.queue_position != null ? `대기 ${doc.queue_position}번째` : "대기", tone: "neutral", action: "진행 보기", href: progress };
    case "running":
      return { label: `추출 중 ${doc.stage_index}/${doc.stage_total}단계`, tone: "info", action: "진행 보기", href: progress };
    case "failed":
    case "interrupted":
      return { ...statusLabel(doc), action: "진행 보기", href: progress };
    case "done": {
      // 모든 항이 실패한 문서는 검수할 값이 없다
      if (allSectionsFailed(doc)) return { ...statusLabel(doc), action: "진행 보기", href: progress };
      if (judgment && judgment.saved_snapshot !== null) {
        return { label: "완료", tone: "success", action: "열기", href: routes.review(doc.id, "hazard") };
      }
      // 어디서 이어 열지: 추출값 확인 중이면 추출값 탭, 판정으로 넘겼으면 2항, 아직 안 골랐으면 방식 선택
      const href =
        doc.review_stage === "추출값 확인 중"
          ? routes.review(doc.id, "values")
          : doc.review_stage === "판정으로 넘김"
            ? routes.review(doc.id, "hazard")
            : routes.reviewMode(doc.id);
      return { label: `검수 중 · ${doc.values_review?.state ?? "미검수"}`, tone: "info", action: "이어서 하기", href };
    }
  }
}
