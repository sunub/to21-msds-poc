"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Suspense, useCallback, useState } from "react";
import { documentDetailQuery, resultQuery } from "@/api/documents";
import type { DocumentDetail, SectionProgress } from "@/api/schemas";
import { RetryButton } from "@/components/documents/retry-button";
import { RegeneratedPreview } from "@/components/extract/regenerated-preview";
import { ValidationNotice } from "@/components/extract/validation-notice";
import { SectionProgressTable, SectionValues, type SectionKey } from "@/components/extract/section-progress";
import { SourceViewer } from "@/components/extract/source-viewer";
import { DocFrame } from "@/components/shell/doc-frame";
import { Foot, Pane, Workspace } from "@/components/shell/layout";
import { Progress, Skeleton, StatusLabel, Table, TableHead, buttonStyles } from "@/components/ui";
import { useDocumentTransitions } from "@/hooks/use-document-transitions";
import { usePageParam } from "@/hooks/use-page-param";
import { routes } from "@/lib/routes";
import { allSectionsFailed, stageMessage } from "@/lib/status";

/**
 * 1.2~1.3 추출 진행과 끝난 뒤의 재생성 미리 보기. 진행 상태는 상세 쿼리 하나(2초 폴링)가 전부다.
 * 항별 추출은 서버가 동시에 돌리므로 화면은 항마다 요청을 보내지 않고, 응답을 항으로 나눠 그린다.
 */
function ExtractBody({ docId }: { docId: string }) {
  const { data: doc, isRefetchError } = useQuery(documentDetailQuery(docId));
  const result = useQuery({
    ...resultQuery(docId),
    enabled: doc?.status === "done" && !doc.validation && !doc.summary?.validation,
  });
  useDocumentTransitions(docId, doc?.status);

  if (!doc) return <LoadingBody />;
  return (
    <>
      {isRefetchError && (
        <p role="status" className="text-sm text-amb-text print:hidden">
          서버와 연결이 끊겼습니다. 아래는 마지막으로 받은 내용이고, 연결되면 이어서 보여 줍니다.
        </p>
      )}
      <LoadedBody doc={{ ...doc, validation: doc.validation ?? doc.summary?.validation ?? result.data?.validation ?? null }} />
    </>
  );
}

function LoadedBody({ doc }: { doc: DocumentDetail }) {
  const [page, setPage] = usePageParam();
  const [selected, setSelected] = useState<SectionKey | null>(null);

  const openSection = useCallback(
    (section: Pick<SectionProgress, "msds_index" | "section" | "pages">) => {
      setSelected({ msds_index: section.msds_index, section: section.section });
      if (section.pages.length) setPage(section.pages[0]);
    },
    [setPage],
  );
  const openBySection = (msdsIndex: number, no: number) => {
    const section = doc.sections.find((s) => s.msds_index === msdsIndex && s.section === no);
    if (section) openSection(section);
  };
  const selectedSection = selected
    ? doc.sections.find((s) => s.msds_index === selected.msds_index && s.section === selected.section)
    : undefined;

  const showPreview = doc.status === "done" && !allSectionsFailed(doc);

  return (
    <>
      <ValidationNotice status={doc.status} counts={doc.counts} validation={doc.validation} />
      <DocumentNotices doc={doc} />
      <Workspace>
        <SourceViewer doc={doc} page={page} onPage={setPage} />
        {showPreview ? (
          <RegeneratedPreview doc={doc} onSection={openBySection} />
        ) : (
          <ProgressPane doc={doc} selected={selected} selectedSection={selectedSection} onSelect={openSection} />
        )}
      </Workspace>
      <ExtractFoot doc={doc} />
    </>
  );
}

function ProgressPane({
  doc,
  selected,
  selectedSection,
  onSelect,
}: {
  doc: DocumentDetail;
  selected: SectionKey | null;
  selectedSection?: SectionProgress;
  onSelect: (section: SectionProgress) => void;
}) {
  const { queued, running, done, failed, total } = doc.counts;
  const active = doc.status === "queued" || doc.status === "running";
  return (
    <Pane
      title="항목별 추출 상태"
      fill
      aside={
        total > 0 ? (
          <span className="text-sm text-mut tabular-nums">
            완료 {done} · 추출 중 {running} · 대기 {queued}
            {failed > 0 && <span className="text-red"> · 실패 {failed}</span>}
          </span>
        ) : undefined
      }
    >
      {active && (
        <div role="status" className="flex flex-col gap-2">
          <p>{stageMessage(doc)}</p>
          <Progress
            value={total > 0 ? ((done + failed) / total) * 100 : (doc.stage_index / doc.stage_total) * 100}
            label="추출 진행"
          />
        </div>
      )}
      {doc.sections.length > 0 ? (
        <SectionProgressTable doc={doc} selected={selected} onSelect={onSelect} />
      ) : (
        <SkeletonTable />
      )}
      {selectedSection && <SectionValues docId={doc.id} section={selectedSection} />}
      {doc.sections.length > 0 && !selectedSection && (
        <p className="text-sm text-mut">항을 누르면 왼쪽 원문이 그 쪽으로 옮겨 가고, 끝난 항은 값을 볼 수 있습니다.</p>
      )}
    </Pane>
  );
}

