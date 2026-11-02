"use client";

import Link from "next/link";
import { Button, buttonStyles } from "@/components/ui";
import { routes } from "@/lib/routes";

/** 판정 탭 아래쪽 오른쪽 버튼: 추출값 탭으로 돌아가는 링크와 저장하기 */
export function FootActions({ docId, onSave }: { docId: string; onSave: () => void }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Link href={routes.review(docId, "values")} className={buttonStyles({ size: "lg" })}>
        추출값 확인하러 가기
      </Link>
      <Button variant="primary" size="lg" onClick={onSave}>
        저장하기
      </Button>
    </div>
  );
}
