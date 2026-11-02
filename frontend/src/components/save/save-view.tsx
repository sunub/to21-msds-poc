"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { documentDetailQuery, reviewQuery } from "@/api/documents";
import { findingsQuery } from "@/api/findings";
import type { Verdict } from "@/api/findings-schemas";
import { saveDocument, type SaveOptions, type SaveResponse } from "@/api/save";
import { VERDICT_LABEL, VERDICT_ORDER, VERDICT_TONE } from "@/components/review/hazard/verdict";
import { useReviewState } from "@/components/review/review-state";
import { useValidationId } from "@/components/review/shared/use-validation-id";
import { Foot, Row } from "@/components/shell/layout";
import { Button, Callout, Checkbox, Skeleton, Spinner, StatusLabel, buttonStyles } from "@/components/ui";
import { cn } from "@/lib/cn";
import { useReviewer } from "@/lib/reviewer";
import { routes } from "@/lib/routes";

/** "2026년 11월 2일 오후 2:30" (한국 시간) */
const SAVED_AT = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "long",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

/** 판정 요약에 건수가 0이어도 보여 주는 판정 (시안). 구버전·해당 없음·비교 제외는 있을 때만 보여 준다 */
const SUMMARY_ALWAYS: Verdict[] = ["mismatch", "borderline", "insufficient_evidence", "warning", "match"];

const stem = (filename: string) => filename.replace(/\.pdf$/i, "");

