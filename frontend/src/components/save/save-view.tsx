"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { ApiRequestError } from "@/api/client";
import { judgmentKeys, judgmentViewQuery } from "@/api/judgment";
import {
  ALL_INCLUDE,
  conflictText,
  postSnapshot,
  requestReport,
  saveOverviewQuery,
  type ReportFormat,
  type ReportInclude,
} from "@/api/judgment-extra";
import { Foot, Row } from "@/components/shell/layout";
import { Button, Skeleton, StatusLabel, buttonStyles } from "@/components/ui";
import { cn } from "@/lib/cn";
import { downloadBlob, openBlob } from "@/lib/download";
import { processedCounts, unreviewedFindings, valuesLabel } from "@/lib/save";
import { useReviewer } from "@/lib/reviewer";
import { routes } from "@/lib/routes";
import { JudgmentError, type JudgmentReady } from "../review/judgment-gate";

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

/** 판정 요약의 칸: [서버 판정 이름, 건수가 0이어도 보이는가]. 참고·범위 외는 있을 때만 */
const SUMMARY = [
  ["불일치", true],
  ["경계", true],
  ["근거부족", true],
  ["경고", true],
  ["일치", true],
  ["참고", false],
  ["범위 외", false],
] as const;

const TONE = { 불일치: "danger", 경계: "warning", 근거부족: "neutral", 경고: "warning", 일치: "success", 참고: "neutral", "범위 외": "neutral" } as const;

/** PDF 에 넣을 항목 (계약 report_request.include) */
const INCLUDE_ITEMS: { key: keyof ReportInclude; label: string }[] = [
  { key: "regenerated_msds", label: "재생성 MSDS" },
  { key: "findings_2", label: "2항 판정 표" },
  { key: "findings_15", label: "15항 판정 표" },
  { key: "components", label: "성분별 요약" },
  { key: "history", label: "검토 이력" },
];

const stem = (filename: string) => filename.replace(/\.pdf$/i, "");
const BUTTON_OFF = "disabled:cursor-not-allowed disabled:border-dashed disabled:border-field-line disabled:bg-line2 disabled:text-mut disabled:opacity-100";
type ReportKind = ReportFormat | "preview";

