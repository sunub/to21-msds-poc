"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { memo, useCallback, useState } from "react";
import { ApiRequestError } from "@/api/client";
import { documentDetailQuery, documentKeys, pageLinesQuery, reviewQuery, saveFieldReview, saveSectionReview } from "@/api/documents";
import type { DocumentDetail, FieldReviewRequest, ReviewField, ReviewResponse, ReviewSection, SectionReviewRequest } from "@/api/schemas";
import { SourceViewer } from "@/components/extract/source-viewer";
import { Foot, Pane, Workspace } from "@/components/shell/layout";
import { Button, Input, Skeleton, StatusLabel, buttonStyles } from "@/components/ui";
import { usePageParam } from "@/hooks/use-page-param";
import { cn } from "@/lib/cn";
import { describeProblem } from "@/lib/problem-text";
import { setReviewer, useReviewer } from "@/lib/reviewer";
import { routes } from "@/lib/routes";
import { fieldHighlight, type Highlight } from "@/lib/viewer";

/**
 * 쓰기 하나의 공통 처리. 같은 문서의 쓰기는 scope 로 차례로 보낸다 (늦게 온 응답이 새 값을 덮지 않게).
 * 서버가 돌려준 전체 보기로 캐시를 바꾸고, 고친 값이 들어가는 재생성은 다시 받게 한다.
 */
function useReviewWrite<T>(docId: string, write: (body: T) => Promise<ReviewResponse>) {
  const queryClient = useQueryClient();
  return useMutation({
    scope: { id: `review-${docId}` },
    mutationFn: write,
    onMutate: () => queryClient.cancelQueries({ queryKey: documentKeys.review(docId) }),
    onSuccess: (view) => {
      queryClient.setQueryData(documentKeys.review(docId), view);
      void queryClient.invalidateQueries({ queryKey: documentKeys.regenerated(docId) });
    },
  });
}

const errorText = (error: unknown) =>
  error instanceof ApiRequestError ? error.message : "저장하지 못했습니다. 서버가 켜져 있는지 확인해 주세요.";

/** 2.2 추출값 확인: 왼쪽 원문, 오른쪽 항별 칸. 칸마다 확인함·수정됨을 남기고 항 단위로 확인을 끝낸다 */
export function ValuesPanel({ docId }: { docId: string }) {
  const { data: doc } = useQuery(documentDetailQuery(docId));
  if (!doc) return <Skeleton className="w-2/3" />;
  if (doc.status !== "done") {
    return (
      <p className="text-mut">
        추출이 끝나면 값을 확인할 수 있습니다. <Link href={routes.extract(docId)}>진행 화면으로 가기</Link>
      </p>
    );
  }
  return <Values doc={doc} />;
}

function Values({ doc }: { doc: DocumentDetail }) {
  const { data, isPending, isError, error, refetch } = useQuery(reviewQuery(doc.id));
  const reviewer = useReviewer();
  const [page, setPage] = usePageParam();
  const [evidence, setEvidence] = useState<Highlight>(null);
  const [open, setOpen] = useState<string | null>(null);

  const showSource = useCallback(
    (nextPage: number | null, text: Highlight) => {
      if (nextPage) setPage(nextPage);
      setEvidence(text);
    },
    [setPage],
  );

  if (isPending) return <Skeleton className="w-2/3" />;
  if (isError) {
    return (
      <div role="alert" className="flex flex-col items-start gap-2 text-sm">
        <p className="text-red">{errorText(error)}</p>
        <Button onClick={() => void refetch()}>다시 불러오기</Button>
      </div>
    );
  }

  const { sections_total: total, sections_confirmed: confirmed, fields_edited: edited } = data.summary;
  const firstOpen = data.msds.flatMap((m) => m.sections.map((s) => ({ m: m.msds_index, s }))).find((x) => !x.s.confirmed);
  const openKey = open ?? (firstOpen ? `${firstOpen.m}:${firstOpen.s.section}` : null);

  return (
    <>
      <Workspace>
        <SourceViewer doc={doc} page={page} onPage={setPage} highlight={evidence} />
        <div className="min-w-0 lg:min-h-0">
          <Pane
            title="재생성 MSDS"
            fill
            aside={
              <span className="text-sm text-mut tabular-nums">
                {total}항 중 {confirmed}항 확인{edited > 0 && ` · 수정 ${edited}칸`} · 항을 눌러 펼칩니다
              </span>
            }
          >
            {!reviewer && <ReviewerPrompt />}
            {data.msds.map((m) => (
              <div key={m.msds_index} role="group" aria-label={`MSDS ${m.msds_index + 1}건`} className="flex flex-col gap-2">
                {data.msds.length > 1 && <h3 className="font-bold">MSDS {m.msds_index + 1}건 · {m.info.product_name}</h3>}
                {m.sections.map((s) => {
                  const key = `${m.msds_index}:${s.section}`;
                  return (
                    <SectionBlock
                      key={key}
                      docId={doc.id}
                      msdsIndex={m.msds_index}
                      section={s}
                      open={openKey === key}
                      reviewer={reviewer}
                      onToggle={() => setOpen(openKey === key ? "" : key)}
                      onSource={showSource}
                    />
                  );
                })}
              </div>
            ))}
          </Pane>
        </div>
      </Workspace>
      <Foot>
        <p className="text-mut">
          {total}항 중 {confirmed}항을 확인했습니다.
          {confirmed < total ? ` 남은 ${total - confirmed}개 항은 미검수로 남습니다.` : " 판정 단계로 넘어갈 수 있습니다."}
        </p>
        <Link href={routes.review(doc.id, "hazard")} className={buttonStyles({ variant: "primary", size: "lg" })}>
          2항 판정으로 가기
        </Link>
      </Foot>
    </>
  );
}