function SkeletonTable() {
  return (
    <Table className="rounded-sm">
      <TableHead className="px-3.5 py-2">
        <span className="w-8">항</span>
        <span className="flex-1">제목</span>
        <span className="w-20">상태</span>
      </TableHead>
      {[0, 1, 2, 3].map((i) => (
        <div key={i} aria-hidden="true" className="flex items-center gap-3 border-b border-line2 px-3.5 py-3 last:border-b-0">
          <Skeleton className="w-8" />
          <span className="flex-1">
            <Skeleton className="w-40" />
          </span>
          <Skeleton className="w-20" />
        </div>
      ))}
    </Table>
  );
}

/** 업로드 문서는 항상 manifest 밖이라 나오는 내부 안내 경고는 숨긴다 */
const HIDDEN_WARNING_PREFIX = "manifest에 없는 문서";

/** 실패 사유, 경고, 같은 PDF 안내 */
function DocumentNotices({ doc }: { doc: DocumentDetail }) {
  const warnings = doc.warnings.filter((w) => !w.startsWith(HIDDEN_WARNING_PREFIX));
  const failedAll = doc.status === "done" && allSectionsFailed(doc);
  const failedSome = !failedAll && doc.status === "done" && doc.counts.failed > 0;
  const firstError = doc.sections.find((s) => s.errors.length)?.errors[0];
  if (!doc.error && !failedAll && !failedSome && warnings.length === 0 && doc.duplicate_of.length === 0) {
    return null;
  }
  return (
    <div className="flex flex-col gap-1.5 rounded-md border border-line bg-white px-5 py-3.5 text-sm print:hidden">
      {doc.error && (
        <p role="alert" className="break-words text-red">
          {doc.status === "interrupted" ? "처리가 멈췄습니다" : "처리하지 못했습니다"}: {doc.error}
        </p>
      )}
      {failedAll && (
        <p role="alert" className="break-words text-red">
          모든 항의 추출이 실패해 보여 줄 결과가 없습니다.{firstError && ` 첫 오류: ${firstError}`}
        </p>
      )}
      {failedSome && (
        <StatusLabel tone="warning">{doc.counts.failed}개 항을 추출하지 못했습니다. 해당 항은 비어 있습니다.</StatusLabel>
      )}
      {warnings.map((w, i) => (
        <p key={i} className="break-words text-amb-text">
          {w}
        </p>
      ))}
      {doc.duplicate_of.length > 0 && (
        <p className="text-mut">
          같은 파일을 먼저 올린 적이 있습니다:{" "}
          {doc.duplicate_of.map((id, i) => (
            <span key={id}>
              {i > 0 && ", "}
              <Link href={routes.extract(id)}>{id}</Link>
            </span>
          ))}
        </p>
      )}
    </div>
  );
}

function ExtractFoot({ doc }: { doc: DocumentDetail }) {
  const active = doc.status === "queued" || doc.status === "running";
  const canReview = doc.status === "done" && !allSectionsFailed(doc);
  return (
    <div className="print:hidden">
      <Foot bordered={false}>
        <p className="text-mut">
          {active
            ? "이 화면을 닫아도 추출은 계속됩니다. 목록에서 이어서 볼 수 있습니다. 검수는 추출이 끝나면 열립니다."
            : canReview
              ? "재생성 문서를 확인한 뒤 검수를 시작하세요."
              : "다시 돌리면 처음부터 다시 추출합니다."}
        </p>
        <div className="flex flex-wrap gap-2">
          <Link href={routes.home()} className={buttonStyles({ size: "lg" })}>
            목록으로
          </Link>
          {doc.can_retry && (
            <RetryButton docId={doc.id} filename={doc.filename} size="lg" variant={canReview ? "default" : "primary"} />
          )}
          {canReview && (
            <Link href={routes.reviewMode(doc.id)} className={buttonStyles({ variant: "primary", size: "lg" })}>
              검수 방식 고르기
            </Link>
          )}
        </div>
      </Foot>
    </div>
  );
}

/** 첫 응답을 받기 전 (1.2 모양) */
function LoadingBody() {
  return (
    <Workspace>
      <Pane title="원문" fill>
        <div aria-hidden="true" className="grid gap-2.5">
          <Skeleton className="w-full" />
          <Skeleton className="w-4/5" />
          <Skeleton className="w-2/3" />
        </div>
      </Pane>
      <Pane title="항목별 추출 상태" fill>
        <SkeletonTable />
      </Pane>
    </Workspace>
  );
}

export default function ExtractPage() {
  return (
    <Suspense>
      <DocFrame stage="extract" width="max-w-320" fill>
        {(doc) => <ExtractBody key={doc} docId={doc} />}
      </DocFrame>
    </Suspense>
  );
}
