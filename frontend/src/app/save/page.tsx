"use client";

import Link from "next/link";
import { Suspense } from "react";
import { DocFrame } from "@/components/shell/doc-frame";
import { Foot, Row } from "@/components/shell/layout";
import { Slot } from "@/components/shell/slot";
import { buttonStyles } from "@/components/ui";
import { routes } from "@/lib/routes";

/** 3.1~3.2 저장: 판정 요약, 처리 상태, DB 저장, PDF 출력. 미검토가 남아도 같은 화면에서 표시만 달리한다. */
export default function SavePage() {
  return (
    <Suspense>
      <DocFrame stage="save">
        {(doc) => (
          <div className="flex flex-col gap-5">
            <section>
              <h1 className="text-2xl font-bold">검토 결과 저장</h1>
              <p className="mt-1 text-mut">결과를 데이터베이스에 저장하고, 재생성 MSDS와 판정이 담긴 PDF로 내려받습니다.</p>
            </section>
            <Slot title="2차 판정 요약과 처리 상태" note="판정 건수, 미검토·처리 건수, 추출값 검수 여부가 들어올 자리" />
            <Row className="items-stretch">
              <Slot title="데이터베이스에 저장" note="저장 상태, 저장 시각, 값의 출처별 칸 수, 다시 저장·JSON 내려받기가 들어올 자리" className="min-h-56 grow basis-105" />
              <Slot title="PDF로 출력" note="PDF 구성과 포함 항목 선택, 미리 보기가 들어올 자리" className="min-h-56 grow basis-105" />
            </Row>
            <Foot>
              <Link href={routes.review(doc)} className={buttonStyles({ size: "lg" })}>
                판정으로 돌아가기
              </Link>
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
