import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "@/lib/cn";

/** 상태 점. 색만으로 뜻을 전하지 않도록 항상 글자와 함께 쓴다. */
export const dotStyles = cva("inline-block size-2 flex-none rounded-full", {
  variants: {
    tone: {
      info: "bg-blue",
      danger: "bg-red",
      warning: "bg-amb",
      success: "bg-grn",
      neutral: "bg-gry",
      stale: "bg-stale",
    },
  },
  defaultVariants: { tone: "neutral" },
});

export type Tone = NonNullable<VariantProps<typeof dotStyles>["tone"]>;

const TEXT: Record<Tone, string> = {
  info: "text-blue2",
  danger: "text-red",
  warning: "text-amb-text",
  success: "text-grn",
  neutral: "text-mut",
  stale: "text-stale",
};

export function StatusLabel({
  tone = "neutral",
  className,
  children,
  ...props
}: ComponentProps<"span"> & { tone?: Tone }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-sm", TEXT[tone], className)} {...props}>
      <span className={dotStyles({ tone })} aria-hidden="true" />
      {children}
    </span>
  );
}

/** 모델이 채운 값임을 알리는 작은 표지 */
export function AiChip({ className, children = "AI", ...props }: ComponentProps<"span">) {
  return (
    <span
      className={cn("rounded-xs bg-blue-soft px-1.5 py-px text-xs font-medium text-blue2", className)}
      {...props}
    >
      {children}
    </span>
  );
}
