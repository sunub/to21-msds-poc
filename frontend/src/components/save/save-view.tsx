"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { documentDetailQuery } from "@/api/documents";
import type { ReportRequest } from "@/api/contract/api";
import type { Verdict } from "@/api/findings-schemas";
import { conflictText, isConflict, judgmentErrorText, judgmentKeys, postReport, postSnapshot, saveOverviewQuery } from "@/api/judgments";
import { VERDICT_TONE } from "@/components/review/hazard/verdict";
import { Foot, Row } from "@/components/shell/layout";
import { Button, Callout, Checkbox, Skeleton, Spinner, StatusLabel, buttonStyles } from "@/components/ui";
import { cn } from "@/lib/cn";
import { downloadBlob, openBlob } from "@/lib/download";
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

/** 판정 요약의 칸: [서버 verdict 이름, 화면 색, 건수가 0이어도 보이는가]. 참고·범위 외는 있을 때만 보여 준다 */
const SUMMARY: [string, Verdict, boolean][] = [
  ["불일치", "mismatch", true],
  ["경계", "borderline", true],
  ["근거부족", "insufficient_evidence", true],
  ["경고", "warning", true],
  ["일치", "match", true],
  ["참고", "not_applicable", false],
  ["범위 외", "excluded", false],
];

/** PDF 에 넣을 항목 (계약 report_request.include) */
const INCLUDE_ITEMS: { key: keyof ReportRequest["include"]; label: string }[] = [
  { key: "regenerated_msds", label: "재생성 MSDS" },
  { key: "findings_2", label: "2항 판정 표" },
  { key: "findings_15", label: "15항 판정 표" },
  { key: "components", label: "성분별 요약" },
  { key: "history", label: "검토 이력" },
];

const stem = (filename: string) => filename.replace(/\.pdf$/i, "");

const DISABLED_BUTTON = "disabled:cursor-not-allowed disabled:border-dashed disabled:border-field-line disabled:bg-line2 disabled:text-mut disabled:opacity-100";

type ReportKind = "pdf" | "preview" | "html" | "xlsx" | "json";

