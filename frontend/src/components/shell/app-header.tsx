import Link from "next/link";
import { Skeleton } from "@/components/ui";
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
  width = "max-w-page",
}: {
  doc?: string;
  /** 문서 이름 옆 설명. 받기 전에는 자리 표시를 그린다 */
  note?: string;
  width?: string;
}) {
  return (
    <header className="border-b border-line bg-white print:hidden">
      <div className={cn("mx-auto flex min-h-14 flex-wrap items-center justify-between gap-4 px-8", width)}>
        <div className="flex flex-wrap items-center gap-2.5">
          <Link href={routes.home()} className="text-lg font-bold text-ink no-underline">
            MSDS 검수
          </Link>
          {doc && (
            <>
              <span className="text-outline" aria-hidden="true">
                /
              </span>
              <strong className="text-lg">{doc}</strong>
              {note ? <span className="text-sm text-mut">{note}</span> : <Skeleton className="w-40" />}
            </>
          )}
        </div>
        <ReviewerBadge />
      </div>
    </header>
  );
}
