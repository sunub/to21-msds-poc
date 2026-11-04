import { cn } from "@/lib/cn";

type Step = { id: string; label: string; note?: string };

/** 상단 단계 표시: 추출 → 검수 → 저장. 순서가 있는 내용이라 번호를 붙인다. */
export function Stepper({
  steps,
  current,
  variant = "tabs",
}: {
  steps: Step[];
  current: string;
  /** tabs: 밑줄 탭(기본), pill: 머리줄용 둥근 알약 묶음 */
  variant?: "tabs" | "pill";
}) {
  if (variant === "pill") {
    const currentIndex = steps.findIndex((s) => s.id === current);
    return (
      <ol className="m-0 flex list-none gap-1 rounded-full bg-tint p-1 text-sm">
        {steps.map((s, i) => {
          const on = i === currentIndex;
          const done = currentIndex >= 0 && i < currentIndex;
          return (
            <li
              key={s.id}
              aria-current={on ? "step" : undefined}
              title={s.note}
              className={cn(
                "flex items-center gap-1.5 rounded-full px-3 py-1",
                on ? "bg-blue font-bold text-white" : done ? "text-ink" : "text-mut",
              )}
            >
              <span
                aria-hidden="true"
                className={cn(
                  "inline-flex size-5 shrink-0 items-center justify-center rounded-full text-xs",
                  on ? "bg-white/25" : done ? "text-grn" : "bg-line",
                )}
              >
                {done ? "✓" : i + 1}
              </span>
              {s.label}
              {s.note && <span className="sr-only">{s.note}</span>}
            </li>
          );
        })}
      </ol>
    );
  }
  return (
    <ol className="m-0 flex list-none flex-wrap gap-8 p-0">
      {steps.map((s, i) => {
        const on = s.id === current;
        return (
          <li
            key={s.id}
            aria-current={on ? "step" : undefined}
            className={cn(
              "border-b-2 pt-3.5 pb-3",
              on ? "border-blue font-bold text-blue2" : "border-transparent text-mut",
            )}
          >
            {i + 1} {s.label}
            {s.note && <span className="ml-1.5 font-normal text-mut">{s.note}</span>}
          </li>
        );
      })}
    </ol>
  );
}
