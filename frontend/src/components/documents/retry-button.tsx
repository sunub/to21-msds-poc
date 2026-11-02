"use client";

import { useState } from "react";
import { Button, Dialog, type ButtonProps } from "@/components/ui";
import { useRetryDocument } from "@/hooks/use-retry-document";

/** 다시 돌리기. 모든 항을 모델에 다시 호출하므로 한 번 묻는다. 목록과 진행 화면이 함께 쓴다 */
export function RetryButton({
  docId,
  filename,
  variant,
  size,
  label = "다시 시도",
}: {
  docId: string;
  filename: string;
  variant?: ButtonProps["variant"];
  size?: ButtonProps["size"];
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  const retry = useRetryDocument(docId, () => setOpen(false));

  return (
    <>
      <Button variant={variant} size={size} onClick={() => setOpen(true)}>
        {label}
      </Button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="처음부터 다시 돌릴까요?"
        actions={
          <>
            <Button onClick={() => setOpen(false)} disabled={retry.isPending}>
              취소
            </Button>
            <Button variant="primary" onClick={() => retry.mutate()} disabled={retry.isPending} aria-busy={retry.isPending}>
              {retry.isPending ? "요청 중" : "다시 돌리기"}
            </Button>
          </>
        }
      >
        <p>{filename} 의 모든 항을 모델에 다시 호출합니다. 성공한 항도 다시 돌리며 이전 결과는 덮어씁니다. 확인·수정 기록은 따로 보관되고 새 결과에는 이어지지 않습니다.</p>
        {retry.isError && (
          <p role="alert" className="mt-2 text-sm text-red">
            다시 돌리지 못했습니다. 서버가 켜져 있는지 확인하고 다시 눌러 주세요.
          </p>
        )}
      </Dialog>
    </>
  );
}
