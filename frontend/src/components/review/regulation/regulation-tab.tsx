"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useState } from "react";
import { ApiContractError, ApiRequestError } from "@/api/client";
import { documentDetailQuery } from "@/api/documents";
import type { DocumentDetail } from "@/api/schemas";
import {
  isJudgmentApiMissing,
  judgmentKeys,
  judgmentStatusQuery,
  judgmentViewQuery,
  postToJudgment,
  type Finding,
  type JudgmentStatus,
  type JudgmentView,
} from "@/api/judgment";
import { SourceViewer } from "@/components/extract/source-viewer";
import { Foot, Pane } from "@/components/shell/layout";
import { Button, Skeleton, buttonStyles } from "@/components/ui";
import { useObservedHeight } from "@/hooks/use-observed-height";
import { defaultFindingId, nextUnreviewedId, regulationCounts, regulationFindings } from "@/lib/regulation";
import { useReviewer } from "@/lib/reviewer";
import { routes } from "@/lib/routes";
import { RegulationDetail, type LockReason } from "./regulation-detail";
import { RegulationTable } from "./regulation-table";

/** 처음 켤 때만 쓰는 대역 안내 링크. 제품 빌드에서는 조건이 거짓이라 빠진다 */
const DEV = process.env.NODE_ENV === "development";

/** 고른 판정·법령 거르기·쪽은 주소에 둔다. 새로 고치거나 검토 이력에서 바로 와도 같은 화면이 나온다 */
function useRegulationParams() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const query = params.toString();
  const update = useCallback(
    (patch: Record<string, string | null>) => {
      const q = new URLSearchParams(query);
      for (const [key, value] of Object.entries(patch)) {
        if (value === null) q.delete(key);
        else q.set(key, value);
      }
      router.replace(`${pathname}?${q.toString()}`, { scroll: false });
    },
    [router, pathname, query],
  );
  return {
    finding: params.get("finding"),
    law: params.get("law"),
    todoOnly: params.get("todo") === "1",
    msds: Math.max(0, Number(params.get("msds")) || 0),
    page: params.has("page") ? Math.max(1, Number(params.get("page")) || 1) : null,
    update,
  };
}

export function RegulationTab({
  docId,
  drafts,
  onDraft,
  onSave,
}: {
  docId: string;
  drafts: Record<string, string>;
  onDraft: (findingId: string, text: string) => void;
  /** 저장으로 간다. 미처리 수를 넘겨 경고를 띄울지 화면이 정한다 */
  onSave: (unreviewed: number) => void;
}) {
  const { data: doc } = useQuery(documentDetailQuery(docId));
  const status = useQuery({ ...judgmentStatusQuery(docId), enabled: doc?.status === "done" });

  if (!doc || (doc.status === "done" && status.isPending)) return <LoadingBody />;
  if (doc.status !== "done") {
    return (
      <Notice title="추출이 끝나야 판정할 수 있습니다">
        <Link href={routes.extract(docId)} className={buttonStyles()}>
          추출 진행 보기
        </Link>
      </Notice>
    );
  }
  if (status.isError && !status.data) {
    if (isJudgmentApiMissing(status.error)) return <NotConnected docId={docId} />;
    return <ErrorBody error={status.error} onRetry={() => void status.refetch()} />;
  }
  const data = status.data as JudgmentStatus;

  if (data.state === "판정 없음") return <StartJudgment docId={docId} />;
  if (data.state === "판정 중") return <LoadingBody message="판정하는 중입니다. 끝나면 이 자리에 나타납니다." />;
  if (data.state === "판정 실패" || data.latest_version === null) {
    return (
      <Notice title="판정하지 못했습니다" alert>
        <p className="break-words text-mut">
          문서 {docId}
          {data.error && ` · ${data.error}`}
        </p>
        <p className="text-mut">다시 불러와도 같으면 개발 담당에게 위 내용을 알려 주세요.</p>
        <Button onClick={() => void status.refetch()}>다시 불러오기</Button>
      </Notice>
    );
  }
  return (
    <RegulationReady
      docId={docId}
      doc={doc}
      latest={data.latest_version}
      pending={data.pending_handoff !== null}
      offline={status.isRefetchError}
      drafts={drafts}
      onDraft={onDraft}
      onSave={onSave}
    />
  );
}

