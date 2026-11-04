"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { ApiContractError, ApiRequestError } from "@/api/client";
import { documentDetailQuery } from "@/api/documents";
import { judgmentHistoryQuery, valuesLogQuery, type HistoryEntry } from "@/api/history";
import { isJudgmentApiMissing, judgmentStatusQuery, judgmentViewQuery } from "@/api/judgment";
import { Foot, Pane } from "@/components/shell/layout";
import { Button, PillTabs, Skeleton, Table, TableHead, buttonStyles, dotStyles } from "@/components/ui";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";
import { filterHistory, historyPills, kindOf, KIND_LABEL, linkOf, mergeHistory, type HistoryKind } from "@/lib/history";
import { isMatch, unreviewedFindings, verdictTone } from "@/lib/regulation";
import { routes } from "@/lib/routes";

const PAGE_SIZE = 100;
const DEV = process.env.NODE_ENV === "development";

const hrefOf = (doc: string, entry: HistoryEntry) => {
  const link = linkOf(entry);
  if (!link) return null;
  if ("save" in link) return routes.save(doc);
  return routes.review(doc, link.tab, link.finding ? { finding: link.finding, msds: String(link.msds ?? 0) } : undefined);
};

/** 탭: 처리하지 않은 판정 + 추출값·판정 이력을 합친 표 */
export function HistoryTab({ docId, onSave }: { docId: string; onSave: (unreviewed: number) => void }) {
  const { data: doc } = useQuery(documentDetailQuery(docId));
  const done = doc?.status === "done";
  const status = useQuery({ ...judgmentStatusQuery(docId), enabled: done });
  const latest = status.data?.state === "판정 있음" ? status.data.latest_version : null;
  const view = useQuery({ ...judgmentViewQuery(docId, latest ?? 0), enabled: latest !== null });
  const log = useQuery({ ...valuesLogQuery(docId), enabled: done });
  const judged = useQuery({ ...judgmentHistoryQuery(docId), enabled: done });

  if (!doc || (done && (log.isPending || judged.isPending || status.isPending))) return <LoadingBody />;
  if (!done) {
    return (
      <Pane title="검토 이력">
        <p className="text-mut">추출이 끝나면 검토 이력을 볼 수 있습니다.</p>
        <div>
          <Link href={routes.extract(docId)} className={buttonStyles()}>
            추출 진행 보기
          </Link>
        </div>
      </Pane>
    );
  }

  const nothingConnected = isJudgmentApiMissing(log.error) && isJudgmentApiMissing(judged.error) && isJudgmentApiMissing(status.error);
  if (nothingConnected) {
    return (
      <Pane title="검토 이력">
        <div role="status" className="flex flex-col items-center gap-3 py-10 text-center">
          <h3 className="text-lg font-bold">검토 이력 서비스가 아직 연결되지 않았습니다</h3>
          <p className="text-mut">
            기록이 없다는 뜻이 아닙니다. 추출값 확인·수정 기록은 서버에 쌓이고 있고, 연결되면 이 화면에 나타납니다.
          </p>
          <div className="flex flex-wrap justify-center gap-2">
            <Link href={routes.review(docId, "values")} className={buttonStyles()}>
              추출값 확인
            </Link>
            {DEV && (
              <Link href={`${routes.review(docId, "history")}&judgmentMock=ready`} className={buttonStyles({ variant: "outline" })}>
                개발용 가상 이력 보기
              </Link>
            )}
          </div>
        </div>
      </Pane>
    );
  }

  const unreviewed = view.data ? unreviewedFindings(view.data) : null;

  return (
    <div className="flex flex-col gap-5">
      <UnreviewedSection docId={docId} status={status} view={view} />
      <HistoryTable docId={docId} log={log} judged={judged} />
      <Foot>
        <p className="text-mut">확인하지 않은 추출값은 저장 결과에 &quot;미검수&quot;로 남습니다.</p>
        <div className="flex flex-wrap gap-2">
          <Link href={routes.review(docId, "values")} className={buttonStyles({ size: "lg" })}>
            추출값 확인하러 가기
          </Link>
          {/* 처리할 판정 수를 모르면 저장 전 경고를 띄울 수 없으므로 저장하지 않는다 */}
          <Button
            variant="primary"
            size="lg"
            disabled={unreviewed === null}
            title={unreviewed === null ? "판정 결과를 받은 뒤 저장할 수 있습니다" : undefined}
            onClick={() => onSave(unreviewed?.length ?? 0)}
          >
            저장하기
          </Button>
        </div>
      </Foot>
    </div>
  );
}

