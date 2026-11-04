import Link from "next/link";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";
import { ReviewerBadge } from "./reviewer-badge";

/**
 * 모든 화면 맨 위 줄 (templates 의 .hd): 왼쪽에 제품 이름과 (문서 화면이면) 문서 이름,
 * 오른쪽에 검토자. width 는 아래 본문과 같은 최대 너비를 받는다.
 */
export function AppHeader({
  doc,
  note,
  center,
  width = "max-w-page",
}: {
  doc?: string;
  /** 문서 이름 옆 설명. 없으면 아무것도 그리지 않는다 */
  note?: string;
  /** 제목과 검토자 사이(가운데)에 그릴 내용. 문서 화면의 단계 알약 */
  center?: ReactNode;
  width?: string;
}) {
  return (
    <header className="border-b border-line bg-white print:hidden">
      <div
        className={cn(
          "mx-auto flex min-h-14 flex-wrap items-center justify-between gap-4 px-8",
          center && "lg:grid lg:grid-cols-[1fr_auto_1fr]",
          width,
        )}
      >
        <div className={cn("flex items-center gap-2.5", center ? "min-w-0 flex-1" : "flex-wrap")}>
          <Link href={routes.home()} className="text-lg font-bold text-ink no-underline">
            MSDS 검수
          </Link>
          {doc && (
            <>
              <span className="shrink-0 text-outline" aria-hidden="true">
                /
              </span>
              <strong className="min-w-0 truncate text-lg" title={doc}>
                {doc}
              </strong>
              {note && <span className="text-sm text-mut">{note}</span>}
            </>
          )}
        </div>
        {center && <div className="shrink-0">{center}</div>}
        {center ? (
          <div className="lg:justify-self-end">
            <ReviewerBadge />
          </div>
        ) : (
          <ReviewerBadge />
        )}
      </div>
    </header>
  );
}
