import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

type Item = { id: string; label: ReactNode };

/** 밑줄 탭: 같은 화면 안에서 구역을 오간다 (2항, 15항, 성분별 요약 …). */
export function UnderlineTabs({
  items,
  value,
  onChange,
  label,
}: {
  items: Item[];
  value: string;
  onChange: (id: string) => void;
  label: string;
}) {
  return (
    <div role="tablist" aria-label={label} className="flex flex-wrap gap-6">
      {items.map((it) => {
        const on = it.id === value;
        return (
          <button
            key={it.id}
            role="tab"
            type="button"
            aria-selected={on}
            onClick={() => onChange(it.id)}
            className={cn(
              "border-b-2 pt-2 pb-2.5",
              on ? "border-blue font-bold text-blue2" : "border-transparent text-mut",
            )}
          >
            {it.label}
          </button>
        );
      })}
    </div>
  );
}

/** 알약 탭: 목록을 거르는 보기 전환 */
export function PillTabs({
  items,
  value,
  onChange,
  label,
}: {
  items: Item[];
  value: string;
  onChange: (id: string) => void;
  label: string;
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-1">
      {items.map((it) => {
        const on = it.id === value;
        return (
          <button
            key={it.id}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(it.id)}
            className={cn(
              "min-h-[34px] rounded-sm px-3 font-medium",
              on ? "bg-blue-soft font-bold text-blue2" : "text-mut",
            )}
          >
            {it.label}
          </button>
        );
      })}
    </div>
  );
}