function RegulationReady({
  docId,
  doc,
  latest,
  pending,
  offline,
  drafts,
  onDraft,
  onSave,
}: {
  docId: string;
  doc: DocumentDetail;
  latest: number;
  pending: boolean;
  offline: boolean;
  drafts: Record<string, string>;
  onDraft: (findingId: string, text: string) => void;
  onSave: (unreviewed: number) => void;
}) {
  // 처음 본 버전에 고정한다. 새 버전이 생겨도 사용자가 고르기 전에는 읽던 표를 바꾸지 않는다
  const [version, setVersion] = useState(latest);
  const view = useQuery(judgmentViewQuery(docId, version));

  if (view.isPending) return <LoadingBody />;
  if (view.isError && !view.data) return <ErrorBody error={view.error} onRetry={() => void view.refetch()} />;
  return (
    <RegulationLoaded
      docId={docId}
      doc={doc}
      data={view.data!}
      version={version}
      latest={latest}
      pending={pending}
      offline={offline || view.isRefetchError}
      onNewest={() => setVersion(latest)}
      drafts={drafts}
      onDraft={onDraft}
      onSave={onSave}
    />
  );
}

/** 판정을 받은 뒤에 그린다. 상세 칸 높이를 재는 훅이 그 칸이 생긴 뒤에 붙도록 나눠 둔다 */
function RegulationLoaded({
  docId,
  doc,
  data,
  version,
  latest,
  pending,
  offline,
  onNewest,
  drafts,
  onDraft,
  onSave,
}: {
  docId: string;
  doc: DocumentDetail;
  data: JudgmentView;
  version: number;
  latest: number;
  pending: boolean;
  offline: boolean;
  onNewest: () => void;
  drafts: Record<string, string>;
  onDraft: (findingId: string, text: string) => void;
  onSave: (unreviewed: number) => void;
}) {
  const params = useRegulationParams();
  const details = useObservedHeight<HTMLDivElement>();

  const results = data.consistency.results;
  const msdsIndex = results.some((r) => r.msds_index === params.msds) ? params.msds : results[0].msds_index;
  const findings = regulationFindings(data, msdsIndex);
  const selected =
    findings.find((f) => f.id === params.finding) ??
    findings.find((f) => f.id === defaultFindingId(findings, data.reviews)) ??
    null;
  const display = selected ? data.display[selected.id] : null;
  const firstPage = doc.sections.find((s) => s.msds_index === msdsIndex && s.section === 15)?.pages[0] ?? 1;
  const findingPage = display?.source_pages[0]?.page ?? firstPage;
  const page = params.page ?? findingPage;
  const highlight = selected?.msds.evidence?.[0]?.source_text ?? null;
  const absentInSource = !!selected && !selected.msds.present;

  const newer = version < latest;
  const lock: LockReason = pending ? "rerun" : newer ? "new" : offline ? "offline" : null;
  const hidden = !!selected && !!params.law && selected.law_label !== params.law;
  const counts = regulationCounts(findings, data.reviews);
  const nextId = nextUnreviewedId(findings, data.reviews, selected?.id ?? null);

  const select = (f: Finding | string) => {
    const target = typeof f === "string" ? findings.find((x) => x.id === f) : f;
    if (!target) return;
    params.update({ finding: target.id, page: String(data.display[target.id]?.source_pages[0]?.page ?? firstPage) });
  };

  return (
    <div className="flex flex-col gap-5">
      {pending && (
        <p role="status" className="rounded-sm bg-blue-soft px-4 py-2.5 text-sm text-blue2">
          추출값이 바뀌어 다시 판정하는 중입니다. 아래는 이전 판정이며 처리는 잠시 잠급니다.
        </p>
      )}
      {!pending && newer && (
        <div role="status" className="flex flex-wrap items-center justify-between gap-3 rounded-sm border border-amb bg-tint px-4 py-2.5 text-sm text-amb-text">
          <span>새 판정이 있습니다. 쓰던 의견은 그대로 남습니다.</span>
          <Button onClick={onNewest}>새 판정 보기</Button>
        </div>
      )}
      {lock === "offline" && (
        <p role="status" className="rounded-sm border border-amb bg-tint px-4 py-2.5 text-sm text-amb-text">
          서버와 연결이 끊겼습니다. 아래는 마지막으로 받은 내용입니다.
        </p>
      )}
      {results.length > 1 && (
        <div role="group" aria-label="MSDS 선택" className="flex flex-wrap gap-2">
          {results.map((r) => (
            <Button
              key={r.msds_index}
              variant={r.msds_index === msdsIndex ? "primary" : "default"}
              onClick={() => params.update({ msds: String(r.msds_index), finding: null, law: null, page: null })}
            >
              MSDS {r.msds_index + 1}
            </Button>
          ))}
        </div>
      )}
      <p className="text-sm text-mut">
        지식 {data.consistency.knowledge.provider} / {data.consistency.knowledge.version} · 판정 버전 {data.version}
        {newer && ` (최신 ${latest})`}
      </p>

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,6fr)_minmax(0,5fr)]">
        <div className="order-2 flex min-w-0 flex-col gap-2 lg:order-1">
          {absentInSource && (
            <p className="rounded-sm bg-tint px-3 py-2 text-sm text-amb-text">이 항목은 원문에 없습니다. 15항 첫 쪽을 보여 줍니다.</p>
          )}
          <SourceViewer doc={doc} page={page} onPage={(next) => params.update({ page: String(next) })} highlight={highlight} panelHeight={details.height} className="basis-auto" />
        </div>
        <div ref={details.ref} className="order-1 min-w-0 lg:order-2">
          {selected ? (
            <RegulationDetail
              key={selected.id}
              docId={docId}
              view={data}
              finding={selected}
              hidden={hidden}
              lock={lock}
              draft={drafts[selected.id] ?? ""}
              onDraft={(text) => onDraft(selected.id, text)}
              onNext={nextId ? () => select(nextId) : null}
              onPin={() => {
                if (params.finding !== selected.id) params.update({ finding: selected.id });
              }}
            />
          ) : (
            <Pane title="선택한 판정">
              <p className="text-mut">{findings.length ? `처리할 판정이 없습니다. 일치 ${counts.match}건은 아래 표에서 펼쳐 볼 수 있습니다.` : "15항에서 판정할 항목이 없습니다."}</p>
            </Pane>
          )}
        </div>
      </div>

      <RegulationTable
        view={data}
        findings={findings}
        law={params.law}
        todoOnly={params.todoOnly}
        selectedId={selected?.id ?? null}
        onSelect={select}
        onLaw={(law) => params.update({ law })}
        onTodoOnly={(on) => params.update({ todo: on ? "1" : null })}
      />
      <p className="text-sm text-mut">구버전은 시행일 자료가 없어 PoC 판정에서 제외하고 참고로만 보여 줍니다.</p>

      <Foot>
        <p className="text-mut">확인하지 않은 추출값은 저장 결과에 &quot;미검수&quot;로 남습니다.</p>
        <div className="flex flex-wrap gap-2">
          <Link href={routes.review(docId, "values")} className={buttonStyles({ size: "lg" })}>
            추출값 확인하러 가기
          </Link>
          <Button variant="primary" size="lg" onClick={() => onSave(counts.unreviewed)}>
            저장하기
          </Button>
        </div>
      </Foot>
    </div>
  );
}

