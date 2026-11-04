import Link from "next/link";
import { buttonStyles } from "@/components/ui";
import { routes, type ReviewTab } from "@/lib/routes";
import { JudgmentNotice } from "./notice";

/** 처음 켤 때만 쓰는 대역 안내 링크. 제품 빌드에서는 조건이 거짓이라 빠진다 */
const DEV = process.env.NODE_ENV === "development";

export function NotConnected({ docId, tab, paneTitle, what }: { docId: string; tab: ReviewTab; paneTitle: string; what: string }) {
  return (
    <JudgmentNotice paneTitle={paneTitle} title="판정 서비스가 아직 연결되지 않았습니다">
      <p className="text-mut">판정 API가 준비되면 이 화면에서 {what}을 바로 볼 수 있습니다. 그동안 추출값은 확인할 수 있습니다.</p>
      <div className="flex flex-wrap justify-center gap-2">
        <Link href={routes.review(docId, "values")} className={buttonStyles()}>
          추출값 확인
        </Link>
        {DEV && (
          <Link href={`${routes.review(docId, tab)}&judgmentMock=ready`} className={buttonStyles({ variant: "outline" })}>
            개발용 가상 판정 보기
          </Link>
        )}
      </div>
    </JudgmentNotice>
  );
}
