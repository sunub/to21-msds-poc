import type { ComponentProps } from "react";
import { cn } from "@/lib/cn";

/** 원문 쪽 보기: 연한 둘레 위에 흰 종이 한 장. 원문 글자는 12px, 줄 간격 1.6. */
export function Paper({ className, ...props }: ComponentProps<"div">) {
  return (
    <div className="rounded-sm bg-paper p-3">
      <div
        className={cn(
          "flex min-h-120 flex-col gap-1.75 border border-line bg-white px-5 py-4.5 text-xs",
          className,
        )}
        {...props}
      />
    </div>
  );
}
