"use client";

import { Suspense } from "react";
import { ReviewStateProvider, useReviewState } from "@/components/review/review-state";
import { SaveView } from "@/components/save/save-view";
import { DocFrame, useDocId } from "@/components/shell/doc-frame";

/** 머리의 "2 검수" 칸에 처리 상태를 적는다 (처리 상태를 읽은 뒤에만) */
function SaveFrame() {
  const { ready, unresolvedCount } = useReviewState();
  const left = unresolvedCount(2) + unresolvedCount(15);
  const note = ready ? (left === 0 ? "· 판정 모두 처리" : `· 판정 미검토 ${left}건`) : undefined;
  return (
    <DocFrame stage="save" notes={{ review: note }}>
      {(doc) => <SaveView docId={doc} />}
    </DocFrame>
  );
}

function SaveRoot() {
  const doc = useDocId();
  // 검수 화면에서 남긴 처리 상태(sessionStorage)를 문서별로 읽기 위해 같은 상태 공급자를 쓴다
  if (!doc) return <DocFrame stage="save">{() => null}</DocFrame>;
  return (
    <ReviewStateProvider key={doc} docId={doc}>
      <SaveFrame />
    </ReviewStateProvider>
  );
}

/** 3 저장 (3.1 모두 처리, 3.2 미검토 포함): 판정 요약, 처리 상태, DB 저장, PDF 출력. */
export default function SavePage() {
  return (
    <Suspense>
      <SaveRoot />
    </Suspense>
  );
}
