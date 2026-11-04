"use client";

/*
 * 3.1~3.2 저장 화면. 판정이 있을 때만 그린다 (판정 상태 안내는 JudgmentGate).
 * 재료는 save-overview 한 번, 저장은 snapshots 에 한 줄을 더한다. 화면은 건수를 새로 계산하지 않는다 (lib/save).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { ApiContractError, ApiRequestError } from "@/api/client";
import { isVersionConflict, judgmentKeys } from "@/api/judgment";
import { fetchReport, postSnapshot, saveOverviewQuery, type ReportInclude, type SaveOverview } from "@/api/save";
import type { DocumentDetail } from "@/api/schemas";
import { JudgmentError, JudgmentGate } from "@/components/review/judgment-gate";
import { Foot, Pane, Row } from "@/components/shell/layout";
import { Button, Card, Skeleton, StatusLabel, Table, TableHead, buttonStyles, dotStyles } from "@/components/ui";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";
import { useReviewer } from "@/lib/reviewer";
import { routes } from "@/lib/routes";
import {
  REPORT_PARTS,
  headline,
  processedText,
  reportFileName,
  reportInclude,
  saveState,
  valueRows,
  verdictSummary,
  type SaveState,
} from "@/lib/save";

const PANE_TITLE = "검토 결과 저장";

export function SaveBody({ docId }: { docId: string }) {
  return (
    <JudgmentGate docId={docId} tab="hazard" paneTitle={PANE_TITLE} what="저장할 판정" loading={() => <LoadingBody />}>
      {(ready) => <SaveReady docId={docId} doc={ready.doc} />}
    </JudgmentGate>
  );
}

function SaveReady({ docId, doc }: { docId: string; doc: DocumentDetail }) {
  const overview = useQuery(saveOverviewQuery(docId));
  if (overview.isPending) return <LoadingBody />;
  if (!overview.data) return <JudgmentError paneTitle={PANE_TITLE} error={overview.error} onRetry={() => void overview.refetch()} />;
  return <SaveLoaded docId={docId} doc={doc} ov={overview.data} />;
}

function SaveLoaded({ docId, doc, ov }: { docId: string; doc: DocumentDetail; ov: SaveOverview }) {
  const state = saveState(ov);
  const { title, body } = headline(ov);
  const unreviewed = ov.reviews.미검토;
  return (
    <div className="flex flex-col gap-5">
      <section>
        <h1 className="text-2xl font-bold">{title}</h1>
        <p className="mt-1 text-mut">{body}</p>
      </section>

      <SummaryCard docId={docId} ov={ov} />

      <Row className="items-stretch">
        <DatabaseCard docId={docId} doc={doc} ov={ov} state={state} />
        <PdfCard docId={docId} doc={doc} state={state} />
      </Row>

      <Foot>
        <div className="flex flex-wrap gap-2">
          <Link href={routes.review(docId)} className={buttonStyles({ size: "lg" })}>
            판정으로 돌아가기
          </Link>
          {unreviewed > 0 && (
            <Link href={routes.review(docId, "history")} className={buttonStyles({ size: "lg" })}>
              판정 처리하러 가기
            </Link>
          )}
        </div>
        <Link href={routes.home()} className={buttonStyles({ size: "lg" })}>
          목록으로
        </Link>
      </Foot>
    </div>
  );
}

const VALUES_CHIP: Record<SaveOverview["values"]["state"], { text: string; className: string }> = {
  완료: { text: "추출값 확인함", className: "bg-grn-soft text-grn" },
  일부: { text: "추출값 일부 확인", className: "bg-tint text-amb-text" },
  미검수: { text: "추출값 미검수", className: "bg-tint text-amb-text" },
};

/** 2차 판정 요약과 처리 상태. 판정·처리 건수는 서버(save-overview)가 센 값이다 */
function SummaryCard({ docId, ov }: { docId: string; ov: SaveOverview }) {
  const unreviewed = ov.reviews.미검토;
  const chip = VALUES_CHIP[ov.values.state];
  return (
    <Card className="flex flex-col gap-0 py-3">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-line2 pb-3">
        <h2 className="text-base font-bold">2차 판정 요약</h2>
        <ul className="flex flex-wrap gap-x-5 gap-y-1" aria-label="2차 판정 건수">
          {verdictSummary(ov.verdicts.total).map((v) => (
            <li key={v.verdict} className="inline-flex items-center gap-1.5 text-sm">
              <span className={dotStyles({ tone: v.tone })} aria-hidden="true" />
              {v.verdict} <span className="tabular-nums">{v.count}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 pt-3">
        <h2 className="text-base font-bold">처리 상태</h2>
        <span className={cn("rounded-sm px-3 py-1 text-sm font-bold", unreviewed ? "bg-tint text-amb-text" : "bg-grn-soft text-grn")}>
          미검토 {unreviewed}건
        </span>
        <span className="text-sm text-mut">{processedText(ov.reviews)}</span>
        {unreviewed > 0 && (
          <Link href={routes.review(docId, "history")} className="text-sm font-medium text-blue2">
            판정 처리하러 가기 ›
          </Link>
        )}
        <span className={cn("ml-auto rounded-sm px-3 py-1 text-sm font-bold", chip.className)}>{chip.text}</span>
      </div>
    </Card>
  );
}

function errorText(error: unknown) {
  if (isVersionConflict(error)) return `${error.message}. 최신 판정을 다시 받았으니 확인한 뒤 저장해 주세요.`;
  if (error instanceof ApiContractError) return "서버 응답이 화면 약속과 달라 결과를 확인하지 못했습니다. 개발 담당에게 알려 주세요.";
  if (error instanceof ApiRequestError) return error.message;
  return "서버에 연결하지 못했습니다. 연결을 확인해 주세요.";
}

function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

/** 저장본이 지금 내용과 같으면 그 저장본으로, 아니면 지금 판정으로 만든다 (저장 전 미리 보기) */
const reportSnapshot = (state: SaveState) => (state.kind === "current" ? state.snapshot.snapshot_no : null);

function DatabaseCard({ docId, doc, ov, state }: { docId: string; doc: DocumentDetail; ov: SaveOverview; state: SaveState }) {
  const client = useQueryClient();
  const reviewer = useReviewer();
  const save = useMutation({
    mutationFn: () => postSnapshot(docId, { reviewer, seen_version: ov.version, note: null }),
    // 저장 화면 건수·판정 상태(등급, 저장 번호)를 함께 다시 받는다
    onSettled: () => client.invalidateQueries({ queryKey: judgmentKeys.all(docId) }),
  });
  const json = useMutation({
    mutationFn: async () => {
      const include: ReportInclude = reportInclude({});
      const { blob, disposition } = await fetchReport(docId, "json", include, reportSnapshot(state));
      download(blob, reportFileName(disposition, doc.filename, "json"));
    },
  });

  const snap = state.kind === "none" ? null : state.snapshot;
  const status =
    state.kind === "none" ? (
      <StatusLabel>아직 저장하지 않음</StatusLabel>
    ) : state.kind === "changed" ? (
      <StatusLabel tone="warning">저장 뒤 바뀜</StatusLabel>
    ) : state.snapshot.counts.미검토 > 0 ? (
      <StatusLabel tone="warning">저장됨 · 미검토 포함</StatusLabel>
    ) : (
      <StatusLabel tone="success">저장됨</StatusLabel>
    );

  return (
    <Pane title="데이터베이스에 저장" aside={status} className="basis-105">
      <dl className="grid grid-cols-[6rem_1fr] gap-x-4 gap-y-1.5 text-sm">
        <dt className="text-mut">저장 시각</dt>
        <dd>{snap ? formatDateTime(snap.saved_at) : "—"}</dd>
        <dt className="text-mut">저장한 사람</dt>
        <dd>{snap?.saved_by ?? "—"}</dd>
        <dt className="text-mut">저장본</dt>
        <dd>{snap ? `${snap.snapshot_no}번째 저장` : "—"}</dd>
        <dt className="text-mut">저장 내용</dt>
        <dd>최종 값, 값의 출처, 2차 판정, 처리 상태, 의견</dd>
      </dl>

      <Table>
        <TableHead>
          <div className="flex-1">값의 출처</div>
          <div className="w-16 text-right">칸 수</div>
        </TableHead>
        {valueRows(ov.values).map((r) => (
          <div key={r.label} className="flex items-center gap-3 border-b border-line2 px-4 py-2.5 last:border-b-0">
            <div className="flex-1">{r.label}</div>
            <div className="w-16 text-right tabular-nums">{r.count}</div>
          </div>
        ))}
      </Table>

      <p className="text-sm text-mut">
        수정한 칸은 고친 값으로 저장되고, 고치기 전 값은 추출 원본에 남습니다. 다시 저장하면 새 번호로 쌓이며 이전 저장본은 그대로 남습니다.
      </p>

      <div className="mt-auto flex flex-wrap gap-2">
        <Button variant="primary" disabled={!reviewer || save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? "저장하는 중…" : state.kind === "none" ? "저장하기" : "다시 저장하기"}
        </Button>
        <Button disabled={json.isPending} onClick={() => json.mutate()}>
          {json.isPending ? "만드는 중…" : "JSON 내려받기"}
        </Button>
      </div>
      {!reviewer && <p className="text-sm text-mut">저장하려면 머리줄에서 검토자 이름을 정해 주세요.</p>}
      {save.isSuccess && !save.isPending && (
        <p role="status" className="text-sm text-grn">
          {save.data.snapshot_no}번째 저장본을 남겼습니다.
        </p>
      )}
      {save.isError && (
        <p role="alert" className="text-sm break-words text-red">
          저장하지 못했습니다. {errorText(save.error)}
        </p>
      )}
      {json.isError && (
        <p role="alert" className="text-sm break-words text-red">
          JSON을 만들지 못했습니다. {errorText(json.error)}
        </p>
      )}
    </Pane>
  );
}

function PdfCard({ docId, doc, state }: { docId: string; doc: DocumentDetail; state: SaveState }) {
  const [picked, setPicked] = useState<Partial<Record<keyof ReportInclude, boolean>>>(() =>
    Object.fromEntries(REPORT_PARTS.map((p) => [p.key, true])),
  );
  const include = reportInclude(picked);
  const snapshotNo = reportSnapshot(state);

  const pdf = useMutation({
    mutationFn: async () => {
      const { blob, disposition } = await fetchReport(docId, "pdf", include, snapshotNo);
      download(blob, reportFileName(disposition, doc.filename, "pdf"));
    },
  });
  const preview = useMutation({
    // 창은 누른 순간에 열어야 막히지 않는다. 받은 뒤 주소만 바꾼다
    mutationFn: async (win: Window | null) => {
      try {
        const { blob } = await fetchReport(docId, "html", include, snapshotNo);
        const url = URL.createObjectURL(blob);
        if (win) win.location.href = url;
        else window.open(url, "_blank");
        setTimeout(() => URL.revokeObjectURL(url), 60_000);
      } catch (error) {
        win?.close();
        throw error;
      }
    },
  });

  return (
    <Pane title="PDF로 출력" className="basis-105">
      <ul className="list-disc pl-5 text-sm">
        <li>표지 · 문서 번호, 제품명, 원본 파일, 기준일, 판정 개수와 미검토 건수</li>
      </ul>
      <fieldset className="flex flex-col gap-2">
        <legend className="sr-only">PDF에 넣을 항목</legend>
        {REPORT_PARTS.map((p) => (
          <label key={p.key} className="flex items-start gap-2.5 text-sm">
            <input
              type="checkbox"
              className="mt-0.5 size-4 accent-blue"
              checked={!!picked[p.key]}
              onChange={(e) => setPicked((prev) => ({ ...prev, [p.key]: e.target.checked }))}
            />
            <span>
              <span className="font-medium">{p.label}</span>
              <span className="text-mut"> · {p.note}</span>
            </span>
          </label>
        ))}
      </fieldset>
      <p className="text-sm text-mut">
        {snapshotNo
          ? `${snapshotNo}번째 저장본으로 만듭니다.`
          : `${state.kind === "none" ? "아직 저장하지 않아" : "저장본이 지금 내용과 달라"} 지금 판정으로 만듭니다. 표지에 "저장 전 미리 보기"로 표시됩니다.`}{" "}
        원문 PDF는 들어 있지 않습니다.
      </p>
      <div className="mt-auto flex flex-wrap gap-2">
        <Button variant="primary" disabled={pdf.isPending} onClick={() => pdf.mutate()}>
          {pdf.isPending ? "만드는 중…" : "PDF로 출력"}
        </Button>
        <Button disabled={preview.isPending} onClick={() => preview.mutate(window.open("", "_blank"))}>
          미리 보기
        </Button>
      </div>
      {(pdf.isError || preview.isError) && (
        <p role="alert" className="text-sm break-words text-red">
          리포트를 만들지 못했습니다. {errorText(pdf.error ?? preview.error)}
        </p>
      )}
    </Pane>
  );
}

function LoadingBody() {
  return (
    <div className="flex flex-col gap-5">
      <section className="flex flex-col gap-2">
        <Skeleton className="h-7 w-64" />
        <Skeleton className="w-96" />
      </section>
      <Card>
        <Skeleton className="w-2/3" />
      </Card>
      <Row className="items-stretch">
        <Pane title="데이터베이스에 저장" className="basis-105">
          <Skeleton className="w-full" />
          <Skeleton className="w-4/5" />
        </Pane>
        <Pane title="PDF로 출력" className="basis-105">
          <Skeleton className="w-full" />
          <Skeleton className="w-3/5" />
        </Pane>
      </Row>
    </div>
  );
}
