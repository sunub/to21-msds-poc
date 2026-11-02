"use client";

import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/cn";

/*
 * 판정 표 (2항·15항). div 로 그리되 표 역할(role)을 붙여 보조기기가 표로 읽게 한다.
 * 열 너비는 행마다 같은 grid-template-columns 를 써서 맞춘다. 표 칸 너비(container)에 따라
 * 보조 열을 숨기므로 화면 폭이 좁아도 가로 스크롤 없이 "판정" 열이 보인다.
 * 행을 고르는 단추는 첫 칸 안의 button 이고, 행 어디를 눌러도 같은 동작이다 (행 onClick).
 */

export function GridTable({ label, className, ...props }: ComponentProps<"div"> & { label: string }) {
  return (
    <div
      role="table"
      aria-label={label}
      className={cn("@container overflow-hidden rounded-md border border-line bg-white", className)}
      {...props}
    />
  );
}

export function GridHead({ cols, children }: { cols: string; children: ReactNode }) {
  return (
    <div role="rowgroup">
      <div role="row" className={cn("grid items-center gap-x-3 border-b border-line bg-tint px-3 py-2 text-sm font-medium text-mut", cols)}>
        {children}
      </div>
    </div>
  );
}

/** 머리 칸. 줄 때문에 낱말이 쪼개지지 않게 break-keep 이다 */
export function HeadCell({ className, ...props }: ComponentProps<"div">) {
  return <div role="columnheader" className={cn("min-w-0 [word-break:keep-all]", className)} {...props} />;
}

export function GridBody({ ...props }: ComponentProps<"div">) {
  return <div role="rowgroup" {...props} />;
}

/** 판정 한 줄. 선택된 줄은 aria-current 와 왼쪽 선으로 표시한다 */
export function GridRow({
  cols,
  selected,
  onSelect,
  className,
  children,
}: {
  cols: string;
  selected: boolean;
  onSelect: () => void;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      role="row"
      aria-current={selected || undefined}
      onClick={onSelect}
      className={cn(
        "grid cursor-pointer items-center gap-x-3 border-b border-l-4 border-b-line2 px-3 py-2.5 text-sm",
        selected ? "border-l-blue bg-sel" : "border-l-transparent bg-white",
        cols,
        className,
      )}
    >
      {children}
    </div>
  );
}

/** 칸. 낱말 중간에서 줄이 바뀌지 않게 break-keep, 아주 긴 낱말만 넘치지 않게 break-words */
export function Cell({ className, ...props }: ComponentProps<"div">) {
  return <div role="cell" className={cn("min-w-0 [word-break:keep-all] break-words", className)} {...props} />;
}

/** 줄 전체를 한 칸으로 쓰는 줄 (접기 단추, 안내 문구) */
export function SpanRow({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div role="row" className={className}>
      <div role="cell">{children}</div>
    </div>
  );
}