/** 3.1~3.2 저장. 판정 상태에 따른 안내는 JudgmentGate 가 맡고, 판정이 있을 때만 이 화면을 그린다 */
export function SaveView({ docId, ready }: { docId: string; ready: JudgmentReady }) {
  const reviewer = useReviewer();
  const client = useQueryClient();
  const overviewQuery = useQuery(saveOverviewQuery(docId));
  const view = useQuery(judgmentViewQuery(docId, ready.latest));
  const [include, setInclude] = useState<ReportInclude>(ALL_INCLUDE);
  const { doc } = ready;

  const overview = overviewQuery.data;
  const last = overview?.snapshots[0];
  const baseName = doc.product_name ?? stem(doc.filename);

  const save = useMutation({
    // 화면이 읽은 판정 버전과 함께 저장한다: 더 새 판정이 있거나 아직 판정 중이면 409
    mutationFn: () => postSnapshot(docId, { reviewer, seen_version: overview?.version ?? ready.latest }),
    onSuccess: () => client.invalidateQueries({ queryKey: judgmentKeys.all(docId) }),
    onError: (error) => {
      if (error instanceof ApiRequestError && error.status === 409) void client.invalidateQueries({ queryKey: judgmentKeys.status(docId) });
    },
  });
  const conflict = save.error instanceof ApiRequestError && save.error.status === 409;
  const saved = save.data;

  const report = useMutation({
    mutationFn: async (kind: ReportKind) => {
      // 미리 보기는 저장하지 않은 최신 판정(snapshot_no null)으로, 나머지는 가장 최근 저장본으로 만든다
      const format = kind === "preview" ? "html" : kind;
      const file = await requestReport(docId, { format, snapshot_no: kind === "preview" ? null : (last?.snapshot_no ?? null), include }, baseName);
      if (kind === "preview") {
        if (!openBlob(file.blob)) throw new Error("새 탭이 막혀 미리 보기를 열지 못했습니다. 팝업을 허용해 주세요.");
      } else downloadBlob(file.blob, file.filename);
    },
  });

  if (overviewQuery.isError) return <JudgmentError paneTitle="검토 결과 저장" error={overviewQuery.error} onRetry={() => void overviewQuery.refetch()} />;
  if (!overview || !view.data) return <Skeleton className="w-2/3" />;

  // 처리할 판정은 2항·15항 탭과 같은 규칙으로 센다 (lib/regulation.ts)
  const todo = unreviewedFindings(view.data);
  const { confirmed, exception, total } = processedCounts(overview.reviews);
  const incomplete = todo.length > 0;
  const saving = save.isPending;
  const reporting = report.isPending;
  const values = overview.values;
  const reportError = report.isError ? (report.error instanceof Error ? report.error.message : "리포트를 만들지 못했습니다.") : null;
  const savedNo = (saved ?? last)?.snapshot_no;
  const savedAt = (saved ?? last)?.saved_at;

  const status = saving
    ? { tone: "info" as const, label: "저장 중" }
    : save.isError
      ? { tone: "danger" as const, label: "저장하지 못함" }
      : savedNo
        ? { tone: "success" as const, label: `저장됨 · 저장본 ${savedNo}${incomplete ? " · 미검토 포함" : ""}` }
        : { tone: "neutral" as const, label: "저장 전" };

  return (
    <div className="flex flex-col gap-6 [word-break:keep-all]">
      <section>
        <h1 className="text-2xl font-bold">{incomplete ? "처리하지 않은 판정이 남아 있습니다" : "검토를 마쳤습니다"}</h1>
        <p className="mt-1 text-mut">
          {incomplete
            ? "결과를 데이터베이스에 저장하면 미검토 판정은 그대로 \"미검토\"로 기록되고, PDF에도 같은 표시가 붙습니다."
            : "결과를 데이터베이스에 저장하고, 재생성 MSDS와 판정이 담긴 PDF로 내려받을 수 있습니다."}
        </p>
      </section>

      {ready.pending && (
        <p role="status" className="rounded-sm bg-blue-soft px-4 py-2.5 text-sm text-blue2">
          추출값이 바뀌어 다시 판정하는 중입니다. 판정이 끝날 때까지 저장은 거절됩니다.
        </p>
      )}

      <section aria-label="2차 판정 요약과 처리 상태" className="flex flex-col gap-3 rounded-md border border-line bg-white px-5 py-4">
        <div className="flex flex-wrap items-center gap-x-7 gap-y-2">
          <b>2차 판정 요약</b>
          {SUMMARY.filter(([key, always]) => always || overview.verdicts.total[key] > 0).map(([key]) => (
            <StatusLabel key={key} tone={TONE[key]} className="text-base text-ink">
              {key} {overview.verdicts.total[key]}
            </StatusLabel>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-x-3.5 gap-y-2 border-t border-line2 pt-3">
          <b>처리 상태</b>
          <span className={cn("rounded-sm px-3 py-1 font-bold", incomplete ? "bg-tint text-amb-text" : "bg-grn-soft text-grn")}>미검토 {todo.length}건</span>
          <span className="text-mut">
            처리 {total}건 (확정 {confirmed} · 예외 승인 {exception})
          </span>
          {incomplete && (
            <Link href={routes.review(docId, todo[0].section === "2" ? "hazard" : "regulation", { finding: todo[0].id })} className="px-1.5">
              판정 처리하러 가기 ›
            </Link>
          )}
          <span className="flex-1" />
          <span className={cn("rounded-sm px-3 py-1 font-bold", values.state === "완료" ? "bg-grn-soft text-grn" : "bg-tint text-amb-text")}>{valuesLabel(values.state)}</span>
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
            <dd className="m-0">{reviewer || "—"}</dd>
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
            <p role="status" className="text-sm text-mut">
              저장하는 중입니다…
            </p>
          )}
          {saved && !saving && (
            <p role="status" className="rounded-sm bg-blue-soft px-3.5 py-2.5 text-sm text-blue2">
              <b>
                저장했습니다. 저장본 {saved.snapshot_no}
                {incomplete && ` · 미검토 ${todo.length}건 포함`}
              </b>
              <br />
              포함한 처리 {saved.counts["불일치 확정"] + saved.counts.확인 + saved.counts["예외 승인"]}건 (확정 {saved.counts["불일치 확정"] + saved.counts.확인} · 예외 승인 {saved.counts["예외 승인"]}) · 미검수 칸 {saved.counts["미검수 칸"]}
            </p>
          )}
          {save.isError && !saving && (
            <p role="alert" className="flex flex-wrap items-center gap-2 text-sm break-words text-red">
              <span>
                {conflict
                  ? conflictText(save.error)
                  : `저장하지 못했습니다${save.error instanceof ApiRequestError ? `: ${save.error.message}` : ". 잠시 뒤 다시 시도해 주세요."}`}
              </span>
              {conflict ? (
                <Button
                  onClick={() => {
                    save.reset();
                    void client.invalidateQueries({ queryKey: judgmentKeys.all(docId) });
                  }}
                >
                  새로고침
                </Button>
              ) : (
                <Button onClick={() => save.mutate()}>다시 시도</Button>
              )}
            </p>
          )}
          {!reviewer && <p className="text-sm text-mut">저장하려면 머리줄에서 검토자 이름을 정해 주세요.</p>}

          <div className="mt-auto flex flex-wrap gap-2">
            <Button variant="primary" size="lg" disabled={saving || !reviewer} aria-busy={saving} onClick={() => save.mutate()}>
              {saving ? "저장 중…" : savedNo ? "다시 저장하기" : "저장하기"}
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
              <label key={item.key} className="flex items-center gap-2">
                <input type="checkbox" checked={include[item.key]} onChange={(e) => setInclude({ ...include, [item.key]: e.target.checked })} />
                {item.label}
              </label>
            ))}
          </fieldset>
          <p className="text-sm text-mut">
            {incomplete && "미검토 판정은 PDF에 \"미검토\"로 표시됩니다. "}원문 PDF는 들어 있지 않습니다. 파일 이름: <span className="whitespace-nowrap">{baseName}_MSDS_검토결과.pdf</span>
          </p>
          {reportError && (
            <p role="alert" className="rounded-sm bg-red-soft px-3 py-2 text-sm break-words text-red">
              리포트를 만들지 못했습니다. {reportError}
            </p>
          )}
          <div className="mt-auto flex flex-col gap-2">
            <div className="flex flex-wrap gap-2">
              <Button variant="primary" size="lg" disabled={reporting} aria-busy={reporting} className={BUTTON_OFF} onClick={() => report.mutate("pdf")}>
                {reporting && report.variables === "pdf" ? "만드는 중…" : "PDF로 출력"}
              </Button>
              <Button size="lg" disabled={reporting} className={BUTTON_OFF} onClick={() => report.mutate("preview")}>
                미리 보기
              </Button>
              <Button size="lg" disabled={reporting} className={BUTTON_OFF} onClick={() => report.mutate("html")}>
                리포트 HTML
              </Button>
              <Button size="lg" disabled={reporting} className={BUTTON_OFF} onClick={() => report.mutate("xlsx")}>
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
            판정으로 돌아가기
          </Link>
        </div>
        <Link href={routes.home()} className={buttonStyles({ size: "lg" })}>
          목록으로
        </Link>
      </Foot>
    </div>
  );
}
