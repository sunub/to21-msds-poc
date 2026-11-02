import type { ReactNode } from "react";
import { Card, Paper, Skeleton } from "@/components/ui";
import { cn } from "@/lib/cn";

/** 카드를 가로로 흘려 놓는 줄 (templates 의 .row). 자리가 모자라면 아래로 넘어간다. */
export function Row({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("flex flex-wrap items-start gap-5", className)}>{children}</div>;
}

/**
 * 제목이 붙은 카드 한 칸. 기본 폭은 basis 로 정한다
 * (원문 460px = basis-115, 작업 영역 420px = basis-105).
 */
export function Pane({
  title,
  aside,
  className,
  children,
}: {
  title: string;
  aside?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Card className={cn("flex min-w-0 grow flex-col gap-3.5", className)}>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-lg font-bold">{title}</h2>
        {aside}
      </div>
      {children}
    </Card>
  );
}

/** 원문 카드. 내용이 없으면 종이에 빈 줄만 그린다. paperClassName 은 종이 한 장의 모양을 바꾼다. */
export function SourcePane({
  aside,
  paperClassName,
  children,
}: {
  aside?: ReactNode;
  paperClassName?: string;
  children?: ReactNode;
}) {
  return (
    <Pane title="원문" aside={aside} className="basis-115">
      <Paper className={paperClassName}>
        {children ?? (
          <div aria-hidden="true" className="grid gap-2.5">
            <Skeleton className="w-full" />
            <Skeleton className="w-4/5" />
            <Skeleton className="w-full" />
            <Skeleton className="w-2/3" />
          </div>
        )}
      </Paper>
    </Pane>
  );
}

/** 화면 맨 아래 줄 (templates 의 .foot): 왼쪽 안내, 오른쪽 버튼. */
export function Foot({ bordered = true, children }: { bordered?: boolean; children: ReactNode }) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-4",
        bordered ? "border-t border-line pt-4" : "pt-1",
      )}
    >
      {children}
    </div>
  );
}
