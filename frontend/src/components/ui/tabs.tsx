"use client";

import { useRef, type KeyboardEvent, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { activeTabIndex, resolveTabKey, tabIndexFor } from "@/lib/tabs";

type Item = { id: string; label: ReactNode };

/**
 * 밑줄 탭: 같은 화면 안에서 구역을 오간다 (2항, 15항, 성분별 요약 …).
 * WAI-ARIA Tabs 패턴: roving tabIndex 와 ArrowLeft/ArrowRight/Home/End 키보드 탐색을 지원한다.
 */
export function UnderlineTabs({
  items,
  value,
  onChange,
  label,
  idPrefix,
}: {
  items: Item[];
  value: string;
  onChange: (id: string) => void;
  label: string;
  /** 지정하면 각 탭에 id 와 aria-controls 를 붙여 tabpanel 과 연결한다 */
  idPrefix?: string;
}) {
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const activeIdx = activeTabIndex(
    items.map((it) => it.id),
    value,
  );

  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    const nextIdx = resolveTabKey(e.key, index, items.length);
    if (nextIdx === null) return;
    e.preventDefault();
    tabRefs.current[nextIdx]?.focus();
    const next = items[nextIdx];
    if (next && next.id !== value) onChange(next.id);
  };

  return (
    <div role="tablist" aria-label={label} className="flex flex-wrap gap-6">
      {items.map((it, idx) => {
        const on = it.id === value;
        return (
          <button
            key={it.id}
            ref={(el) => {
              tabRefs.current[idx] = el;
            }}
            id={idPrefix ? `${idPrefix}-${it.id}` : undefined}
            role="tab"
            type="button"
            aria-selected={on}
            aria-controls={idPrefix ? `${idPrefix}-panel-${it.id}` : undefined}
            tabIndex={tabIndexFor(idx, activeIdx)}
            onClick={() => onChange(it.id)}
            onKeyDown={(e) => onKeyDown(e, idx)}
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
