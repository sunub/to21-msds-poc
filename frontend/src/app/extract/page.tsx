"use client";

import Link from "next/link";
import { Suspense } from "react";
import { DocFrame } from "@/components/shell/doc-frame";
import { Slot } from "@/components/shell/slot";
import { SourcePane, Split } from "@/components/shell/split";
import { buttonStyles } from "@/components/ui";
import { routes } from "@/lib/routes";

/** 1.2~1.3 추출 진행: 원문 미리 읽기와 쪽별 추출 상태. */
export default function ExtractPage() {
  return (
    <Suspense>
      <DocFrame stage="extract">
        {(doc) => (
          <Split source={<SourcePane note="전처리가 끝난 쪽부터 읽을 수 있는 자리" />}>
            <Slot title="쪽별 추출 상태" note="쪽마다 전처리·추출 상태와 전체 진행이 들어올 자리" className="min-h-80" />
            <p className="text-sm text-mut">추출 중에도 이 화면을 닫을 수 있습니다. 목록에서 이어서 볼 수 있습니다.</p>
            <div className="flex gap-2">
              <Link href={routes.home()} className={buttonStyles()}>
                목록으로
              </Link>
              <Link href={routes.reviewMode(doc)} className={buttonStyles({ variant: "primary" })}>
                검수로 넘어가기
              </Link>
            </div>
          </Split>
        )}
      </DocFrame>
    </Suspense>
  );
}
