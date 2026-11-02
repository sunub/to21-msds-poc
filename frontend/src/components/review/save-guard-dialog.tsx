"use client";

import { Button, Dialog } from "@/components/ui";
import { useReviewState } from "./review-state";
import { UnresolvedList } from "./unresolved-list";

/**
 * 2.5 저장 전 경고: 처리하지 않은 판정이 남았을 때만 띄운다 (없으면 호출한 쪽이 바로 저장 화면으로 보낸다).
 * 저장을 막지 않고, 처리하러 가기와 미검토로 두고 저장하기 중에서 고르게 한다.
 * 목록의 "이동"을 누르면 대화상자를 닫고 그 판정으로 간다.
 */
export function SaveGuardDialog({
  docId,
  open,
  onClose,
  onSave,
}: {
  docId: string;
  open: boolean;
  onClose: () => void;
  onSave: () => void;
}) {
  const { unresolvedCount } = useReviewState();
  const total = unresolvedCount(2) + unresolvedCount(15);
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={`처리하지 않은 판정이 ${total}건 있습니다`}
      actions={
        <>
          <Button onClick={onSave}>미검토로 두고 저장하기</Button>
          <Button variant="primary" onClick={onClose}>
            판정 처리하러 가기
          </Button>
        </>
      }
    >
      <p className="mb-3 leading-relaxed [word-break:keep-all]">
        저장하면 아래 판정은 &quot;미검토&quot;로 남습니다. 지금 처리하고 저장하거나, 그대로 저장할 수 있습니다.
      </p>
      {/* 닫혀 있는 동안은 그리지 않는다 (같은 목록이 화면 밖에 한 벌 더 남지 않게) */}
      {open && (
        <div className="max-h-64 overflow-y-auto">
          <UnresolvedList docId={docId} onNavigate={onClose} />
        </div>
      )}
    </Dialog>
  );
}
