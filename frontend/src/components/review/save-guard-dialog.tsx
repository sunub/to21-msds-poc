"use client";

import { Button, Dialog } from "@/components/ui";

/**
 * 2.5 저장 전 경고: 처리하지 않은 판정이 남았을 때만 띄운다.
 * 저장을 막지 않고, 처리하러 가기와 미검토로 두고 저장하기 중에서 고르게 한다.
 */
export function SaveGuardDialog({
  open,
  onClose,
  onSave,
}: {
  open: boolean;
  onClose: () => void;
  onSave: () => void;
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="처리하지 않은 판정이 남아 있습니다"
      actions={
        <>
          <Button onClick={onSave}>미검토로 두고 저장하기</Button>
          <Button variant="primary" onClick={onClose}>
            판정 처리하러 가기
          </Button>
        </>
      }
    >
      미검토 판정 목록이 들어올 자리
    </Dialog>
  );
}
