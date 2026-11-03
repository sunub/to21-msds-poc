import type { ComponentProps } from "react";
import { cn } from "@/lib/cn";

/** 목록 표: 머리줄은 연한 바탕, 행은 얇은 선으로 나눈다. 행은 누를 수 있는 버튼이고 선택된 행은 --sel 바탕. */
export function Table({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("overflow-x-auto rounded-md border border-line bg-white", className)} {...props} />;
}

/** sticky: 스크롤하는 표(ScrollTable) 안에서 머리줄을 위에 붙여 둔다 */
export function TableHead({ sticky, className, ...props }: ComponentProps<"div"> & { sticky?: boolean }) {
  return (
    <div
      data-sticky-head={sticky || undefined}
      className={cn(
        "flex items-center gap-3 border-b border-line bg-tint px-4 py-[9px] text-sm font-medium text-mut",
        sticky && "sticky top-0 z-10",
        className,
      )}
      {...props}
    />
  );
}

export function TableRow({
  selected,
  className,
  ...props
}: ComponentProps<"button"> & { selected?: boolean }) {
  return (
    <button
      type="button"
      aria-current={selected || undefined}
      className={cn(
        "flex w-full items-center gap-3 border-b border-line2 px-4 py-2.5 text-left last:border-b-0",
        selected ? "bg-sel" : "bg-white",
        className,
      )}
      {...props}
    />
  );
}
