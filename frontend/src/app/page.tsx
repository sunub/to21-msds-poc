import Link from "next/link";
import { DocumentList } from "@/components/home/document-list";
import { UploadForm } from "@/components/home/upload-form";
import { AppHeader } from "@/components/shell/app-header";
import { PageMain } from "@/components/shell/layout";
import { routes } from "@/lib/routes";

// 뼈대 확인용: 검수·저장 화면은 아직 데이터가 붙지 않아 따로 오갈 길을 둔다.
const PREVIEW_DOC = "T21-002";

// 목록 화면은 1120px 폭 (templates 1.1)
const WIDTH = "max-w-280";

/** 1.1 추출 · 목록: PDF 올리기와 검증 조건, 작업한 문서. */
export default function HomePage() {
  return (
    <>
      <AppHeader width={WIDTH} />
      <PageMain width={WIDTH} className="gap-10 pt-10">
        <section>
          <h1 className="text-2xl font-bold">새 문서 검수</h1>
          <p className="text-mut">PDF를 올리면 추출, 검수, 저장이 이어서 진행됩니다. 파일은 이 서버 밖으로 나가지 않습니다.</p>
        </section>

        <UploadForm />
        <DocumentList />

        <nav aria-label="뼈대 확인용 화면 목록" className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
          <span className="text-mut">뼈대 확인용:</span>
          <Link href={routes.reviewMode(PREVIEW_DOC)}>2.1 검수 방식 선택</Link>
          <Link href={routes.review(PREVIEW_DOC, "values")}>2.2 추출값 확인</Link>
          <Link href={routes.review(PREVIEW_DOC, "hazard")}>2.3 2항 판정</Link>
          <Link href={routes.review(PREVIEW_DOC, "regulation")}>2.4 15항 판정</Link>
          <Link href={routes.save(PREVIEW_DOC)}>3 저장</Link>
          <Link href="/design-system/">디자인 시스템</Link>
        </nav>
      </PageMain>
    </>
  );
}
