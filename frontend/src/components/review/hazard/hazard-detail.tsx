"use client";

import type { Finding, JudgmentView } from "@/api/judgment";
import { Pane } from "@/components/shell/layout";
import { StatusLabel } from "@/components/ui";
import { cn } from "@/lib/cn";
import { basisTitle, valueEmphasis } from "@/lib/hazard";
import { isNote, verdictText, verdictTone } from "@/lib/regulation";
import { ExplanationBlock, ReviewControls, type LockReason } from "../regulation/regulation-detail";

const VALUE_STYLE = {
  differ: { msds: "bg-red-soft text-red line-through", expected: "bg-grn-soft text-grn" },
  same: { msds: "bg-grn-soft text-grn", expected: "bg-grn-soft text-grn" },
  neutral: { msds: "bg-tint", expected: "bg-tint" },
} as const;

/** 2.3 오른쪽: 고른 판정의 값, 설명, 근거와 계산 과정, 처리. 줄을 바꾸면 key 로 새로 그려 오류 표시를 지운다 */
export function HazardDetail({
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
  const reviewed = !!review && review.status !== "미검토" && !review.stale;
  const emphasis = valueEmphasis(finding);
  const hasBasis = display.basis_lines.length > 0 || display.calc_lines.length > 0;

  return (
    <Pane
      title={finding.label}
      className={cn(finding.verdict === "불일치" && "border-l-4 border-red")}
      aside={<StatusLabel tone={verdictTone(finding)}>{verdictText(finding)}</StatusLabel>}
    >
      {hidden && <p className="rounded-sm bg-blue-soft px-3 py-2 text-sm text-blue2">거르기로 표에서 숨겨진 항목입니다.</p>}
      {review?.stale && (
        <p className="rounded-sm bg-tint px-3 py-2 text-sm text-stale">
          판정이 바뀌어 다시 확인이 필요합니다. 이전 처리: {review.status}
          {review.reviewer && ` · ${review.reviewer}`}
          {review.comment && ` — ${review.comment}`}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2 font-bold">
        <span className={cn("rounded-xs px-2 py-0.5", VALUE_STYLE[emphasis].msds)}>
          <span className="sr-only">MSDS 기재: </span>
          {display.msds}
        </span>
        <span aria-hidden="true">→</span>
        <span className={cn("rounded-xs px-2 py-0.5", VALUE_STYLE[emphasis].expected)}>
          <span className="sr-only">검증 결과: </span>
          {display.expected}
        </span>
      </div>

      <ExplanationBlock view={view} finding={finding} />

      {hasBasis && (
        <details open={!view.explanations[finding.id]}>
          <summary className="cursor-pointer font-medium text-blue2">{basisTitle(display)}</summary>
          <div className="mt-2 flex flex-col gap-1 rounded-sm bg-tint px-3 py-2.5 text-sm">
            {display.basis_lines.map((line, i) => (
              <p key={`basis-${i}`}>{line}</p>
            ))}
            {display.calc_lines.map((line, i) => (
              <p key={`calc-${i}`} className="tabular-nums">
                {line}
              </p>
            ))}
            {finding.expected.source && <p className="mt-1 text-mut">출처: {finding.expected.source}</p>}
          </div>
        </details>
      )}

      {isNote(finding) ? (
        <p className="text-sm text-mut">참고·범위 외 항목은 판정이 아니어서 처리하지 않습니다.</p>
      ) : (
        <ReviewControls
          docId={docId}
          view={view}
          finding={finding}
          reviewed={reviewed}
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
