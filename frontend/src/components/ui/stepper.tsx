import { cn } from "@/lib/cn";

type Step = { id: string; label: string; note?: string };

/** 상단 단계 표시: 추출 → 검수 → 저장. 순서가 있는 내용이라 번호를 붙인다. */
export function Stepper({ steps, current }: { steps: Step[]; current: string }) {
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
