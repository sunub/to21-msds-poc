import Link from "next/link";
import { routes } from "@/lib/routes";

/** 데모 모드에서만 홈에 보이는 링크 줄 (lib/demo.ts 의 loadDemo 를 거쳐서만 불러온다) */
export function DemoNav() {
  return (
    <nav aria-label="데모 링크" className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
      <Link href={routes.review("demo", "hazard")}>데모 문서 열기</Link>
      <Link href="/design-system/">디자인 시스템</Link>
    </nav>
  );
}
