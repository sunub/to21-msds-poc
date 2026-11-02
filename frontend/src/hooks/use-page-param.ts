"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

/** ?page= 는 원문 칸의 쪽. 다른 주소 값(doc, tab)은 그대로 두고, 새로 고쳐도 유지하며 뒤로 가기 기록은 늘리지 않는다 */
export function usePageParam() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const page = Math.max(1, Number(params.get("page")) || 1);
  const query = params.toString();
  const setPage = useCallback(
    (next: number) => {
      const q = new URLSearchParams(query);
      q.set("page", String(next));
      router.replace(`${pathname}?${q.toString()}`, { scroll: false });
    },
    [router, pathname, query],
  );
  return [page, setPage] as const;
}
