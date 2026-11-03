"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiRequestError } from "@/api/client";
import {
  isVersionConflict,
  judgmentKeys,
  postJudgmentReview,
  type Finding,
  type JudgmentView,
  type ReviewAction,
} from "@/api/judgment";
import { Pane } from "@/components/shell/layout";
import { AiChip, Button, Skeleton, StatusLabel, Textarea } from "@/components/ui";
import { actionsFor, commentRequired, isNote, verdictText, verdictTone } from "@/lib/regulation";
import { useReviewer } from "@/lib/reviewer";

export type LockReason = "rerun" | "new" | "offline" | null;

const LOCK_TEXT: Record<Exclude<LockReason, null>, string> = {
  rerun: "다시 판정이 끝나면 처리할 수 있습니다.",
  new: "새 판정을 본 뒤 처리할 수 있습니다.",
  offline: "연결되면 처리할 수 있습니다.",
};

/** 2.4 오른쪽: 고른 판정의 값, 설명, 근거, 처리. 줄을 바꾸면 key 로 새로 그려 오류 표시를 지운다 */
export function RegulationDetail({
  docId,
  view,
  finding,
  hidden,
  lock,
  draft,
  onDraft,
  onNext,
  onPin,
}: {
  docId: string;
  view: JudgmentView;
  finding: Finding;
  hidden: boolean;
  lock: LockReason;
  draft: string;
  onDraft: (text: string) => void;
  onNext: (() => void) | null;
  onPin: () => void;
}) {
  const display = view.display[finding.id];
  const review = view.reviews[finding.id];
  const reviewed = !!review && review.status !== "미검토";

  return (
    <Pane title={`${finding.label}${finding.law_label ? ` (${finding.law_label})` : ""}`} aside={<StatusLabel tone={verdictTone(finding)}>{verdictText(finding)}</StatusLabel>}>
      {hidden && <p className="rounded-sm bg-blue-soft px-3 py-2 text-sm text-blue2">거르기로 표에서 숨겨진 항목입니다.</p>}
      {review?.stale && (
        <p className="rounded-sm bg-tint px-3 py-2 text-sm text-stale">
          판정이 바뀌어 다시 확인이 필요합니다. 이전 처리: {review.status}
          {review.reviewer && ` · ${review.reviewer}`}
          {review.comment && ` — ${review.comment}`}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2 font-bold">
        <span className="rounded-xs bg-tint px-2 py-0.5">MSDS: {display.msds}</span>
        <span aria-hidden="true">→</span>
        <span className="rounded-xs bg-tint px-2 py-0.5 text-amb-text">규제DB: {display.expected}</span>
      </div>
      <p className="text-sm text-mut">{display.component ?? "제품"}</p>

      <ExplanationBlock view={view} finding={finding} />

      {display.basis_lines.length > 0 && (
        <details open={!view.explanations[finding.id]}>
          <summary className="cursor-pointer font-medium text-blue2">판단 근거 · 규제DB 기준</summary>
          <div className="mt-2 rounded-sm bg-tint px-3 py-2.5 text-sm">
            {display.basis_lines.map((line, i) => (
              <p key={i}>{line}</p>
            ))}
            {finding.expected.source && <p className="mt-1.5 text-mut">출처: {finding.expected.source}</p>}
          </div>
        </details>
      )}

      {isNote(finding) ? (
        <p className="text-sm text-mut">참고 항목은 판정이 아니어서 처리하지 않습니다.</p>
      ) : (
        <ReviewControls
          docId={docId}
          view={view}
          finding={finding}
          reviewed={reviewed && !review.stale}
          lock={lock}
          draft={draft}
          onDraft={onDraft}
          onNext={onNext}
          onPin={onPin}
        />
      )}
    </Pane>
  );
}

export function ExplanationBlock({ view, finding }: { view: JudgmentView; finding: Finding }) {
  const explanation = view.explanations[finding.id];
  if (!explanation) return null;
  if (explanation.status === "작성 중") {
    return (
      <div role="status" className="flex flex-col gap-1.5">
        <Skeleton className="w-11/12" />
        <Skeleton className="w-3/5" />
        <span className="text-sm text-mut">설명 작성 중</span>
      </div>
    );
  }
  // 검사를 통과하지 못한 설명은 숫자가 틀릴 수 있어 보여 주지 않는다. 판단 근거는 그대로 남는다
  if (!explanation.checked) return <p className="text-sm text-mut">설명이 검사를 통과하지 못해 표시하지 않습니다. 판단 근거를 확인해 주세요.</p>;
  return (
    <div className="flex flex-col items-start gap-1.5">
      <p>{explanation.summary}</p>
      {explanation.reasons.length > 0 && (
        <ul className="list-disc pl-5 text-sm">
          {explanation.reasons.map((reason, i) => (
            <li key={i}>{reason}</li>
          ))}
        </ul>
      )}
      {explanation.by === "llm" ? (
        <AiChip>AI 설명 · 검사 ✓</AiChip>
      ) : (
        <span className="rounded-xs bg-line2 px-1.5 py-px text-xs font-medium text-mut">문장틀</span>
      )}
    </div>
  );
}

export function ReviewControls({
  docId,
  view,
  finding,
  reviewed,
  lock,
  draft,
  onDraft,
  onNext,
  onPin,
}: {
  docId: string;
  view: JudgmentView;
  finding: Finding;
  reviewed: boolean;
  lock: LockReason;
  draft: string;
  onDraft: (text: string) => void;
  onNext: (() => void) | null;
  onPin: () => void;
}) {
  const client = useQueryClient();
  const reviewer = useReviewer();
  const [missing, setMissing] = useState<"comment" | "reviewer" | null>(null);
  const review = view.reviews[finding.id];

  const mutation = useMutation({
    mutationFn: ({ action, comment }: { action: ReviewAction; comment: string | null }) =>
      postJudgmentReview(docId, { finding_id: finding.id, action, comment, reviewer, seen_version: view.version }),
    onSuccess: () => {
      onDraft("");
      return client.invalidateQueries({ queryKey: judgmentKeys.all(docId) });
    },
    onError: (error) => {
      // 새 판정이 있으면 상태를 다시 받아 위쪽 띠가 뜨게 한다. 쓰던 의견은 지우지 않는다
      if (isVersionConflict(error)) void client.invalidateQueries({ queryKey: judgmentKeys.status(docId) });
    },
  });

  const locked = lock !== null || mutation.isPending;

  const submit = (action: ReviewAction) => {
    const comment = draft.trim() || null;
    if (!reviewer) return setMissing("reviewer");
    if (commentRequired(action) && !comment) {
      document.getElementById("regulation-comment")?.focus();
      return setMissing("comment");
    }
    setMissing(null);
    onPin(); // 기본 선택으로 보던 줄을 주소에 고정한다. 처리 뒤 다음 미처리 줄로 저절로 넘어가지 않게 한다
    mutation.mutate({ action, comment });
  };

  const error = mutation.error;
  const nextButton = onNext && <Button onClick={onNext}>다음 미처리</Button>;

  return (
    <div className="flex flex-col gap-2.5 border-t border-line pt-3">
      {reviewed && (
        <p className="rounded-sm bg-blue-soft px-3 py-2 text-sm text-blue2">
          {review.status}
          {review.reviewer && ` · ${review.reviewer}`}
          {review.comment && ` — ${review.comment}`}
        </p>
      )}
      <label htmlFor="regulation-comment" className="text-sm">
        의견
        {missing === "comment" ? (
          <span className="text-red"> — 이유가 필요합니다</span>
        ) : (
          !reviewed && <span className="text-mut"> (예외 승인은 필수)</span>
        )}
      </label>
      <Textarea
        id="regulation-comment"
        value={draft}
        disabled={locked}
        maxLength={2000}
        aria-invalid={missing === "comment" || undefined}
        onChange={(e) => {
          onDraft(e.target.value);
          if (missing === "comment") setMissing(null);
        }}
      />
      <div className="flex flex-wrap items-center gap-2">
        {reviewed ? (
          <>
            <Button disabled={locked} onClick={() => submit("의견")}>
              의견 추가
            </Button>
            <Button disabled={locked} onClick={() => submit("되돌리기")}>
              되돌리기
            </Button>
          </>
        ) : (
          actionsFor(finding).map((action, i) => (
            <Button key={action} variant={i === 0 ? "primary" : "default"} disabled={locked} onClick={() => submit(action)}>
              {mutation.isPending && mutation.variables?.action === action ? "저장 중…" : action}
            </Button>
          ))
        )}
        {nextButton}
      </div>
      {lock && <p className="text-sm text-mut">{LOCK_TEXT[lock]}</p>}
      {missing === "reviewer" && (
        <p role="alert" className="text-sm text-red">
          처리하려면 머리줄에서 검토자 이름을 먼저 정해 주세요.
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm break-words text-red">
          {isVersionConflict(error)
            ? "처리되지 않았습니다. 그 사이 새 판정이 만들어졌습니다. 쓰던 의견은 남겨 두었습니다."
            : `처리하지 못했습니다${error instanceof ApiRequestError ? `: ${error.message}` : ". 연결을 확인해 주세요"}. 쓰던 의견은 남겨 두었습니다.`}
        </p>
      )}
    </div>
  );
}
