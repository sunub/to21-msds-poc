"use client";

import { useState } from "react";
import { Button, Dialog, Field, Input } from "@/components/ui";
import { setReviewer, useReviewer } from "@/lib/reviewer";

/** 머리줄 오른쪽: "검토자 이름 · 변경". 변경을 누르면 대화상자에서 고친다 (어느 화면에서나). */
export function ReviewerBadge() {
  const reviewer = useReviewer();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  const close = () => {
    setOpen(false);
    setError(null);
  };
  const save = () => {
    const name = draft.trim();
    if (!name) return setError("검토자 이름을 적어 주세요.");
    if (name.length > 40) return setError("검토자 이름은 40자 이하로 적어 주세요.");
    setReviewer(name);
    close();
  };

  return (
    <div className="flex items-center gap-2 text-mut">
      <span>검토자</span>
      <strong className="font-medium text-ink">{reviewer || "미지정"}</strong>
      {/* link 모양이 md 크기의 최소 높이를 물려받지 않도록 머리줄 높이에 맞춘다 */}
      <Button
        variant="link"
        className="min-h-0"
        onClick={() => {
          setDraft(reviewer);
          setOpen(true);
        }}
      >
        변경
      </Button>
      <Dialog
        open={open}
        onClose={close}
        title="검토자 이름"
        actions={
          <>
            <Button onClick={close}>취소</Button>
            <Button variant="primary" type="submit" form="reviewer-form">
              저장
            </Button>
          </>
        }
      >
        <form
          id="reviewer-form"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            save();
          }}
        >
          <Field id="reviewer-dialog" label="이름" hint="이 브라우저에만 저장됩니다." error={error ?? undefined}>
            <Input
              id="reviewer-dialog"
              autoComplete="name"
              value={draft}
              aria-invalid={!!error}
              aria-describedby={error ? "reviewer-dialog-error" : "reviewer-dialog-hint"}
              // 대화상자가 열리며 초점을 받을 때 지금 이름을 골라 두어, 바로 치면 바뀌게 한다
              onFocus={(e) => e.currentTarget.select()}
              onChange={(e) => {
                setDraft(e.target.value);
                setError(null);
              }}
            />
          </Field>
        </form>
      </Dialog>
    </div>
  );
}
