import type { CSSProperties, ReactNode } from "react";
import { Card, Paper, Skeleton } from "@/components/ui";
import { cn } from "@/lib/cn";

/**
 * 머리줄 아래 남은 높이를 모두 차지하는 본문. 스크롤은 문서가 아니라 여기서 하므로 머리줄은 늘 보인다.
 * fill: 내용을 이 높이에 꼭 맞춘다 (Workspace 가 남은 높이를 채운다). 아니면 내용만큼 늘어나 스크롤한다.
 * 안쪽의 Workspace·SourceViewer 가 cqh 로 이 높이를 읽도록 크기 컨테이너로 둔다.
 * relative: 화면에서 숨긴 절대 위치 요소(sr-only)가 스크롤 영역을 벗어나 문서 전체를 늘리지 않게 한다.
 * scrollbar-gutter: 스크롤바가 생겨도 본문이 머리줄과 어긋나거나 화면을 옮길 때 좌우로 흔들리지 않게 한다.
 */
export function PageMain({
  width = "max-w-page",
  fill,
  className,
  children,
}: {
  width?: string;
  fill?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <main className="relative min-h-0 flex-1 overflow-y-auto [container-type:size] [scrollbar-gutter:stable_both-edges] print:overflow-visible print:[container-type:normal]">
      <div
        className={cn(
          "mx-auto flex flex-col gap-5 px-8 print:h-auto print:min-h-0",
          fill ? "h-full py-5" : "min-h-full pt-7 pb-14",
          width,
          className,
        )}
      >
        {children}
      </div>
    </main>
  );
}

/**
 * 원문과 작업 칸을 나란히 두는 영역. 칸은 이 높이를 채우고 안에서 스크롤한다. 좁은 화면에서는 위아래로 쌓는다.
 * 기본은 PageMain fill 의 남은 높이를 채운다.
 * viewport: 위아래로 표가 붙는 화면에서 본문 한 화면 높이를 쓴다.
 */
export function Workspace({ viewport, className, children }: { viewport?: boolean; className?: string; children: ReactNode }) {
  return (
    <div
      className={cn(
        "grid min-w-0 gap-5 lg:grid-cols-2 lg:grid-rows-[minmax(0,1fr)] print:block print:h-auto print:min-h-0",
        viewport ? "lg:h-[max(35rem,calc(100cqh-2.5rem))]" : "lg:min-h-104 lg:flex-1",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** 카드를 가로로 흘려 놓는 줄 (templates 의 .row). 자리가 모자라면 아래로 넘어간다. */
export function Row({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("flex flex-wrap items-start gap-5", className)}>{children}</div>;
}

/**
 * 제목이 붙은 카드 한 칸. 기본 폭은 basis 로 정한다
 * (원문 460px = basis-115, 작업 영역 420px = basis-105).
 * fill: Workspace 안에서 칸 높이를 채우고 제목 아래 내용만 스크롤한다.
 */
export function Pane({
  title,
  aside,
  fill,
  className,
  style,
  children,
}: {
  title: string;
  aside?: ReactNode;
  fill?: boolean;
  className?: string;
  style?: CSSProperties;
  children: ReactNode;
}) {
  return (
    <Card className={cn("flex min-w-0 grow flex-col gap-3.5", fill && "lg:h-full lg:min-h-0 print:h-auto", className)} style={style}>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-lg font-bold">{title}</h2>
        {aside}
      </div>
      {fill ? (
        <div className="flex flex-col gap-3.5 lg:min-h-0 lg:flex-1 lg:overflow-y-auto print:overflow-visible">{children}</div>
      ) : (
        children
      )}
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
export function Foot({ bordered = true, className, children }: { bordered?: boolean; className?: string; children: ReactNode }) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-4",
        bordered ? "border-t border-line pt-4" : "pt-1",
        className,
      )}
    >
      {children}
    </div>
  );
}