function sectionTone(s: ReviewSection, open: boolean) {
  if (s.status === "failed") return { tone: "danger" as const, label: "추출 실패" };
  if (s.confirmed) return { tone: "success" as const, label: "확인 완료" };
  if (open) return { tone: "info" as const, label: "지금 작업 중" };
  if (s.needs_review) return { tone: "warning" as const, label: "검토 필요" };
  return { tone: "neutral" as const, label: "확인 전" };
}

function SectionBlock({
  docId,
  msdsIndex,
  section,
  open,
  reviewer,
  onToggle,
  onSource,
}: {
  docId: string;
  msdsIndex: number;
  section: ReviewSection;
  open: boolean;
  reviewer: string;
  onToggle: () => void;
  onSource: (page: number | null, text: Highlight) => void;
}) {
  const confirm = useReviewWrite(docId, (body: SectionReviewRequest) => saveSectionReview(docId, body));
  const { tone, label } = sectionTone(section, open);
  const panelId = `section-${msdsIndex}-${section.section}`;
  return (
    <section className={cn("rounded-sm border", open ? "border-blue-line" : "border-line")}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => {
          onToggle();
          if (!open && section.pages[0]) onSource(section.pages[0], null);
        }}
        className="flex w-full cursor-pointer items-center gap-3 px-3.5 py-2.5 text-left"
      >
        <span className="w-6 tabular-nums">{section.section}</span>
        <span className="min-w-0 flex-1 font-medium">{section.title ?? `${section.section}항`}</span>
        <span className="text-sm text-mut tabular-nums">{section.field_count}칸</span>
        <StatusLabel tone={tone}>{label}</StatusLabel>
      </button>
      {open && (
        <div id={panelId} className="flex flex-col gap-3 border-t border-line2 px-3.5 py-3">
          {section.problems.length > 0 && <Problems docId={docId} problems={section.problems} onSource={onSource} />}
          {section.field_count === 0 ? (
            <p className="text-sm text-mut">이 항에는 추출된 값이 없습니다. 원문과 맞춰 봐 주세요.</p>
          ) : (
            section.groups.map((g) => (
              <div key={g.path} className="flex flex-col">
                {g.fields.length > 1 && <h4 className="mb-1 text-sm font-medium text-sub">{g.title}</h4>}
                {g.fields.map((f) => (
                  <FieldRow key={f.path} docId={docId} msdsIndex={msdsIndex} field={f} reviewer={reviewer} onSource={onSource} />
                ))}
              </div>
            ))
          )}
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line2 pt-3">
            <p className="text-sm text-mut">
              {section.confirmed
                ? `${section.confirmed.reviewer} 확인`
                : `칸 ${section.field_count}개 중 ${section.checked_count}개를 표시했습니다`}
            </p>
            <Button
              variant={section.confirmed ? "default" : "primary"}
              disabled={!reviewer || confirm.isPending}
              aria-busy={confirm.isPending}
              onClick={() =>
                confirm.mutate({ msds_index: msdsIndex, section: section.section, confirmed: !section.confirmed, reviewer })
              }
            >
              {section.confirmed ? "확인 취소" : "이 항 확인 완료"}
            </Button>
          </div>
          {confirm.isError && (
            <p role="alert" className="text-sm text-red">
              {errorText(confirm.error)}
            </p>
          )}
        </div>
      )}
    </section>
  );
}