function UnreviewedSection({
  docId,
  status,
  view,
}: {
  docId: string;
  status: UseQueryResult<{ state: string; error?: string | null }>;
  view: UseQueryResult<import("@/api/judgment").JudgmentView>;
}) {
  const box = (title: string, body?: React.ReactNode, tone?: "alert") => (
    <section className="flex flex-col gap-2.5 rounded-lg border border-line bg-white px-5 py-4" role={tone === "alert" ? "alert" : undefined}>
      <h2 className="text-base font-bold">{title}</h2>
      {body}
    </section>
  );

  if (status.isError && !status.data) {
    if (isJudgmentApiMissing(status.error)) {
      return box("처리하지 않은 판정", <p className="text-sm text-mut">판정 서비스가 아직 연결되지 않아 처리할 판정을 알 수 없습니다.</p>);
    }
    return box("처리하지 않은 판정을 불러오지 못했습니다", <RetryLine error={status.error} onRetry={() => void status.refetch()} />, "alert");
  }
  const state = status.data?.state;
  if (state === "판정 없음") return box("아직 판정하지 않았습니다", <p className="text-sm text-mut">판정이 끝나면 처리할 항목이 여기에 나타납니다.</p>);
  if (state === "판정 중") return box("판정하는 중입니다", <Skeleton className="w-2/3" />);
  if (state === "판정 실패") return box("판정하지 못했습니다", <p className="text-sm break-words text-mut">문서 {docId}{status.data?.error && ` · ${status.data.error}`}</p>, "alert");
  if (view.isPending) return box("처리하지 않은 판정", <Skeleton className="w-2/3" />);
  if (!view.data) return box("처리하지 않은 판정을 불러오지 못했습니다", <RetryLine error={view.error} onRetry={() => void view.refetch()} />, "alert");

  const rows = unreviewedFindings(view.data);
  const all = view.data.consistency.results.flatMap((r) => r.findings);
  const matches = all.filter(isMatch).length;
  const multi = view.data.consistency.results.length > 1;
  return box(
    rows.length ? `아직 처리하지 않은 판정 ${rows.length}건` : "처리할 판정이 없습니다",
    <>
      <p className="text-sm text-mut">
        {rows.length ? "불일치·경계·근거부족·경고는 불일치 확정이나 예외 승인으로 처리합니다. " : ""}일치 {matches}건은 처리하지 않아도 됩니다.
      </p>
      {rows.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {rows.map((f) => {
            const msds = /^m(\d+)\//.exec(f.id)?.[1] ?? "0";
            const stale = view.data.reviews[f.id]?.stale;
            return (
              <Link
                key={f.id}
                href={routes.review(docId, f.section === "2" ? "hazard" : "regulation", { finding: f.id, msds })}
                className="inline-flex items-center gap-1.5 rounded-sm border border-line bg-white px-3 py-1.5 text-ink no-underline"
              >
                <span className={dotStyles({ tone: verdictTone(f) })} aria-hidden="true" />
                {multi && <span className="text-mut">MSDS {Number(msds) + 1}</span>}
                {f.label}
                <span className="text-mut">· {stale ? "다시 확인 필요" : f.verdict}</span>
              </Link>
            );
          })}
        </div>
      )}
    </>,
  );
}

