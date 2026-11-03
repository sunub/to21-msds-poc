"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { judgmentStatusQuery, judgmentViewQuery } from "@/api/judgment";
import { Button, Dialog } from "@/components/ui";
import { unreviewedFindings } from "@/lib/save";
import { routes } from "@/lib/routes";

const SHOWN = 8;

/**
 * 2.5 저장 전 경고: 처리하지 않은 판정이 남았을 때만 띄운다 (탭이 건수를 세어 연다).
 * 저장을 막지 않고, 처리하러 가기와 미검토로 두고 저장하기 중에서 고르게 한다.
 * 목록은 열릴 때 판정에서 읽는다. 무엇이 처리할 판정인지는 탭과 같은 규칙(lib/regulation.ts)이다.
 */
export function SaveGuardDialog({
  docId,
  open,
  onClose,
  onSave,
}: {
  docId?: string;
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
      <p>저장하면 아래 판정은 &quot;미검토&quot;로 남습니다. 지금 처리하고 저장하거나, 그대로 저장할 수 있습니다.</p>
      {open && docId && <UnreviewedList docId={docId} onClose={onClose} />}
    </Dialog>
  );
}

function UnreviewedList({ docId, onClose }: { docId: string; onClose: () => void }) {
  const status = useQuery(judgmentStatusQuery(docId));
  const latest = status.data?.latest_version ?? null;
  const view = useQuery({ ...judgmentViewQuery(docId, latest ?? 1), enabled: latest !== null });
  if (!view.data) return null;
  const todo = unreviewedFindings(view.data);
  if (todo.length === 0) return null;
  return (
    <ul className="m-0 mt-3 flex list-none flex-col p-0 text-sm text-ink">
      {todo.slice(0, SHOWN).map((f) => (
        <li key={f.id} className="flex items-center gap-3 border-t border-line2 py-2">
          <span className="w-9 flex-none text-mut">{f.section}항</span>
          <span className="min-w-0 flex-1 break-words">{f.label}</span>
          <span className="flex-none text-mut">{f.verdict}</span>
          <Link
            href={routes.review(docId, f.section === "2" ? "hazard" : "regulation", { finding: f.id })}
            onClick={onClose}
            aria-label={`${f.section}항 ${f.label} 판정으로 이동`}
            className="flex-none"
          >
            이동 ›
          </Link>
        </li>
      ))}
      {todo.length > SHOWN && <li className="border-t border-line2 py-2 text-mut">외 {todo.length - SHOWN}건</li>}
    </ul>
  );
}
