"use client";

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import type { ReactNode } from "react";
import { ApiRequestError } from "@/api/client";
import { documentDetailQuery } from "@/api/documents";
import type { DocumentDetail } from "@/api/schemas";
import { Stepper } from "@/components/ui";
import { stageNote } from "@/lib/status";
import { AppHeader } from "./app-header";
import { PageMain } from "./layout";
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
  fill,
  children,
}: {
  stage: Stage;
  notes?: Partial<Record<Stage, string>>;
  width?: string;
  /** 본문을 화면 높이에 꼭 맞춘다 (PageMain) */
  fill?: boolean;
  children: (doc: string) => ReactNode;
}) {
  const doc = useDocId();
  const { data, error } = useQuery({ ...documentDetailQuery(doc ?? ""), enabled: !!doc });
  const stageNotes = { ...(data ? defaultNotes(data) : {}), ...notes };
  return (
    <>
      <AppHeader
        doc={data ? stem(data.filename) : (doc ?? undefined)}
        center={<Stepper variant="pill" steps={STAGES.map((s) => ({ ...s, note: stageNotes[s.id] }))} current={stage} />}
        badge={
          stage === "review" && data?.as_of ? (
            <span className="inline-flex items-center whitespace-nowrap rounded-full border border-line bg-white px-2.5 py-1 text-xs text-mut">
              기준일 {data.as_of}
            </span>
          ) : undefined
        }
        width={width}
      />
      <PageMain width={width} fill={fill} className="print:max-w-none print:p-0">
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
      </PageMain>
    </>
  );
}

function stem(filename: string) {
  return filename.replace(/\.pdf$/i, "");
}

function defaultNotes(doc: DocumentDetail): Partial<Record<Stage, string>> {
  return { extract: stageNote(doc), review: doc.status === "done" ? undefined : "· 추출이 끝나면 열림" };
}
