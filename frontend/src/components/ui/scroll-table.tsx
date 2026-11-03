"use client";

import { useLayoutEffect, useRef, type ComponentProps } from "react";
import { cn } from "@/lib/cn";
import { Table } from "./table";

/**
 * 높이를 정해 두고 안에서 스크롤하는 목록 표. 아래에 원문·상세 칸이 붙는 화면에서 쓴다.
 * 높이: 본문(PageMain) 높이의 40%, 최소 16rem(줄 5개쯤), 최대 28rem(줄 9개쯤).
 *   표를 고르고 아래 칸을 보는 일을 오가므로, 표가 화면을 다 덮어 아래 칸 머리가 밀려나지 않게 한다.
 * 머리줄은 <TableHead sticky> 로 고정한다.
 * follow: 고른 행의 키. 바뀌면 고른 행(aria-current)이 표 안에서 보이도록 표만 스크롤한다.
 *   "다음 판정"이나 주소로 바로 온 경우 고른 행이 보이는 범위 밖에 있을 수 있다.
 * 인쇄할 때는 높이 제한을 푼다.
 */
export function ScrollTable({ follow, className, ...props }: ComponentProps<"div"> & { follow?: string | null }) {
  const ref = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const box = ref.current;
    const row = box?.querySelector<HTMLElement>("[aria-current]");
    if (!box || !row) return;
    const head = box.querySelector<HTMLElement>("[data-sticky-head]")?.offsetHeight ?? 0;
    const boxRect = box.getBoundingClientRect();
    const rowRect = row.getBoundingClientRect();
    const above = rowRect.top - (boxRect.top + head);
    const below = rowRect.bottom - boxRect.bottom;
    if (above < 0) box.scrollTop += above;
    else if (below > 0) box.scrollTop += below;
  }, [follow]);

  return (
    <Table
      ref={ref}
      className={cn(
        "max-h-[clamp(16rem,40cqh,28rem)] overflow-y-auto print:max-h-none print:overflow-visible",
        className,
      )}
      {...props}
    />
  );
}