const PROBLEMS_SHOWN = 5;

function Problems({
  docId,
  problems,
  onSource,
}: {
  docId: string;
  problems: string[];
  onSource: (page: number | null, text: Highlight) => void;
}) {
  const [all, setAll] = useState(false);
  const [open, setOpen] = useState<number[]>([]);
  const shown = all ? problems : problems.slice(0, PROBLEMS_SHOWN);
  return (
    <div className="rounded-md bg-tint px-3 py-2 text-sm">
      <p className="font-medium text-amb-text">확인이 필요한 값 {problems.length}건</p>
      <ul className="m-0 mt-1 flex list-none flex-col gap-1 p-0 text-sub">
        {shown.map((p, i) => {
          const d = describeProblem(p);
          const expanded = open.includes(i);
          return (
            <li key={i} className="break-words">
              <div className="flex items-baseline justify-between gap-2">
                <span>
                  {d.where && <b className="font-bold">{d.where} </b>}
                  {d.summary}
                </span>
                {d.page !== null && (
                  <Button
                    variant="link"
                    className="min-h-0 shrink-0 text-xs"
                    aria-expanded={expanded}
                    onClick={() => setOpen(expanded ? open.filter((x) => x !== i) : [...open, i])}
                  >
                    원문
                  </Button>
                )}
              </div>
              {expanded && d.page !== null && <SourceLines docId={docId} page={d.page} line={d.line} onSource={onSource} />}
            </li>
          );
        })}
      </ul>
      {problems.length > PROBLEMS_SHOWN && (
        <Button variant="link" className="min-h-0" onClick={() => setAll(!all)}>
          {all ? "줄이기" : `${problems.length - PROBLEMS_SHOWN}건 더 보기`}
        </Button>
      )}
    </div>
  );
}

/** 오류가 가리키는 줄과 앞뒤 1줄. 펼쳤을 때만 그려지므로 그때만 요청한다 */
function SourceLines({
  docId,
  page,
  line,
  onSource,
}: {
  docId: string;
  page: number;
  line: number | null;
  onSource: (page: number | null, text: Highlight) => void;
}) {
  const { data, isPending, isError } = useQuery(pageLinesQuery(docId, page));
  if (isPending) return <p className="m-0 mt-1 text-xs text-mut">원문을 불러오는 중</p>;
  if (isError) return <p className="m-0 mt-1 text-xs text-mut">원문을 불러오지 못했습니다</p>;
  const at = data.lines.findIndex((l) => l.no === line);
  if (at < 0) return <p className="m-0 mt-1 text-xs text-mut">원문을 불러오지 못했습니다</p>;
  const hit = data.lines[at];
  return (
    <div className="mt-1 flex flex-col items-start gap-1">
      <p className="m-0 flex w-full gap-2 break-words bg-tint px-1 py-0.5 text-xs font-medium text-ink">
        <span className="w-6 shrink-0 text-right text-mut tabular-nums">{hit.no}</span>
        <span className="min-w-0">{hit.text}</span>
      </p>
      <Button variant="link" className="min-h-0 text-xs" onClick={() => onSource(page, hit.text)}>
        {page}페이지에서 보기
      </Button>
    </div>
  );
}

