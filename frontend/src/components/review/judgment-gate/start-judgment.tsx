"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { isJudgmentApiMissing, judgmentKeys, postToJudgment } from "@/api/judgment";
import { Button, buttonStyles } from "@/components/ui";
import { useReviewer } from "@/lib/reviewer";
import { routes } from "@/lib/routes";
import { JudgmentNotice } from "./notice";

/** 아직 판정하지 않은 문서. 검토자 이름이 있어야 판정으로 넘길 수 있다 */
export function StartJudgment({ docId, paneTitle }: { docId: string; paneTitle: string }) {
  const client = useQueryClient();
  const reviewer = useReviewer();
  const start = useMutation({
    mutationFn: () => postToJudgment(docId, reviewer),
    onSuccess: () => client.invalidateQueries({ queryKey: judgmentKeys.status(docId) }),
  });
  return (
    <JudgmentNotice paneTitle={paneTitle} title="아직 판정하지 않았습니다">
      <p className="text-mut">추출값을 먼저 확인하거나, 지금 값으로 바로 판정할 수 있습니다.</p>
      <div className="flex flex-wrap justify-center gap-2">
        <Link href={routes.review(docId, "values")} className={buttonStyles()}>
          추출값 확인
        </Link>
        <Button variant="primary" disabled={!reviewer || start.isPending} onClick={() => start.mutate()}>
          {start.isPending ? "넘기는 중…" : "판정으로 넘기기"}
        </Button>
      </div>
      {!reviewer && <p className="text-sm text-mut">판정으로 넘기려면 머리줄에서 검토자 이름을 정해 주세요.</p>}
      {start.isError && (
        <p role="alert" className="text-sm break-words text-red">
          {isJudgmentApiMissing(start.error) ? "판정으로 넘기는 서버 기능이 아직 연결되지 않았습니다." : `넘기지 못했습니다: ${start.error.message}`}
        </p>
      )}
    </JudgmentNotice>
  );
}