function StartJudgment({ docId }: { docId: string }) {
  const client = useQueryClient();
  const reviewer = useReviewer();
  const start = useMutation({
    mutationFn: () => postToJudgment(docId, reviewer),
    onSuccess: () => client.invalidateQueries({ queryKey: judgmentKeys.status(docId) }),
  });
  return (
    <Notice title="아직 판정하지 않았습니다">
      <p className="text-mut">추출값을 먼저 확인하거나, 지금 값으로 바로 판정할 수 있습니다.</p>
      <div className="flex flex-wrap justify-center gap-2">
        <Link href={routes.review(docId, "values")} className={buttonStyles()}>
          추출값 확인
        </Link>
        <Button variant="primary" disabled={!reviewer || start.isPending} onClick={() => start.mutate()}>
          {start.isPending ? "넘기는 중…" : "판정으로 넘기기"}
        </Button>
      </div>
      {!reviewer && <p className="text-sm text-mut">판정으로 넘기려면 머리줄에서 검토자 이름을 정해 주세요.</p>}
      {start.isError && (
        <p role="alert" className="text-sm break-words text-red">
          {isJudgmentApiMissing(start.error) ? "판정으로 넘기는 서버 기능이 아직 연결되지 않았습니다." : `넘기지 못했습니다: ${start.error.message}`}
        </p>
      )}
    </Notice>
  );
}

