import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "@/lib/cn";

/** 경고 상자: 본문 옆에서 주의·오류를 알린다. 색만으로 뜻을 전하지 않도록 글자와 함께 쓴다. */
const calloutStyles = cva("rounded-sm border px-3 py-2 text-sm", {
  variants: {
    tone: {
      warning: "border-amb bg-tint text-amb-text",
      danger: "border-red bg-red-soft text-red",
      info: "border-blue-line bg-blue-soft text-blue2",
    },
  },
  defaultVariants: { tone: "warning" },
});

export function Callout({
  tone,
  className,
  ...props
}: ComponentProps<"div"> & VariantProps<typeof calloutStyles>) {
  return <div className={cn(calloutStyles({ tone }), className)} {...props} />;
}
