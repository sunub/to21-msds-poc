import { ApiContractError, ApiRequestError } from "@/api/client";
import { Button } from "@/components/ui";
import { JudgmentNotice } from "./notice";

export function JudgmentError({ paneTitle, error, onRetry }: { paneTitle: string; error: unknown; onRetry: () => void }) {
  const message =
    error instanceof ApiContractError
      ? "판정 응답이 화면 약속과 달라 틀린 판정을 보여 주지 않으려고 표시하지 않았습니다."
      : error instanceof ApiRequestError
        ? error.message
        : "서버에 연결하지 못했습니다.";
  return (
    <JudgmentNotice paneTitle={paneTitle} title="판정 결과를 불러오지 못했습니다" alert>
      <p className="break-words text-mut">{message}</p>
      {error instanceof ApiContractError && <p className="text-sm break-words text-mut">{error.message}</p>}
      <Button onClick={onRetry}>다시 불러오기</Button>
    </JudgmentNotice>
  );
}