/** 저장 화면 (3.1 모두 처리, 3.2 미검토 포함). 어느 쪽인지는 서버의 저장 개요(save-overview)로 정한다. */
export function SaveView({ docId }: { docId: string }) {
  const reviewer = useReviewer() || "미지정";
  const queryClient = useQueryClient();
  const overviewQuery = useQuery(saveOverviewQuery(docId));
  const { data: doc } = useQuery(documentDetailQuery(docId));
  const [include, setInclude] = useState<ReportRequest["include"]>({ regenerated_msds: true, findings_2: true, findings_15: true, components: true, history: true });
  const failDemo = useSearchParams().get("fail") === "1";

  const overview = overviewQuery.data;
  const lastSnapshot = overview?.snapshots[0];

  const save = useMutation({
    // 화면이 읽은 판정 버전(seen_version)과 함께 저장한다: 더 새 판정이 있으면 409
    mutationFn: () => postSnapshot(docId, { reviewer, seen_version: overview?.version ?? 1 }, { fail: failDemo }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: [...judgmentKeys.all] }),
  });
  const saveConflict = save.isError && isConflict(save.error);
  const saved = save.data;

  const report = useMutation({
    mutationFn: async (kind: ReportKind) => {
      const format = kind === "preview" ? "html" : kind;
      // 미리 보기는 저장하지 않은 최신 판정(snapshot_no null)으로, 나머지는 가장 최근 저장본으로 만든다
      const request: ReportRequest = { format, snapshot_no: kind === "preview" ? null : (lastSnapshot?.snapshot_no ?? null), include };
      const file = await postReport(docId, request, doc?.product_name ?? (doc ? stem(doc.filename) : docId));
      if (kind === "preview") {
        if (!openBlob(file.blob)) throw new Error("새 탭이 막혀 미리 보기를 열지 못했습니다. 팝업을 허용해 주세요.");
      } else downloadBlob(file.blob, file.filename);
    },
  });

  if (overviewQuery.isError) {
    return (
      <Callout tone="danger" role="alert" className="flex flex-wrap items-center gap-2">
        <span>{judgmentErrorText(overviewQuery.error, "판정 결과를 불러오지 못했습니다.")}</span>
        <Button onClick={() => void overviewQuery.refetch()}>다시 불러오기</Button>
      </Callout>
    );
  }
  if (!overview) return <Skeleton className="w-2/3" />;

  const unresolved = overview.reviews.미검토;
  const confirmed = overview.reviews["불일치 확정"] + overview.reviews.확인;
  const exception = overview.reviews["예외 승인"];
  const incomplete = unresolved > 0;
  const saving = save.isPending;
  const reporting = report.isPending;
  const fileName = `${doc ? stem(doc.filename) : docId}_MSDS_검토결과.pdf`;
  const values = overview.values;

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
      : saved || lastSnapshot
        ? { tone: "success" as const, label: `저장됨 · 저장본 ${(saved ?? lastSnapshot)!.snapshot_no}${incomplete ? " · 미검토 포함" : ""}` }
        : { tone: "neutral" as const, label: "저장 전" };
  const savedAt = (saved ?? lastSnapshot)?.saved_at;

  const reportError = report.isError ? (report.error instanceof Error ? report.error.message : "리포트를 만들지 못했습니다.") : null;

  return (
    <div className="flex flex-col gap-6 [word-break:keep-all]">
      <section>
        <h1 className="text-2xl font-bold">{title}</h1>
        <p className="mt-1 text-mut">{lead}</p>
      </section>

      <section aria-label="2차 판정 요약과 처리 상태" className="flex flex-col gap-3 rounded-md border border-line bg-white px-5 py-4">
        <div className="flex flex-wrap items-center gap-x-7 gap-y-2">
          <b>2차 판정 요약</b>
          {SUMMARY.filter(([key, , always]) => always || overview.verdicts.total[key as keyof typeof overview.verdicts.total] > 0).map(([key, verdict]) => (
            <StatusLabel key={key} tone={VERDICT_TONE[verdict]} className="text-base text-ink">
              {key} {overview.verdicts.total[key as keyof typeof overview.verdicts.total]}
            </StatusLabel>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-x-3.5 gap-y-2 border-t border-line2 pt-3">
          <b>처리 상태</b>
          <span className={cn("rounded-sm px-3 py-1 font-bold", incomplete ? "bg-tint text-amb-text" : "bg-grn-soft text-grn")}>미검토 {unresolved}건</span>
          <span className="text-mut">
            처리 {confirmed + exception}건 (확정 {confirmed} · 예외 승인 {exception})
          </span>
          {incomplete && (
            <Link href={routes.review(docId, "history")} className="px-1.5">
              판정 처리하러 가기 ›
            </Link>
          )}
          <span className="flex-1" />
          <span className={cn("rounded-sm px-3 py-1 font-bold", values.state === "완료" ? "bg-grn-soft text-grn" : "bg-tint text-amb-text")}>
            {values.state === "완료" ? "추출값 확인함" : values.state === "일부" ? "추출값 일부 확인" : "추출값 미검수"}
          </span>
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
            <dd className="m-0">{savedAt ? SAVED_AT.format(new Date(savedAt)) : "—"}</dd>
            <dt className="text-mut">검토자</dt>
            <dd className="m-0">{reviewer}</dd>
            <dt className="text-mut">저장 내용</dt>
            <dd className="m-0">최종 값, 값의 출처, 2차 판정, 처리 상태, 의견</dd>
          </dl>

          <div className="overflow-hidden rounded-sm border border-line">
            <div className="flex bg-tint px-3.5 py-2 text-sm font-medium text-mut">
              <span className="flex-1">값의 출처</span>
              <span className="w-16 text-right">칸 수</span>
            </div>
            {(
              [
                ["확인함", values.confirmed],
                ["수정됨", values.edited],
                ["미검수 (확인하지 않음)", values.model_as_is],
              ] as const
            ).map(([label, n]) => (
              <div key={label} className="flex border-t border-line2 px-3.5 py-2.5">
                <span className="flex-1">{label}</span>
                <span className="w-16 text-right tabular-nums">{n}</span>
              </div>
            ))}
          </div>

          <p className="text-sm text-mut">수정과 추가에는 원래 값, 근거, 검토자, 시각이 함께 남습니다. 다시 저장하면 새 저장본 번호로 남습니다.</p>

          {saving && (
            <div role="status" className="flex items-center gap-3 text-sm text-mut">
              <Spinner label="저장 중" />
              <span>저장하는 중입니다…</span>
            </div>
          )}
          {saved && !saving && (
            <Callout tone="info" role="status" className="flex flex-col gap-0.5">
              <b>
                저장했습니다. 저장본 {saved.snapshot_no}
                {incomplete && ` · 미검토 ${saved.counts.미검토}건 포함`}
              </b>
              <span>
                포함한 처리 {saved.counts["불일치 확정"] + saved.counts.확인 + saved.counts["예외 승인"]}건 (확정 {saved.counts["불일치 확정"] + saved.counts.확인} · 예외 승인{" "}
                {saved.counts["예외 승인"]}){incomplete ? ` · 미검토 ${saved.counts.미검토}건` : ""} · 미검수 칸 {saved.counts["미검수 칸"]}
              </span>
            </Callout>
          )}
          {saveConflict && !saving && (
            <Callout tone="danger" role="alert" className="flex flex-wrap items-center gap-2">
              <span>{conflictText(save.error)}</span>
              <Button
                onClick={() => {
                  save.reset();
                  void queryClient.invalidateQueries({ queryKey: [...judgmentKeys.all] });
                }}
              >
                새로고침
              </Button>
            </Callout>
          )}
          {save.isError && !saveConflict && !saving && (
            <Callout tone="danger" role="alert" className="flex flex-wrap items-center gap-2">
              <span>저장하지 못했습니다. 잠시 뒤 다시 시도해 주세요.</span>
              <Button onClick={() => save.mutate()}>다시 시도</Button>
            </Callout>
          )}

          <div className="mt-auto flex flex-wrap gap-2">
            <Button variant="primary" size="lg" disabled={saving} aria-busy={saving} onClick={() => save.mutate()}>
              {saving ? "저장 중…" : saved || lastSnapshot ? "다시 저장하기" : "저장하기"}
            </Button>
            <Button size="lg" disabled={reporting} onClick={() => report.mutate("json")}>
              JSON 내려받기
            </Button>
          </div>
        </section>

        <section aria-labelledby="save-pdf" className="flex min-w-0 grow basis-110 flex-col gap-4 rounded-md border border-line bg-white p-6">
          <h2 id="save-pdf" className="text-lg font-bold">
            PDF로 출력
          </h2>
          <ul className="m-0 list-disc pl-4.5 leading-relaxed text-sub">
            <li>표지 · 문서 번호, 제품명, 원본 파일, 검토자, 검토 일시, 2차 판정 개수와 미검토 건수</li>
            <li>고른 항목: 재생성 MSDS, 2항·15항 판정 표, 성분별 요약, 검토 이력</li>
            <li>판정 표에는 처리 상태와 검토자 의견이 함께 나옵니다</li>
          </ul>
          <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
            <legend className="mb-1 text-sm font-medium text-mut">포함할 항목</legend>
            {INCLUDE_ITEMS.map((item) => (
              <Checkbox
                key={item.key}
                label={item.label}
                checked={include[item.key]}
                onChange={(e) => setInclude({ ...include, [item.key]: e.target.checked })}
              />
            ))}
          </fieldset>
          <p className="text-sm text-mut">
            {incomplete && "미검토 판정은 PDF에 \"미검토\"로 표시됩니다. "}원문 PDF는 들어 있지 않습니다. 파일 이름: <span className="whitespace-nowrap">{fileName}</span>
          </p>
          {reportError && (
            <Callout tone="danger" role="alert" className="[word-break:keep-all]">
              리포트를 만들지 못했습니다. {reportError}
            </Callout>
          )}
          <div className="mt-auto flex flex-col gap-2">
            <div className="flex flex-wrap gap-2">
              <Button variant="primary" size="lg" disabled={reporting} aria-busy={reporting} className={DISABLED_BUTTON} onClick={() => report.mutate("pdf")}>
                {reporting && report.variables === "pdf" ? "만드는 중…" : "PDF로 출력"}
              </Button>
              <Button size="lg" disabled={reporting} className={DISABLED_BUTTON} onClick={() => report.mutate("preview")}>
                미리 보기
              </Button>
              <Button size="lg" disabled={reporting} className={DISABLED_BUTTON} onClick={() => report.mutate("html")}>
                리포트 HTML
              </Button>
              <Button size="lg" disabled={reporting} className={DISABLED_BUTTON} onClick={() => report.mutate("xlsx")}>
                리포트 Excel
              </Button>
            </div>
            <p className="text-sm text-mut">미리 보기는 저장하지 않은 최신 판정으로, 나머지는 가장 최근 저장본으로 만듭니다.</p>
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
