import { Button } from "@/components/ui";
import { JudgmentNotice } from "./notice";

export function JudgmentFailed({
  docId,
  paneTitle,
  error,
  onRetry,
}: {
  docId: string;
  paneTitle: string;
  error: string | null;
  onRetry: () => void;
}) {
  return (
    <JudgmentNotice paneTitle={paneTitle} title="판정하지 못했습니다" alert>
      <p className="break-words text-mut">
        문서 {docId}
        {error && ` · ${error}`}
      </p>
      <p className="text-mut">다시 불러와도 같으면 개발 담당에게 위 내용을 알려 주세요.</p>
      <Button onClick={onRetry}>다시 불러오기</Button>
    </JudgmentNotice>
  );
}
