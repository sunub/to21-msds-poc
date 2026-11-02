"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Suspense } from "react";
import { documentDetailQuery } from "@/api/documents";
import type { DocumentDetail } from "@/api/schemas";
import { DocFrame } from "@/components/shell/doc-frame";
import { Foot, Row } from "@/components/shell/layout";
import { Card, Skeleton, buttonStyles } from "@/components/ui";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import { allSectionsFailed, inputType } from "@/lib/status";

function ModeBody({ docId }: { docId: string }) {
  const { data: doc } = useQuery(documentDetailQuery(docId));
  if (!doc) return <Skeleton className="w-2/3" />;
  if (doc.status !== "done" || allSectionsFailed(doc)) {
    return (
      <p className="text-mut">
        {doc.status === "done" ? "모든 항의 추출이 실패해 검수할 값이 없습니다." : "추출이 끝나면 검수 방식을 고를 수 있습니다."}{" "}
        <Link href={routes.extract(docId)}>진행 화면으로 가기</Link>
      </p>
    );
  }
  return <Mode doc={doc} />;
}

/** 2.1 검수 방식 선택: 텍스트층으로 입력 유형을 판정해 권장 순서를 안내한다. 어느 쪽을 골라도 된다 */
function Mode({ doc }: { doc: DocumentDetail }) {
  const type = inputType(doc.text_layer);
  const { done, failed, needs_review: review, total } = doc.counts;
  return (
    <div className="flex flex-col gap-5">
      <section>
        <h1 className="text-2xl font-bold">추출이 끝났습니다. 다음 단계를 선택해 주세요</h1>
        <p className="mt-1 text-mut">문서 종류에 따라 추출값 확인을 건너뛸 수 있습니다.</p>
      </section>
      <Card className="flex flex-col gap-3">
        <dl className="m-0 flex flex-wrap gap-x-12 gap-y-3">
          <div>
            <dt className="text-sm text-mut">입력 유형</dt>
            <dd className="m-0 font-bold">{type.label}</dd>
          </div>
          <div className="min-w-0 flex-1 basis-80">
            <dt className="text-sm text-mut">추출 상태</dt>
            <dd className="m-0">
              {total}개 항 중 {done}개 완료
              {failed > 0 && <span className="text-red"> · 실패 {failed}개</span>}
              {review > 0 && <span className="text-amb-text"> · 검토 필요 {review}개</span>} · {type.note}
            </dd>
          </div>
        </dl>
        <p className="text-sm text-sub">
          이 문서는 {type.label}(으)로 확인되어{" "}
          <strong>{type.recommendValues ? "추출값 확인부터" : "판정으로 바로 가기"}</strong>를 권장합니다. 다른 방식을 골라도 됩니다.
        </p>
      </Card>
      <Row className="items-stretch">
        <ModeCard
          title="추출값 확인부터 하기"
          recommended={type.recommendValues}
          body="재생성한 16항 MSDS를 원문과 나란히 놓고 칸마다 확인하고 고칩니다. 끝나면 판정 단계로 넘어갑니다."
          flow='확인한 칸은 "확인함", 고친 칸은 "수정됨"으로 기록됩니다.'
          href={routes.review(doc.id, "values")}
          action="추출값 확인 시작하기"
        />
        <ModeCard
          title="판정으로 바로 가기"
          recommended={!type.recommendValues}
          body="추출값 확인을 건너뛰고 2항 유해성·위험성과 15항 법적 규제 판정부터 확인합니다."
          flow='건너뛴 추출값은 "미검수"로 남고, 검수 화면의 추출값 탭에서 언제든 확인할 수 있습니다.'
          href={routes.review(doc.id, "hazard")}
          action="판정 확인 시작하기"
        />
      </Row>
      <Foot>
        <p className="text-mut">나중에 바꿀 수 있습니다. 검수 화면의 추출값 탭에서 추출값 확인을 시작할 수 있습니다.</p>
        <Link href={routes.home()} className={buttonStyles({ size: "lg" })}>
          목록으로
        </Link>
      </Foot>
    </div>
  );
}

function ModeCard({
  title,
  recommended,
  body,
  flow,
  href,
  action,
}: {
  title: string;
  recommended: boolean;
  body: string;
  flow: string;
  href: string;
  action: string;
}) {
  return (
    <Card className={cn("flex grow basis-105 flex-col gap-3", recommended && "border-blue")}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-bold">{title}</h2>
        {recommended && <span className="text-sm font-medium text-blue2">권장</span>}
      </div>
      <p className="text-mut">{body}</p>
      <p className="text-sm text-mut">{flow}</p>
      <Link href={href} className={cn("mt-auto", buttonStyles({ variant: recommended ? "primary" : "outline" }))}>
        {action}
      </Link>
    </Card>
  );
}

export default function ReviewModePage() {
  return (
    <Suspense>
      <DocFrame stage="review">{(doc) => <ModeBody docId={doc} />}</DocFrame>
    </Suspense>
  );
}
