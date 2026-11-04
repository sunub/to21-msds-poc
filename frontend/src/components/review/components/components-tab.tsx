"use client";

/*
 * 성분별 요약 탭 (시안 '탭 · 성분별 요약' 혼합물·단일물질). 판정 API의 consistency.results[m].components·limitations 를 그린다.
 * 계약: docs/superpowers/specs/contracts/3-consistency (component_summary), 6-screens '성분별 요약 탭'.
 * 판정 API가 아직 성분 요약을 채우지 않으면 그 사실만 알리고, 나머지 탭은 그대로 쓴다.
 */
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useState } from "react";
import { judgmentViewQuery, type JudgmentView } from "@/api/judgment";
import { SourceViewer } from "@/components/extract/source-viewer";
import { Foot, Pane, Workspace } from "@/components/shell/layout";
import { Button, PillTabs, Skeleton, buttonStyles } from "@/components/ui";
import { componentFindings, limitationCards, pickResult, sourceTabs, type LimitationCard } from "@/lib/components";
import { isUnreviewed } from "@/lib/regulation";
import { routes } from "@/lib/routes";
import { JudgmentError, JudgmentGate, JudgmentNotice, type JudgmentReady } from "../judgment-gate";
import { ComponentDetail } from "./component-detail";
import { ComponentTable } from "./component-table";
import { LimitationList } from "./limitation-list";

const PANE = "성분별 요약";

/** 고른 성분·MSDS·쪽은 주소에 둔다. 새로 고치거나 다른 탭에서 돌아와도 같은 화면이 나온다 */
function useComponentParams() {
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
    comp: params.get("comp"),
    msds: Math.max(0, Number(params.get("msds")) || 0),
    page: params.has("page") ? Math.max(1, Number(params.get("page")) || 1) : null,
    update,
  };
}

export function ComponentsTab({ docId, onSave }: { docId: string; onSave: (unreviewed: number) => void }) {
  return (
    <JudgmentGate docId={docId} tab="components" paneTitle={PANE} what="성분별 판단 요약" loading={(m) => <LoadingBody message={m} />}>
      {(ready) => <ComponentsReady docId={docId} ready={ready} onSave={onSave} />}
    </JudgmentGate>
  );
}

function ComponentsReady({ docId, ready, onSave }: { docId: string; ready: JudgmentReady; onSave: (unreviewed: number) => void }) {
  // 처음 본 버전에 고정한다. 새 버전이 생기면 알리고 사용자가 고를 때 바꾼다 (15항 탭과 같은 규칙)
  const [version, setVersion] = useState(ready.latest);
  const view = useQuery(judgmentViewQuery(docId, version));

  if (view.isPending) return <LoadingBody />;
  if (view.isError && !view.data) return <JudgmentError paneTitle={PANE} error={view.error} onRetry={() => void view.refetch()} />;
  return (
    <ComponentsLoaded
      docId={docId}
      ready={ready}
      data={view.data!}
      version={version}
      offline={ready.offline || view.isRefetchError}
      onNewest={() => setVersion(ready.latest)}
      onSave={onSave}
    />
  );
}

