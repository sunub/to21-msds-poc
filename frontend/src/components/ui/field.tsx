import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/cn";

const control =
  "w-full rounded-md border border-field-line bg-white text-ink placeholder:text-outline aria-invalid:border-red disabled:bg-tint disabled:text-mut";

/** react-hook-form 의 register() 결과를 그대로 펼쳐 쓸 수 있다 (React 19 는 ref 가 일반 prop). */
export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(control, "min-h-10 px-3", className)} {...props} />;
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cn(control, "resize-y px-2.5 py-2", className)} {...props} />;
}

export function Label({ className, ...props }: ComponentProps<"label">) {
  return <label className={cn("mb-1 block text-sm font-bold text-mut", className)} {...props} />;
}

/** 라벨, 입력, 도움말·오류를 한 묶음으로 둔다. 오류는 무엇이 잘못됐고 어떻게 고치는지 쓴다. */
export function Field({
  id,
  label,
  hint,
  error,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div>
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error ? (
        <p id={`${id}-error`} role="alert" className="mt-1 text-sm text-red">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="mt-1 text-sm text-mut">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