function NotConnected({ docId }: { docId: string }) {
  return (
    <Notice title="판정 서비스가 아직 연결되지 않았습니다">
      <p className="text-mut">판정 API가 준비되면 이 화면에서 15항 판정을 바로 볼 수 있습니다. 그동안 추출값은 확인할 수 있습니다.</p>
      <div className="flex flex-wrap justify-center gap-2">
        <Link href={routes.review(docId, "values")} className={buttonStyles()}>
          추출값 확인
        </Link>
        {DEV && (
          <Link href={`${routes.review(docId, "regulation")}&judgmentMock=ready`} className={buttonStyles({ variant: "outline" })}>
            개발용 가상 판정 보기
          </Link>
        )}
      </div>
    </Notice>
  );
}

function ErrorBody({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const message =
    error instanceof ApiContractError
      ? "판정 응답이 화면 약속과 달라 틀린 판정을 보여 주지 않으려고 표시하지 않았습니다."
      : error instanceof ApiRequestError
        ? error.message
        : "서버에 연결하지 못했습니다.";
  return (
    <Notice title="판정 결과를 불러오지 못했습니다" alert>
      <p className="break-words text-mut">{message}</p>
      {error instanceof ApiContractError && <p className="text-sm break-words text-mut">{error.message}</p>}
      <Button onClick={onRetry}>다시 불러오기</Button>
    </Notice>
  );
}

function Notice({ title, alert, children }: { title: string; alert?: boolean; children: React.ReactNode }) {
  return (
    <Pane title="15항 법적 규제">
      <div role={alert ? "alert" : "status"} className="flex flex-col items-center gap-3 py-10 text-center">
        <h3 className="text-lg font-bold">{title}</h3>
        {children}
      </div>
    </Pane>
  );
}

function LoadingBody({ message }: { message?: string }) {
  return (
    <div className="flex flex-col gap-5">
      <div className="grid gap-5 lg:grid-cols-[minmax(0,6fr)_minmax(0,5fr)]">
        <Pane title="원문">
          <Skeleton className="h-56 w-full" />
        </Pane>
        <Pane title="선택한 판정">
          <Skeleton className="w-full" />
          <Skeleton className="w-2/3" />
        </Pane>
      </div>
      <Pane title="15항 판정">
        {message && (
          <p role="status" className="text-sm text-mut">
            {message}
          </p>
        )}
        <Skeleton className="w-full" />
        <Skeleton className="w-full" />
        <Skeleton className="w-4/5" />
      </Pane>
    </div>
  );
}
