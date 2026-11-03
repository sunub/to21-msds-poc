"use client";

import { Suspense } from "react";
import { JudgmentGate } from "@/components/review/judgment-gate";
import { SaveView } from "@/components/save/save-view";
import { DocFrame } from "@/components/shell/doc-frame";
import { Pane } from "@/components/shell/layout";
import { Skeleton } from "@/components/ui";

/** 3.1~3.2 저장: 판정 요약, 처리 상태, DB 저장, PDF 출력. 미검토가 남아도 같은 화면에서 표시만 달리한다. */
export default function SavePage() {
  return (
    <Suspense>
      <DocFrame stage="save">
        {(doc) => (
          <JudgmentGate
            docId={doc}
            tab="hazard"
            paneTitle="검토 결과 저장"
            what="저장 화면"
            loading={() => (
              <Pane title="검토 결과 저장">
                <Skeleton className="w-2/3" />
              </Pane>
            )}
          >
            {(ready) => <SaveView docId={doc} ready={ready} />}
          </JudgmentGate>
        )}
      </DocFrame>
    </Suspense>
  );
}
