import type { ReactNode } from "react";
import { Card } from "@/components/ui";
import { cn } from "@/lib/cn";

/**
 * 뼈대 단계의 자리 표시. 데이터 설계가 정해지면 실제 내용으로 바꾼다.
 * 지어낸 값을 넣지 않고, 이 자리에 무엇이 오는지만 적는다.
 * 실제 카드와 구별되도록 Card 에 연한 바탕(tint)만 바꿔 쓴다.
 */
export function Slot({
  title,
  note,
  className,
  children,
}: {
  title: string;
  note?: string;
  className?: string;
  children?: ReactNode;
}) {
  return (
    <Card className={cn("flex flex-col gap-1 bg-tint text-mut", className)}>
      <span className="text-sm font-bold text-sub">{title}</span>
      {note && <span className="text-sm">{note}</span>}
      {children}
    </Card>
  );
}
