import { DocumentList } from "@/components/home/document-list";
import { UploadForm } from "@/components/home/upload-form";
import { AppHeader } from "@/components/shell/app-header";
import { PageMain } from "@/components/shell/layout";

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
      </PageMain>
    </>
  );
}
