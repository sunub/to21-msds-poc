import type { ComponentProps } from "react";
import { cn } from "@/lib/cn";

export function Progress({ value, label }: { value: number; label: string }) {
  const pct = Math.min(100, Math.max(0, value));
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct}
      className="h-1 rounded-[2px] bg-[#e3ebf4]"
    >
      <div className="h-1 rounded-[2px] bg-blue" style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Spinner({ label = "불러오는 중" }: { label?: string }) {
  return (
    <span
      role="status"
      aria-label={label}
      className="inline-block size-7 animate-spin rounded-full border-[3px] border-line border-t-blue motion-reduce:animate-none"
    />
  );
}

export function Skeleton({ className, ...props }: ComponentProps<"span">) {
  return <span aria-hidden="true" className={cn("block h-3.5 rounded-sm bg-line2", className)} {...props} />;
}
