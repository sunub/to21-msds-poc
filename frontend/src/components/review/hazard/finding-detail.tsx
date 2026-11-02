"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { findingDetailQuery } from "@/api/findings";
import type { FindingDetail, FindingSummary } from "@/api/findings-schemas";
import { AiChip, Button, Callout, Input, Skeleton, StatusLabel } from "@/components/ui";
import { OPINION_MAX, REVIEW_STATE_LABEL, isProcessed, useReviewState } from "../review-state";
import { SEVERITY_LABEL, VERDICT_LABEL, VERDICT_TONE, isActionable } from "./verdict";

/** 선택한 판정의 상세. 확정·예외 승인·의견은 공유 상태(review-state)에 남고 서버에는 보내지 않는다. */
export function FindingDetailView({
  docId,
  validationId,
  finding,
}: {
  docId: string;
  validationId: string;
  finding: FindingSummary;
}) {
  const { data, isPending, isError, refetch } = useQuery(findingDetailQuery(docId, validationId, finding.finding_id));

  return (
    <div className="flex flex-col gap-3.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h3 className="text-xl font-bold">{finding.item}</h3>
        <StatusLabel tone={VERDICT_TONE[finding.verdict]} className="text-base font-medium">
          {VERDICT_LABEL[finding.verdict]}
          {finding.severity && ` · ${SEVERITY_LABEL[finding.severity]}`}
        </StatusLabel>
      </div>

      <dl className="m-0 grid grid-cols-[auto_1fr] items-baseline gap-x-3 gap-y-1.5 text-base">
        <dt className="text-sm text-mut">MSDS 기재</dt>
        <dd className="m-0">
          <span className="rounded-xs bg-red-soft px-2 py-0.5 font-bold text-red">{finding.msds_value.text}</span>
        </dd>
        <dt className="text-sm text-mut">기준값</dt>
        <dd className="m-0">
          <span className="rounded-xs bg-grn-soft px-2 py-0.5 font-bold text-grn">{finding.expected_value.text}</span>
        </dd>
      </dl>

      {isPending && <Skeleton className="w-2/3" />}
      {isError && (
        <Callout tone="danger" role="alert" className="flex flex-wrap items-center gap-2">
          <span>판정 상세를 불러오지 못했습니다.</span>
          <Button onClick={() => void refetch()}>다시 불러오기</Button>
        </Callout>
      )}
      {data && <DetailBody detail={data} />}

      {isActionable(finding.verdict) && <ReviewActions finding={finding} />}
    </div>
  );
}

/** 확정·예외 승인 버튼과 의견 칸. 일치·해당 없음·비교 제외 판정은 처리 대상이 아니라 그리지 않는다. */
function ReviewActions({ finding }: { finding: FindingSummary }) {
  const { getState, confirm, approveException, undo } = useReviewState();
  const { state, opinion } = getState(finding.finding_id);
  const [draft, setDraft] = useState("");
  const inputId = `opinion-${finding.finding_id}`;
  const needOpinion = draft.trim() === "";

  if (isProcessed(state)) {
    return (
      <div className="flex flex-col gap-2 border-t border-line2 pt-3">
        <div className="flex flex-wrap items-center gap-2">
          <StatusLabel tone="success">{REVIEW_STATE_LABEL[state]}</StatusLabel>
          <Button
            variant="link"
            onClick={() => {
              undo(finding.finding_id);
              setDraft("");
            }}
          >
            되돌리기
          </Button>
        </div>
        {opinion && (
          <p className="text-sm break-words">
            <span className="text-mut">의견 </span>
            {opinion}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2 border-t border-line2 pt-3">
      {state === "opinion" && (
        <p className="text-sm break-words">
          <b className="text-amb-text">{REVIEW_STATE_LABEL.opinion}</b>
          {opinion && <span className="text-mut"> · {opinion}</span>}
        </p>
      )}
      <label htmlFor={inputId} className="sr-only">
        의견 남기기
      </label>
      <Input
        id={inputId}
        value={draft}
        maxLength={OPINION_MAX}
        placeholder="의견 남기기"
        aria-describedby={`${inputId}-hint`}
        onChange={(e) => setDraft(e.target.value)}
      />
      <p id={`${inputId}-hint`} className="text-xs text-mut tabular-nums">
        확정은 의견을 비워도 됩니다. 예외 승인은 의견이 있어야 합니다. ({draft.length}/{OPINION_MAX}자)
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" onClick={() => confirm(finding.finding_id, draft)}>
          {VERDICT_LABEL[finding.verdict]} 확정
        </Button>
        <Button
          variant="outline"
          // 비활성일 때도 글자가 읽히도록 흐리게 하지 않고 색으로 구분한다 (대비 4.5:1 이상)
          className="disabled:border-line disabled:bg-tint disabled:text-sub disabled:opacity-100"
          disabled={needOpinion}
          onClick={() => approveException(finding.finding_id, draft)}
        >
          예외 승인
        </Button>
      </div>
    </div>
  );
}

function DetailBody({ detail }: { detail: FindingDetail }) {
  const { explanation, trace, evidence, finding } = detail;
  const [open, setOpen] = useState(false);
  const pages = [...new Set(evidence.map((e) => e.page_no))];
  const pagesText = pages.map((p) => `${p}쪽`).join(", ");
  const panelId = `trace-${finding.finding_id}`;

  return (
    <>
      {explanation.source !== "unavailable" && (
        <div className="flex flex-col gap-1.5">
          <p className="leading-relaxed">{explanation.text}</p>
          <div className="flex flex-wrap items-center gap-2 text-sm text-mut">
            {explanation.source === "ai" ? (
              <AiChip>AI 설명{explanation.check_status === "passed" && " · 검사 ✓"}</AiChip>
            ) : (
              <span className="rounded-xs bg-tint px-1.5 py-px text-xs font-medium text-sub">기본 문장</span>
            )}
            {explanation.check_status === "failed" && <span className="text-red">자동 검사를 통과하지 못했습니다</span>}
          </div>
          {explanation.limitations.length > 0 && (
            <Callout>
              <ul className="m-0 list-none p-0">
                {explanation.limitations.map((l, i) => (
                  <li key={i}>{l}</li>
                ))}
              </ul>
            </Callout>
          )}
        </div>
      )}

      <p className="text-sm">
        <span className="text-mut">판단 근거 </span>
        {finding.method}
      </p>

      {trace && (
        <div>
          <button
            type="button"
            aria-expanded={open}
            aria-controls={panelId}
            onClick={() => setOpen(!open)}
            className="font-medium text-blue2"
          >
            {open ? "▾" : "▸"} 계산 과정
          </button>
          {open && (
            <div id={panelId} className="mt-2 flex flex-col gap-1 rounded-sm bg-tint px-3 py-2.5 text-sm">
              {trace.inputs.map((line, i) => (
                <div key={i}>{line}</div>
              ))}
              {trace.thresholds.map((t, i) => (
                <div key={`t${i}`} className="text-mut">
                  기준: {t}
                </div>
              ))}
              <div className="text-xs text-mut">
                규칙 {trace.rule.id} (v{trace.rule.version})
              </div>
            </div>
          )}
        </div>
      )}

      {pages.length > 0 && <p className="text-sm text-mut">원문 근거 {pagesText}</p>}
    </>
  );
}
