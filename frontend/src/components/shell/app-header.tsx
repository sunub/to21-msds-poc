import Link from "next/link";
import { routes } from "@/lib/routes";

/** 모든 화면 맨 위 줄: 제품 이름, (문서 화면이면) 문서 이름, 검토자. 모양은 /design-system 머리줄과 같다. */
export function AppHeader({ doc }: { doc?: string }) {
  return (
    <header className="border-b border-line bg-white">
      <div className="mx-auto flex min-h-14 max-w-page items-center gap-2.5 px-8">
        <Link href={routes.home()} className="text-lg font-bold text-ink">
          MSDS 검수
        </Link>
        {doc && (
          <>
            <span className="text-outline" aria-hidden="true">
              /
            </span>
            {/* 제품명·파일 이름·쪽 수·데이터 등급은 데이터 설계 뒤에 채운다 */}
            <strong className="text-lg">{doc}</strong>
          </>
        )}
        <span className="ml-auto text-sm text-mut">검토자 자리</span>
      </div>
    </header>
  );
}
