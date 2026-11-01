import Link from "next/link";
import { AppHeader } from "@/components/shell/app-header";
import { Slot } from "@/components/shell/slot";
import { Card } from "@/components/ui";
import { routes } from "@/lib/routes";

// 뼈대 확인용: 데이터 설계 전이라 목록이 비어 있어 화면 사이를 오갈 길을 따로 둔다.
const PREVIEW_DOC = "T21-002";

/** 1.1 추출 · 목록: PDF 올리기, 검증 조건, 작업한 문서. */
export default function HomePage() {
  return (
    <>
      <AppHeader />
      <main className="mx-auto flex max-w-page flex-col gap-5 px-8 pt-7 pb-14">
        <section>
          <h1 className="text-2xl font-bold">새 문서 검수</h1>
          <p className="mt-1 text-mut">PDF를 올리면 추출, 검수, 저장이 이어서 진행됩니다.</p>
        </section>

        <div className="grid gap-4 lg:grid-cols-3">
          <Slot title="PDF 올리기" note="끌어 놓기 영역과 파일 선택 버튼이 들어올 자리" className="min-h-40 lg:col-span-2" />
          <Slot title="검증 조건" note="기준일과 검토자 이름 입력이 들어올 자리" className="min-h-40" />
        </div>

        <section className="flex flex-col gap-3">
          <h2 className="text-xl font-bold">작업한 문서</h2>
          <Slot title="문서 목록" note="전체·진행 중·완료 보기 전환과 문서 표(문서, 단계, 진행, 데이터 등급, 마지막 작업)가 들어올 자리" />
        </section>

        <Card>
          <h2 className="text-lg font-bold">화면 둘러보기 (뼈대 확인용)</h2>
          <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1">
            <li><Link href={routes.extract(PREVIEW_DOC)}>1 추출 진행</Link></li>
            <li><Link href={routes.reviewMode(PREVIEW_DOC)}>2.1 검수 방식 선택</Link></li>
            <li><Link href={routes.review(PREVIEW_DOC, "values")}>2.2 추출값 확인</Link></li>
            <li><Link href={routes.review(PREVIEW_DOC, "hazard")}>2.3 2항 판정</Link></li>
            <li><Link href={routes.review(PREVIEW_DOC, "regulation")}>2.4 15항 판정</Link></li>
            <li><Link href={routes.save(PREVIEW_DOC)}>3 저장</Link></li>
            <li><Link href="/design-system/">디자인 시스템</Link></li>
          </ul>
        </Card>
      </main>
    </>
  );
}