/** 저장 화면 (3.1 모두 처리, 3.2 미검토 포함). 어느 쪽인지는 검수 화면에서 이어받은 처리 상태로 정한다. */
export function SaveView({ docId }: { docId: string }) {
  const reviewer = useReviewer() || "미지정";
  const { ready, getState, unresolvedCount } = useReviewState();
  const validation = useValidationId(docId);
  const hazard = useQuery(findingsQuery(docId, validation, { section: 2 }));
  const regulation = useQuery(findingsQuery(docId, validation, { section: 15 }));
  const { data: doc } = useQuery(documentDetailQuery(docId));
  // 추출값 확인 기록이 있을 때만 쓴다 (없으면 해당 칸을 그리지 않는다)
  const review = useQuery({ ...reviewQuery(docId), enabled: doc?.status === "done", retry: false }).data;

  const [options, setOptions] = useState<SaveOptions>({ includeRevisionAppendix: true, includeOpinions: true });
  const failDemo = useSearchParams().get("fail") === "1";

  const findings = useMemo(() => [...(hazard.data?.items ?? []), ...(regulation.data?.items ?? [])], [hazard.data, regulation.data]);
  const confirmed = findings.filter((f) => getState(f.finding_id).state === "confirmed").length;
  const exception = findings.filter((f) => getState(f.finding_id).state === "exception_approved").length;
  const unresolved = unresolvedCount(2) + unresolvedCount(15);
  const verdictCounts = useMemo(() => {
    const n: Partial<Record<Verdict, number>> = {};
    for (const f of findings) n[f.verdict] = (n[f.verdict] ?? 0) + 1;
    return n;
  }, [findings]);

  const save = useMutation({
    mutationFn: () => saveDocument(docId, options, { reviewer, confirmed, exception, unresolved }, { fail: failDemo }),
  });
  const saved: SaveResponse | undefined = save.data;

  // 처리 상태를 읽어 오기 전에는 어느 화면인지 알 수 없다 (잠깐 틀린 화면이 보이지 않게 기다린다)
  if (!ready || hazard.isPending || regulation.isPending) return <Skeleton className="w-2/3" />;
  if (hazard.isError || regulation.isError) {
    return (
      <Callout tone="danger" role="alert" className="flex flex-wrap items-center gap-2">
        <span>판정 결과를 불러오지 못했습니다.</span>
        <Button onClick={() => void Promise.all([hazard.refetch(), regulation.refetch()])}>다시 불러오기</Button>
      </Callout>
    );
  }

  const incomplete = unresolved > 0;
  const saving = save.isPending;
  const fileName = `${doc ? stem(doc.filename) : docId}_MSDS_검토결과.pdf`;
  const extractionDone = review ? review.summary.sections_confirmed >= review.summary.sections_total : null;

  const title = !incomplete
    ? "검토를 마쳤습니다"
    : saved
      ? "저장했습니다. 처리하지 않은 판정이 남아 있습니다"
      : "처리하지 않은 판정이 남아 있습니다";
  const lead = !incomplete
    ? "결과를 데이터베이스에 저장하고, 재생성 MSDS와 판정이 담긴 PDF로 내려받을 수 있습니다."
    : saved
      ? "결과를 데이터베이스에 저장했습니다. 미검토 판정은 그대로 \"미검토\"로 기록되고, PDF에도 같은 표시가 붙습니다."
      : "결과를 데이터베이스에 저장하면 미검토 판정은 그대로 \"미검토\"로 기록되고, PDF에도 같은 표시가 붙습니다.";

  const status = saving
    ? { tone: "info" as const, label: "저장 중" }
    : save.isError
      ? { tone: "danger" as const, label: "저장하지 못함" }
      : saved
        ? { tone: "success" as const, label: incomplete ? "저장됨 · 미검토 포함" : "저장됨" }
        : { tone: "neutral" as const, label: "저장 전" };

  return (
    <div className="flex flex-col gap-6">
      <section>
        <h1 className="text-2xl font-bold">{title}</h1>
        <p className="mt-1 text-mut">{lead}</p>
      </section>

      <section aria-label="2차 판정 요약과 처리 상태" className="flex flex-col gap-3 rounded-md border border-line bg-white px-5 py-4">
        <div className="flex flex-wrap items-center gap-x-7 gap-y-2">
          <b>2차 판정 요약</b>
          {VERDICT_ORDER.filter((v) => SUMMARY_ALWAYS.includes(v) || (verdictCounts[v] ?? 0) > 0).map((v) => (
            <StatusLabel key={v} tone={VERDICT_TONE[v]} className="text-base text-ink">
              {VERDICT_LABEL[v]} {verdictCounts[v] ?? 0}
            </StatusLabel>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-x-3.5 gap-y-2 border-t border-line2 pt-3">
          <b>처리 상태</b>
          <span
            className={cn(
              "rounded-sm px-3 py-1 font-bold",
              incomplete ? "bg-tint text-amb-text" : "bg-grn-soft text-grn",
            )}
          >
            미검토 {unresolved}건
          </span>
          <span className="text-mut">
            처리 {confirmed + exception}건 (확정 {confirmed} · 예외 승인 {exception})
          </span>
          {incomplete && (
            <Link href={routes.review(docId, "history")} className="px-1.5">
              판정 처리하러 가기 ›
            </Link>
          )}
          <span className="flex-1" />
          {extractionDone !== null && (
            <span className={cn("rounded-sm px-3 py-1 font-bold", extractionDone ? "bg-grn-soft text-grn" : "bg-tint text-amb-text")}>
              {extractionDone ? "추출값 확인함" : "추출값 미검수"}
            </span>
          )}
        </div>
      </section>

      <Row className="items-stretch">
        <section aria-labelledby="save-db" className="flex min-w-0 grow basis-110 flex-col gap-4 rounded-md border border-line bg-white p-6">
          <div className="flex items-center justify-between gap-3">
            <h2 id="save-db" className="text-lg font-bold">
              데이터베이스에 저장
            </h2>
            <StatusLabel tone={status.tone}>{status.label}</StatusLabel>
          </div>

          <dl className="m-0 grid grid-cols-[5rem_1fr] gap-x-3 gap-y-1.5">
            <dt className="text-mut">저장 시각</dt>
            <dd className="m-0">{saved ? SAVED_AT.format(new Date(saved.saved_at)) : "—"}</dd>
            <dt className="text-mut">검토자</dt>
            <dd className="m-0">{reviewer}</dd>
            <dt className="text-mut">저장 내용</dt>
            <dd className="m-0">최종 값, 값의 출처, 2차 판정, 처리 상태, 의견</dd>
          </dl>

          {review ? (
            <div className="overflow-hidden rounded-sm border border-line">
              <div className="flex bg-tint px-3.5 py-2 text-sm font-medium text-mut">
                <span className="flex-1">값의 출처</span>
                <span className="w-16 text-right">칸 수</span>
              </div>
              {[
                ["확인함", review.summary.fields_checked],
                ["수정됨", review.summary.fields_edited],
                ["미검수 (확인하지 않음)", Math.max(0, review.summary.fields_total - review.summary.fields_checked - review.summary.fields_edited)],
              ].map(([label, n]) => (
                <div key={label} className="flex border-t border-line2 px-3.5 py-2.5">
                  <span className="flex-1">{label}</span>
                  <span className="w-16 text-right tabular-nums">{n}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-mut">추출값 확인 기록이 없어 값의 출처별 칸 수는 표시하지 않습니다.</p>
          )}

          <p className="text-sm text-mut">수정과 추가에는 원래 값, 근거, 검토자, 시각이 함께 남습니다. 다시 저장하면 같은 문서의 기록을 덮어씁니다.</p>

          {saving && (
            <div role="status" className="flex items-center gap-3 text-sm text-mut">
              <Spinner label="저장 중" />
              <span>저장하는 중입니다…</span>
            </div>
          )}
          {saved && !saving && (
            <Callout tone="info" role="status" className="flex flex-col gap-0.5">
              <b>저장했습니다.{incomplete && ` 미검토 ${saved.included.unreviewed}건 포함`}</b>
              <span>
                저장 번호 {saved.snapshot_id} · 포함한 처리 {saved.included.confirmed + saved.included.exception}건 (확정 {saved.included.confirmed} · 예외 승인{" "}
                {saved.included.exception})
                {incomplete ? ` · 미검토 ${saved.included.unreviewed}건` : ""}
              </span>
            </Callout>
          )}
          {save.isError && !saving && (
            <Callout tone="danger" role="alert" className="flex flex-wrap items-center gap-2">
              <span>저장하지 못했습니다. {save.error instanceof Error ? save.error.message : ""} 다시 시도해 주세요.</span>
              <Button onClick={() => save.mutate()}>다시 시도</Button>
            </Callout>
          )}

          <div className="mt-auto flex flex-wrap gap-2">
            <Button variant="primary" size="lg" disabled={saving} aria-busy={saving} onClick={() => save.mutate()}>
              {saving ? "저장 중…" : saved ? "다시 저장하기" : "저장하기"}
            </Button>
          </div>
        </section>

        <section aria-labelledby="save-pdf" className="flex min-w-0 grow basis-110 flex-col gap-4 rounded-md border border-line bg-white p-6">
          <h2 id="save-pdf" className="text-lg font-bold">
            PDF로 출력
          </h2>
          <ul className="m-0 list-disc pl-4.5 leading-relaxed text-sub">
            <li>표지 · 문서 번호, 제품명, 원본 파일, 검토자, 검토 일시, 2차 판정 개수와 미검토 건수</li>
            <li>재생성 MSDS · 최종 값으로 만든 16항 문서</li>
            <li>2차 판정 표 · 2항, 15항, 처리 상태와 검토자 의견</li>
            <li>부록 · 수정 이력</li>
          </ul>
          <div className="flex flex-col gap-2">
            <Checkbox
              label="수정 이력 부록 포함"
              checked={options.includeRevisionAppendix}
              onChange={(e) => setOptions({ ...options, includeRevisionAppendix: e.target.checked })}
            />
            <Checkbox
              label="검토자 의견 포함"
              checked={options.includeOpinions}
              onChange={(e) => setOptions({ ...options, includeOpinions: e.target.checked })}
            />
          </div>
          <p className="text-sm text-mut">
            {incomplete && "미검토 판정은 PDF에 \"미검토\"로 표시됩니다. "}원문 PDF는 들어 있지 않습니다. 파일 이름: {fileName}
          </p>
          <div className="mt-auto flex flex-col gap-2">
            <div className="flex flex-wrap gap-2">
              <Button variant="primary" size="lg" disabled>
                PDF로 출력
              </Button>
              <Button size="lg" disabled>
                미리 보기
              </Button>
            </div>
            <p className="text-sm text-mut">PDF 출력은 아직 연결되지 않았습니다.</p>
          </div>
        </section>
      </Row>

      <Foot>
        <div className="flex flex-wrap items-center gap-2">
          {incomplete && (
            <Link href={routes.review(docId, "history")} className={buttonStyles({ size: "lg" })}>
              판정 처리하러 가기
            </Link>
          )}
          <Link href={routes.review(docId)} className={buttonStyles({ size: "lg" })}>
            검수로 돌아가기
          </Link>
        </div>
        <Link href={routes.home()} className={buttonStyles({ size: "lg" })}>
          목록으로
        </Link>
      </Foot>
    </div>
  );
}