function ComponentsLoaded({
  docId,
  ready,
  data,
  version,
  offline,
  onNewest,
  onSave,
}: {
  docId: string;
  ready: JudgmentReady;
  data: JudgmentView;
  version: number;
  offline: boolean;
  onNewest: () => void;
  onSave: (unreviewed: number) => void;
}) {
  const params = useComponentParams();
  const results = data.consistency.results;
  const result = pickResult(results, params.msds);
  const msdsIndex = result.msds_index;
  const productType = result.product_type.value;
  const single = productType === "단일물질";
  const newer = version < ready.latest;
  const unreviewed = results.flatMap((r) => r.findings).filter((f) => isUnreviewed(f, data.reviews)).length;

  const banners = (
    <>
      {ready.pending && (
        <p role="status" className="rounded-md bg-blue-soft px-4 py-2.5 text-sm text-blue2">
          추출값이 바뀌어 다시 판정하는 중입니다. 아래는 이전 판정입니다.
        </p>
      )}
      {!ready.pending && newer && (
        <div role="status" className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-amb bg-tint px-4 py-2.5 text-sm text-amb-text">
          <span>새 판정이 있습니다.</span>
          <Button onClick={onNewest}>새 판정 보기</Button>
        </div>
      )}
      {offline && (
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
              onClick={() => params.update({ msds: String(r.msds_index), comp: null, page: null })}
            >
              MSDS {r.msds_index + 1}
            </Button>
          ))}
        </div>
      )}
      <p className="text-sm text-mut">판정 기준 {productType}</p>
    </>
  );

  const foot = (
    <Foot>
      <p className="text-mut">확인하지 않은 추출값은 저장 결과에 &quot;미검수&quot;로 남습니다.</p>
      <div className="flex flex-wrap gap-2">
        <Link href={routes.review(docId, "values")} className={buttonStyles({ size: "lg" })}>
          추출값 확인하러 가기
        </Link>
        <Button variant="primary" size="lg" onClick={() => onSave(unreviewed)}>
          저장하기
        </Button>
      </div>
    </Foot>
  );

  const components = result.components;
  if (!components || components.length === 0) {
    return (
      <div className="flex flex-col gap-5">
        {banners}
        <JudgmentNotice paneTitle={PANE} title={components ? "성분 정보가 없습니다" : "판정에 성분별 요약이 아직 없습니다"}>
          <p className="text-mut">
            {components
              ? "3항에서 읽은 성분이 없어 성분별로 나눠 볼 내용이 없습니다. 추출값의 3항을 확인해 주세요."
              : "판정 서버가 성분별 요약을 아직 보내지 않습니다. 2항·15항 판정은 각 탭에서 볼 수 있습니다."}
          </p>
          <div className="flex flex-wrap justify-center gap-2">
            <Link href={routes.review(docId, "hazard")} className={buttonStyles()}>
              2항 판정
            </Link>
            <Link href={routes.review(docId, "regulation")} className={buttonStyles()}>
              15항 판정
            </Link>
          </div>
        </JudgmentNotice>
        {foot}
      </div>
    );
  }

  const selected = components.find((c) => c.comp_ref === params.comp) ?? components[0];
  const tabs = sourceTabs(ready.doc.sections, msdsIndex, single);
  const page = params.page ?? tabs[0]?.page ?? 1;
  const firstRegulation = componentFindings(result, selected, "15")[0];
  const cards = limitationCards(result, result.limitations ?? []);
  const hrefFor = (card: LimitationCard) =>
    card.findingId === null
      ? null
      : card.section === "15"
        ? routes.review(docId, "regulation", { finding: card.findingId })
        : routes.review(docId, "hazard");

  return (
    <div className="flex flex-col gap-5">
      {banners}
      <Workspace viewport className="lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <div className="order-2 flex min-w-0 flex-col gap-2 lg:order-1 lg:min-h-0">
          <div className="flex flex-wrap items-center justify-between gap-2">
            {single ? (
              <span className="text-sm text-mut">성분이 1개라 3항만 봅니다</span>
            ) : (
              <span className="text-sm text-mut">성분표와 독성 정보</span>
            )}
            {tabs.length > 1 && (
              <PillTabs
                label="원문 항"
                items={tabs.map((t) => ({ id: String(t.page), label: `${t.section}항 p.${t.page}` }))}
                value={String(page)}
                onChange={(id) => params.update({ page: id })}
              />
            )}
          </div>
          {tabs.length === 0 && <p className="rounded-md bg-tint px-3 py-2 text-sm text-amb-text">3항 페이지를 찾지 못해 첫 페이지를 보여 줍니다.</p>}
          <SourceViewer
            doc={ready.doc}
            page={page}
            onPage={(next) => params.update({ page: String(next) })}
            highlight={selected.cas ?? selected.name}
            className="lg:h-auto lg:min-h-0 lg:flex-1"
          />
        </div>
        <div className="order-1 min-w-0 lg:order-2 lg:min-h-0">
          <ComponentDetail
            key={selected.comp_ref}
            component={selected}
            single={single}
            hazardHref={routes.review(docId, "hazard")}
            regulationHref={firstRegulation ? routes.review(docId, "regulation", { finding: firstRegulation.id }) : null}
          />
        </div>
      </Workspace>

      <ComponentTable
        components={components}
        productType={productType}
        selected={selected.comp_ref}
        onSelect={(comp) => params.update({ comp })}
      />
      <LimitationList cards={cards} hrefFor={hrefFor} />
      {foot}
    </div>
  );
}

function LoadingBody({ message }: { message?: string }) {
  return (
    <div className="flex flex-col gap-5">
      <div className="grid gap-5 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <Pane title="원문">
          <Skeleton className="h-56 w-full" />
        </Pane>
        <Pane title="성분 상세">
          <Skeleton className="w-full" />
          <Skeleton className="w-2/3" />
        </Pane>
      </div>
      <Pane title="구성성분별 판단 요약">
        {message && (
          <p role="status" className="text-sm text-mut">
            {message}
          </p>
        )}
        <Skeleton className="w-full" />
        <Skeleton className="w-4/5" />
      </Pane>
    </div>
  );
}