/** 칸 한 줄. 응답의 구조 공유로 안 바뀐 칸은 다시 그리지 않는다 */
const FieldRow = memo(function FieldRow({
  docId,
  msdsIndex,
  field,
  reviewer,
  onSource,
}: {
  docId: string;
  msdsIndex: number;
  field: ReviewField;
  reviewer: string;
  onSource: (page: number | null, text: Highlight) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const write = useReviewWrite(docId, (body: FieldReviewRequest) => saveFieldReview(docId, body));
  const send = (action: FieldReviewRequest["action"], value?: string) =>
    write.mutate({ msds_index: msdsIndex, path: field.path, action, value, reviewer }, { onSuccess: () => setEditing(false) });

  return (
    <div className="border-b border-line2 py-2 last:border-b-0">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="w-32 flex-none text-sm break-words text-mut">{field.label}</span>
        <span className="min-w-0 flex-1 basis-40 text-sm break-words">
          {field.value === null ? <span className="text-mut">값 없음</span> : (field.display ?? String(field.value))}
        </span>
        {field.page !== null && (
          <Button variant="link" className="min-h-0 text-sm" onClick={() => onSource(field.page, fieldHighlight(field.value, field.source_text))}>
            원문 {field.page}페이지
          </Button>
        )}
        {field.state === "confirmed" && <StatusLabel tone="success">확인함</StatusLabel>}
        {field.state === "edited" && <StatusLabel tone="info">수정됨</StatusLabel>}
        {field.problems.length > 0 && <StatusLabel tone="danger">검사 실패</StatusLabel>}
      </div>
      {field.problems.map((p, i) => (
        <p key={i} className="mt-1 text-sm break-words text-red">
          {p}
        </p>
      ))}
      {field.state === "edited" && (
        <p className="mt-1 text-sm break-words text-mut">
          원래 값: {field.original === null ? "값 없음" : String(field.original)} · {field.reviewer}
        </p>
      )}
      {editing ? (
        <form
          className="mt-2 flex flex-col gap-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            send("edit", draft);
          }}
        >
          <div className="flex flex-wrap gap-2">
            <Input
              aria-label={`${field.label} 고치기`}
              value={draft}
              autoFocus
              onChange={(e) => setDraft(e.target.value)}
              className="min-w-0 flex-1 basis-40"
            />
            <Button type="submit" variant="primary" disabled={write.isPending} aria-busy={write.isPending}>
              저장
            </Button>
            <Button onClick={() => setEditing(false)} disabled={write.isPending}>
              취소
            </Button>
          </div>
          <p className="text-sm text-mut">원래 값, 원문 근거, 검토자, 시각이 함께 남습니다. 비우면 값 없음이 됩니다.</p>
        </form>
      ) : (
        <div className="mt-1 flex flex-wrap gap-x-3">
          {field.state !== "confirmed" && field.state !== "edited" && (
            <Button variant="outline" size="md" className="px-2.5 text-sm" disabled={!reviewer || write.isPending} onClick={() => send("confirm")}>
              확인함
            </Button>
          )}
          <Button
            variant="outline"
            size="md"
            className="px-2.5 text-sm"
            disabled={!reviewer || write.isPending}
            onClick={() => {
              setDraft(field.value === null ? "" : String(field.value));
              setEditing(true);
            }}
          >
            고치기
          </Button>
          {field.state !== "unchecked" && (
            <Button variant="default" size="md" className="px-2.5 text-sm" disabled={!reviewer || write.isPending} onClick={() => send("reset")}>
              되돌리기
            </Button>
          )}
        </div>
      )}
      {write.isError && (
        <p role="alert" className="mt-1 text-sm text-red">
          {errorText(write.error)}
        </p>
      )}
    </div>
  );
});

/** 검토자 이름이 없으면 확인·수정 단추가 잠긴다. 머리줄을 찾아가지 않고 이 자리에서 바로 정하게 한다 */
function ReviewerPrompt() {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      role="alert"
      noValidate
      className="flex flex-wrap items-center gap-2 rounded-md bg-tint px-3 py-2 text-sm text-amb-text"
      onSubmit={(e) => {
        e.preventDefault();
        const name = draft.trim();
        if (!name) return setError("검토자 이름을 입력해 주세요.");
        if (name.length > 40) return setError("검토자 이름은 40자 이내로 입력해 주세요.");
        setReviewer(name);
      }}
    >
      <label htmlFor="values-reviewer" className="break-keep">검토자 이름을 입력해야 확인·수정할 수 있습니다. 기록에 이 이름이 남습니다.</label>
      <Input
        id="values-reviewer"
        autoComplete="name"
        className="w-40"
        value={draft}
        aria-invalid={!!error}
        aria-describedby={error ? "values-reviewer-error" : undefined}
        onChange={(e) => {
          setDraft(e.target.value);
          setError(null);
        }}
      />
      <Button type="submit" size="md" className="min-h-8 px-2.5">저장</Button>
      {error && <span id="values-reviewer-error" className="text-red">{error}</span>}
    </form>
  );
}
