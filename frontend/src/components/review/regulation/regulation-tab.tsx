"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useState } from "react";
import { judgmentViewQuery, type Finding, type JudgmentView } from "@/api/judgment";
import type { DocumentDetail } from "@/api/schemas";
import { SourceViewer } from "@/components/extract/source-viewer";
import { Foot, Pane, Workspace } from "@/components/shell/layout";
import { Button, PillTabs, Skeleton, buttonStyles } from "@/components/ui";
import { ownSectionPage, sectionTabs } from "@/lib/hazard";
import { defaultFindingId, nextUnreviewedId, prevUnreviewedId, regulationCounts, regulationFindings, unreviewedFindings } from "@/lib/regulation";
import { routes } from "@/lib/routes";
import { JudgmentError, JudgmentGate, type JudgmentReady } from "../judgment-gate";
import { RegulationDetail, type LockReason } from "./regulation-detail";
import { RegulationTable } from "./regulation-table";

type DraftProps = {
  drafts: Record<string, string>;
  onDraft: (findingId: string, text: string) => void;
};

const PANE_TITLE = "15항 법적 규제";

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

/** 2.4 검수 · 15항 판정. 판정 상태에 따른 안내는 JudgmentGate 가 맡고, 판정이 있을 때만 시안 화면을 그린다 */
export function RegulationTab({
  docId,
  drafts,
  onDraft,
  onSave,
}: {
  docId: string;
  /** 저장으로 간다. 미처리 수를 넘겨 경고를 띄울지 화면이 정한다 */
  onSave: (unreviewed: number) => void;
} & DraftProps) {
  return (
    <JudgmentGate
      docId={docId}
      tab="regulation"
      paneTitle={PANE_TITLE}
      what="15항 판정"
      loading={(message) => <LoadingBody message={message} />}
    >
      {(ready) => <RegulationReady docId={docId} ready={ready} drafts={drafts} onDraft={onDraft} onSave={onSave} />}
    </JudgmentGate>
  );
}

function RegulationReady({
  docId,
  ready,
  drafts,
  onDraft,
  onSave,
}: {
  docId: string;
  ready: JudgmentReady;
  onSave: (unreviewed: number) => void;
} & DraftProps) {
  // 처음 본 버전에 고정한다. 새 버전이 생겨도 사용자가 고르기 전에는 읽던 표를 바꾸지 않는다
  const [version, setVersion] = useState(ready.latest);
  const view = useQuery(judgmentViewQuery(docId, version));

  if (view.isPending) return <LoadingBody />;
  if (view.isError && !view.data) return <JudgmentError paneTitle={PANE_TITLE} error={view.error} onRetry={() => void view.refetch()} />;
  return (
    <RegulationLoaded
      docId={docId}
      doc={ready.doc}
      data={view.data!}
      version={version}
      latest={ready.latest}
      pending={ready.pending}
      offline={ready.offline || view.isRefetchError}
      onNewest={() => setVersion(ready.latest)}
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
  onSave: (unreviewed: number) => void;
} & DraftProps) {
  const params = useRegulationParams();

  const results = data.consistency.results;
  const msdsIndex = results.some((r) => r.msds_index === params.msds) ? params.msds : results[0].msds_index;
  const findings = regulationFindings(data, msdsIndex);
  const selected =
    findings.find((f) => f.id === params.finding) ??
    findings.find((f) => f.id === defaultFindingId(findings, data.reviews)) ??
    null;
  const display = selected ? data.display[selected.id] : null;
  const firstPage = doc.sections.find((s) => s.msds_index === msdsIndex && s.section === 15)?.pages[0] ?? 1;
  const page = params.page ?? ownSectionPage(display, 15, firstPage);
  const tabs = sectionTabs(display, 15, firstPage);
  const highlight = selected?.msds.evidence?.[0]?.source_text ?? null;
  const absentInSource = !!selected && !selected.msds.present;

  const newer = version < latest;
  const lock: LockReason = pending ? "rerun" : newer ? "new" : offline ? "offline" : null;
  const hidden = !!selected && !!params.law && selected.law_label !== params.law;
  const counts = regulationCounts(findings, data.reviews);
  const nextId = nextUnreviewedId(findings, data.reviews, selected?.id ?? null);
  const prevId = prevUnreviewedId(findings, data.reviews, selected?.id ?? null);

  const select = (f: Finding | string) => {
    const target = typeof f === "string" ? findings.find((x) => x.id === f) : f;
    if (!target) return;
    params.update({ finding: target.id, page: String(ownSectionPage(data.display[target.id], 15, firstPage)) });
  };

  return (
    <div className="flex flex-col gap-5">
      {pending && (
        <p role="status" className="rounded-md bg-blue-soft px-4 py-2.5 text-sm text-blue2">
          추출값이 바뀌어 다시 판정하는 중입니다. 아래는 이전 판정이며 처리는 잠시 잠급니다.
        </p>
      )}
      {!pending && newer && (
        <div role="status" className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-amb bg-tint px-4 py-2.5 text-sm text-amb-text">
          <span>새 판정이 있습니다. 쓰던 의견은 그대로 남습니다.</span>
          <Button onClick={onNewest}>새 판정 보기</Button>
        </div>
      )}
      {lock === "offline" && (
        <p role="status" className="rounded-md border border-amb bg-tint px-4 py-2.5 text-sm text-amb-text">
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
      {/* 원문 칸 안에 두면 원문 카드만 내려가 옆 판정 카드와 위아래가 어긋난다 */}
      {absentInSource && (
        <p role="status" className="rounded-md bg-tint px-3 py-2 text-sm text-amb-text">이 항목은 원문에 없습니다. 15항 첫 쪽을 보여 줍니다.</p>
      )}

      <Workspace viewport className="lg:grid-cols-[minmax(0,6fr)_minmax(0,5fr)]">
        <div className="order-2 min-w-0 lg:order-1 lg:min-h-0">
          <SourceViewer doc={doc} page={page} onPage={(next) => params.update({ page: String(next) })} highlight={highlight}>
            {tabs.length > 0 && (
              <PillTabs
                label="근거 쪽으로 이동"
                items={tabs.map((t) => ({ id: t.id, label: t.label }))}
                value={tabs.find((t) => t.page === page)?.id ?? ""}
                onChange={(id) => {
                  const target = tabs.find((t) => t.id === id);
                  if (target) params.update({ page: String(target.page) });
                }}
              />
            )}
          </SourceViewer>
        </div>
        <div className="order-1 min-w-0 lg:order-2 lg:min-h-0">
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
              onPrev={prevId ? () => select(prevId) : null}
              onPin={() => {
                if (params.finding !== selected.id) params.update({ finding: selected.id });
              }}
            />
          ) : (
            <Pane title="선택한 판정" fill>
              <p className="text-mut">{findings.length ? `처리할 판정이 없습니다. 일치 ${counts.match}건은 아래 표에서 펼쳐 볼 수 있습니다.` : "15항에서 판정할 항목이 없습니다."}</p>
            </Pane>
          )}
        </div>
      </Workspace>

      <Foot>
        <p className="text-mut">확인하지 않은 추출값은 저장 결과에 &quot;미검수&quot;로 남습니다.</p>
        <div className="flex flex-wrap gap-2">
          <Link href={routes.review(docId, "values")} className={buttonStyles({ size: "lg" })}>
            추출값 확인하러 가기
          </Link>
          <Button variant="primary" size="lg" onClick={() => onSave(unreviewedFindings(data).length)}>
            저장하기
          </Button>
        </div>
      </Foot>
    </div>
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
