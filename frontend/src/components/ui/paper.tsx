import type { ComponentProps } from "react";
import { cn } from "@/lib/cn";

/** 원문 쪽 보기: 연한 둘레 위에 흰 종이 한 장. 원문 글자는 12px, 줄 간격 1.6. */
/** fill: 높이가 정해진 칸(flex 세로)에 맞춘다. 최소 높이를 두지 않아 칸보다 짧은 내용이 잘리지 않고, 긴 내용은 칸이 스크롤한다. */
export function Paper({ className, fill, ...props }: ComponentProps<"div"> & { fill?: boolean }) {
  return (
    <div className={cn("rounded-sm bg-paper p-3", fill && "flex flex-1 flex-col")}>
      <div
        className={cn(
          "flex min-h-120 flex-col gap-1.75 border border-line bg-white px-5 py-4.5 text-xs",
          fill && "min-h-0 flex-1",
          className,
        )}
        {...props}
      />
    </div>
  );
}
