import Link from "next/link";
import { buttonStyles } from "@/components/ui";
import { routes } from "@/lib/routes";
import { JudgmentNotice } from "./notice";

export function NotExtracted({ docId, paneTitle }: { docId: string; paneTitle: string }) {
  return (
    <JudgmentNotice paneTitle={paneTitle} title="추출이 끝나야 판정할 수 있습니다">
      <Link href={routes.extract(docId)} className={buttonStyles()}>
        추출 진행 보기
      </Link>
    </JudgmentNotice>
  );
}
