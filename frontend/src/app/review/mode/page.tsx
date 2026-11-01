"use client";

import Link from "next/link";
import { Suspense } from "react";
import { DocFrame } from "@/components/shell/doc-frame";
import { Foot, Row } from "@/components/shell/layout";
import { Slot } from "@/components/shell/slot";
import { Card, buttonStyles } from "@/components/ui";
import { routes } from "@/lib/routes";

/** 2.1 검수 방식 선택: 입력 유형(디지털 PDF·스캔본)에 따라 권장 순서를 안내한다. */
export default function ReviewModePage() {
  return (
    <Suspense>
      <DocFrame stage="review">
        {(doc) => (
          <div className="flex flex-col gap-5">
            <section>
              <h1 className="text-2xl font-bold">추출이 끝났습니다. 다음 단계를 선택해 주세요</h1>
              <p className="mt-1 text-mut">문서 종류에 따라 추출값 확인을 건너뛸 수 있습니다.</p>
            </section>
            <Slot title="입력 유형과 추출 상태" note="디지털 PDF·스캔본 판별과 권장 방식이 들어올 자리" />
            <Row className="items-stretch">
              <Card className="flex grow basis-105 flex-col gap-3">
                <h2 className="text-lg font-bold">추출값 확인부터 하기</h2>
                <p className="text-mut">재생성한 16항 MSDS를 원문과 나란히 놓고 칸마다 확인하고 고칩니다.</p>
                <p className="text-sm text-mut">추출값 확인 → 2항 판정 → 15항 판정 → 저장</p>
                <Link href={routes.review(doc, "values")} className={buttonStyles({ variant: "outline" })}>
                  추출값 확인 시작하기
                </Link>
              </Card>
              <Card className="flex grow basis-105 flex-col gap-3">
                <h2 className="text-lg font-bold">판정으로 바로 가기</h2>
                <p className="text-mut">추출값 확인을 건너뛰고 2항과 15항 판정부터 확인합니다.</p>
                <p className="text-sm text-mut">건너뛴 추출값은 &quot;미검수&quot;로 남습니다.</p>
                <Link href={routes.review(doc, "hazard")} className={buttonStyles({ variant: "outline" })}>
                  판정 확인 시작하기
                </Link>
              </Card>
            </Row>
            <Foot>
              <p className="text-mut">나중에 바꿀 수 있습니다. 검수 화면의 추출값 탭에서 추출값 확인을 시작할 수 있습니다.</p>
              <Link href={routes.home()} className={buttonStyles({ size: "lg" })}>
                목록으로
              </Link>
            </Foot>
          </div>
        )}
      </DocFrame>
    </Suspense>
  );
}
