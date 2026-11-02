"use client";

import { Button, Callout } from "@/components/ui";

/** 판정·성분 목록을 불러오지 못했을 때의 오류 상자와 다시 불러오기 */
export function LoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Callout tone="danger" role="alert" className="flex flex-wrap items-center gap-2">
      <span>{message}</span>
      <Button onClick={onRetry}>다시 불러오기</Button>
    </Callout>
  );
}
