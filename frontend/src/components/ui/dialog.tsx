"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";

/**
 * 확인 대화상자: 브라우저 <dialog> 를 모달로 연다 (Esc 로 닫기, 초점 가두기는 브라우저가 맡는다).
 * 그림자 대신 얇은 선과 어두운 뒷배경으로 띄운다. 좁은 화면에서는 브라우저 기본 최대 너비가 여백을 남긴다.
 */
export function Dialog({
  open,
  onClose,
  title,
  children,
  actions,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      aria-labelledby={titleId}
      className="m-auto w-120 rounded-md border border-line bg-white p-6 text-ink backdrop:bg-ink/30"
    >
      <h2 id={titleId} className="text-lg font-bold">
        {title}
      </h2>
      {children && <div className="mt-2 text-mut">{children}</div>}
      {actions && <div className="mt-5 flex flex-wrap justify-end gap-2">{actions}</div>}
    </dialog>
  );
}
