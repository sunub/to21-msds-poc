"use client";

import { Suspense } from "react";
import { SaveBody } from "@/components/save/save-body";
import { DocFrame } from "@/components/shell/doc-frame";

/** 3.1~3.2 저장: 판정 요약, 처리 상태, DB 저장, PDF 출력. 미검토가 남아도 같은 화면에서 표시만 달리한다. */
export default function SavePage() {
  return (
    <Suspense>
      <DocFrame stage="save">{(doc) => <SaveBody docId={doc} />}</DocFrame>
    </Suspense>
  );
}
