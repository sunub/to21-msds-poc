"use client";

import { useSearchParams } from "next/navigation";
import type { ReactNode } from "react";
import { Stepper } from "@/components/ui";
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
 * 문서 한 건을 다루는 화면의 공통 틀: 머리줄, 추출→검수→저장 단계, 본문.
 * ?doc= 이 없으면 본문 대신 안내를 보여 준다.
 */
export function DocFrame({
  stage,
  children,
}: {
  stage: Stage;
  children: (doc: string) => ReactNode;
}) {
  const doc = useDocId();
  return (
    <>
      <AppHeader doc={doc ?? undefined} />
      <div className="border-b border-line bg-white">
        <div className="mx-auto max-w-page px-8">
          <Stepper steps={STAGES} current={stage} />
        </div>
      </div>
      <main className="mx-auto flex max-w-page flex-col gap-5 px-8 pt-7 pb-14">
        {doc ? (
          children(doc)
        ) : (
          <Slot title="문서를 고르지 않았습니다" note="목록에서 문서를 골라 들어와 주세요." />
        )}
      </main>
    </>
  );
}