function RetryLine({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const message =
    error instanceof ApiContractError
      ? "응답이 화면 약속과 달라 표시하지 않았습니다."
      : error instanceof ApiRequestError
        ? error.message
        : "서버에 연결하지 못했습니다.";
  return (
    <div className="flex flex-wrap items-center gap-3 text-sm">
      <span className="break-words text-red">{message}</span>
      <Button onClick={onRetry}>다시 불러오기</Button>
    </div>
  );
}

type Source = { name: string; query: UseQueryResult<HistoryEntry[]> };

function HistoryTable({
  docId,
  log,
  judged,
}: {
  docId: string;
  log: UseQueryResult<HistoryEntry[]>;
  judged: UseQueryResult<HistoryEntry[]>;
}) {
  const [kind, setKind] = useState<HistoryKind>("all");
  const [limit, setLimit] = useState(PAGE_SIZE);
  const sources: Source[] = [
    { name: "추출값", query: log },
    { name: "판정", query: judged },
  ];
  const entries = mergeHistory(log.data ?? [], judged.data ?? []);
  const missing = sources.filter((s) => !s.query.data && isJudgmentApiMissing(s.query.error));
  const failed = sources.filter((s) => s.query.isError && !isJudgmentApiMissing(s.query.error));
  // 받지 못한 쪽이 있으면 0건을 "기록 없음"으로 말하지 않는다
  const complete = !missing.length && !failed.length;
  const shown = filterHistory(entries, kind);
  const pills = historyPills(entries);
  // 고른 구분의 기록이 다시 받으며 사라지면 전체로 돌아간다
  const activeKind = pills.some((p) => p.id === kind) ? kind : "all";

  return (
    <section className="flex flex-col gap-3" aria-label="검토 이력">
      {missing.length > 0 && (
        <p role="status" className="rounded-md border border-amb bg-tint px-4 py-2.5 text-sm text-amb-text">
          {missing.map((s) => s.name).join("·")} 이력은 아직 연결되지 않아 아래 표와 건수에 포함되지 않았습니다.
        </p>
      )}
      {failed.map((s) => (
        <div key={s.name} role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-white px-4 py-2.5">
          <span className="text-sm font-medium">{s.name} 이력</span>
          <RetryLine error={s.query.error} onRetry={() => void s.query.refetch()} />
        </div>
      ))}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PillTabs
          label="이력 구분"
          value={activeKind}
          onChange={(id) => {
            setKind(id as HistoryKind);
            setLimit(PAGE_SIZE);
          }}
          items={pills}
        />
        <span className="text-sm text-mut">최근 처리가 위로 옵니다</span>
      </div>
      <Table>
        <TableHead className="max-lg:hidden">
          <div className="w-44 flex-none">시각</div>
          <div className="w-20 flex-none">검토자</div>
          <div className="w-24 flex-none">구분</div>
          <div className="flex-[2_1_0]">대상</div>
          <div className="flex-[3_1_0]">처리 내용</div>
          <div className="flex-[3_1_0]">의견</div>
          <div className="w-14 flex-none" />
        </TableHead>
        {(activeKind === kind ? shown : entries).slice(0, limit).map((entry, i) => (
          <HistoryRow key={`${entry.at}-${entry.target}-${entry.action}-${i}`} docId={docId} entry={entry} />
        ))}
        {!entries.length && (
          <p className="px-4 py-8 text-center text-mut">
            {complete ? "아직 처리한 기록이 없습니다." : "연결된 이력에는 아직 기록이 없습니다."}
          </p>
        )}
      </Table>
      {shown.length > limit && (
        <div>
          <Button onClick={() => setLimit((n) => n + PAGE_SIZE)}>더 보기 ({shown.length - limit}건 남음)</Button>
        </div>
      )}
    </section>
  );
}

function HistoryRow({ docId, entry }: { docId: string; entry: HistoryEntry }) {
  const href = hrefOf(docId, entry);
  const label = entry.area === "추출값" || entry.area === "저장" ? KIND_LABEL[kindOf(entry)] : `${KIND_LABEL.judgment} · ${entry.area}`;
  return (
    <div className="flex items-start gap-3 border-b border-line2 px-4 py-2.5 last:border-b-0 max-lg:flex-wrap">
      <time dateTime={entry.at} className="w-44 flex-none text-sm text-mut">
        {formatDateTime(entry.at)}
      </time>
      <div className="w-20 flex-none break-words">{entry.reviewer}</div>
      <div className="w-24 flex-none font-medium max-lg:w-auto">{label}</div>
      <div className="min-w-0 flex-[2_1_0] font-medium break-words max-lg:basis-full">{entry.target}</div>
      <div className="min-w-0 flex-[3_1_0] break-words max-lg:basis-full">
        <span className="font-medium">{entry.action}</span>
        {entry.detail && <span className="text-mut"> · {entry.detail}</span>}
      </div>
      <div className={cn("min-w-0 flex-[3_1_0] break-words text-mut max-lg:basis-full", !entry.comment && "max-lg:hidden")}>{entry.comment ?? "—"}</div>
      <div className="w-14 flex-none">
        {href && (
          <Link href={href} aria-label={`${entry.target}(으)로 이동`} className="text-blue2">
            이동 ›
          </Link>
        )}
      </div>
    </div>
  );
}

function LoadingBody() {
  return (
    <div className="flex flex-col gap-5">
      <Pane title="처리하지 않은 판정">
        <Skeleton className="w-2/3" />
      </Pane>
      <Pane title="검토 이력">
        <Skeleton className="w-full" />
        <Skeleton className="w-full" />
        <Skeleton className="w-4/5" />
      </Pane>
    </div>
  );
}
