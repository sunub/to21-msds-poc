"use client";

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import type { ReactNode } from "react";
import { ApiRequestError } from "@/api/client";
import { documentDetailQuery } from "@/api/documents";
import type { DocumentDetail } from "@/api/schemas";
import { Stepper } from "@/components/ui";
import { cn } from "@/lib/cn";
import { useJudgmentGlance } from "@/hooks/use-judgment-glance";
import { headerNote, judgmentLabel, reviewNote, saveNote } from "@/lib/doc-glance";
import { stageNote } from "@/lib/status";
import { AppHeader } from "./app-header";
import { Slot } from "./slot";

export type Stage = "extract" | "review" | "save";

const STAGES: { id: Stage; label: string }[] = [
  { id: "extract", label: "추출" },
  { id: "review", label: "검수" },
  { id: "save", label: "저장" },
];

export function useDocId() {
  return useSearchParams().get("doc");
}

/**
 * 문서 한 건을 다루는 화면의 공통 틀 (templates 의 .hd → .stp → .wrap).
 * 머리줄, 단계, 본문이 같은 최대 너비(width)를 쓴다. 추출 화면은 1280px(max-w-320).
 * 머리줄과 단계 문구는 진행 상태 응답으로 채운다 (본문과 같은 쿼리라 요청은 한 번이다).
 * ?doc= 이 없거나, 문서가 없거나, 서버에 닿지 못하면 본문 대신 안내를 보여 준다.
 */
export function DocFrame({
  stage,
  notes,
  width = "max-w-page",
  children,
}: {
  stage: Stage;
  notes?: Partial<Record<Stage, string>>;
  width?: string;
  children: (doc: string) => ReactNode;
}) {
  const doc = useDocId();
  const { data, error } = useQuery({ ...documentDetailQuery(doc ?? ""), enabled: !!doc });
  // 판정 쪽 값(등급·판정 상태·미검토 수·저장본)은 서버가 줄 때만 쓴다. 판정 서비스가 없으면 그 칸만 숨는다
  const glance = useJudgmentGlance(doc, { extractionDone: data?.status === "done", withView: stage !== "extract" });
  const stageNotes = { ...(data ? defaultNotes(data, glance) : {}), ...notes };
  return (
    <>
      <AppHeader doc={data ? headerTitle(data) : (doc ?? undefined)} note={data && headerNoteOf(data, glance)} width={width} />
      <div className="border-b border-line bg-white print:hidden">
        <div className={cn("mx-auto px-8", width)}>
          <Stepper steps={STAGES.map((s) => ({ ...s, note: stageNotes[s.id] }))} current={stage} />
        </div>
      </div>
      <main className={cn("mx-auto flex flex-col gap-5 px-8 pt-7 pb-14 print:max-w-none print:p-0", width)}>
        {!doc ? (
          <Slot title="문서를 고르지 않았습니다" note="목록에서 문서를 골라 들어와 주세요." />
        ) : !data && error ? (
          error instanceof ApiRequestError && error.status === 404 ? (
            <Slot title="문서를 찾을 수 없습니다" note={`${doc} 문서가 없습니다. 목록에서 다시 골라 주세요.`} />
          ) : (
            <Slot title="서버에 연결하지 못했습니다" note="추출 API 서버가 켜져 있는지 확인해 주세요. 연결되면 이어서 보여 줍니다." />
          )
        ) : (
          children(doc)
        )}
      </main>
    </>
  );
}

function stem(filename: string) {
  return filename.replace(/\.pdf$/i, "");
}

type Glance = ReturnType<typeof useJudgmentGlance>;

/** 제목: 문서 번호와 제품명 (제품명을 서버가 아직 안 주면 파일 이름) */
function headerTitle(doc: DocumentDetail) {
  return doc.product_name ? `${doc.id} ${doc.product_name}` : stem(doc.filename);
}

/** 머리줄 옆 글: 파일 · 쪽 수 · 데이터 등급 · 추출값 검수 · 판정 상태. 값이 없는 칸은 숨긴다 (lib/doc-glance.ts) */
function headerNoteOf(doc: DocumentDetail, glance: Glance) {
  return headerNote(doc, glance.grade, judgmentLabel(glance.status, glance.unreviewed));
}

/** 단계 띠: 추출은 진행 상태(단계 수는 응답 값), 검수는 추출값 확인 여부와 판정 상태, 저장은 저장본 번호 */
function defaultNotes(doc: DocumentDetail, glance: Glance): Partial<Record<Stage, string>> {
  if (doc.status !== "done") return { extract: stageNote(doc), review: "· 추출이 끝나면 열림" };
  return { extract: stageNote(doc), review: reviewNote(doc, glance.status, glance.unreviewed), save: saveNote(glance.status) };
}
