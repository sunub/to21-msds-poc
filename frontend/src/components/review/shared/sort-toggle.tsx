"use client";

import { cn } from "@/lib/cn";
import { SORTS, type SortKey } from "./sort";

/** "정렬 판정 순 / 심각도 순" 버튼 (2항·15항 표가 같이 쓴다) */
export function SortToggle({ sort, onSort }: { sort: SortKey; onSort: (key: SortKey) => void }) {
  return (
    <div role="group" aria-label="정렬 기준" className="flex flex-wrap items-center gap-1 text-sm text-mut">
      <span>정렬</span>
      {SORTS.map((s) => (
        <button
          key={s.id}
          type="button"
          aria-pressed={sort === s.id}
          onClick={() => onSort(s.id)}
          className={cn("rounded-sm px-2 py-0.5", sort === s.id ? "bg-blue-soft font-bold text-blue2" : "text-mut")}
        >
          {s.label}
        </button>
      ))}
    </div>
  );
}
