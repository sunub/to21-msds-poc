"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { cn } from "@/lib/cn";
import { routes } from "@/lib/routes";

const SCENARIOS = [
  { id: "ready", label: "기본 혼합물" },
  { id: "conflict", label: "409 충돌" },
  { id: "stale", label: "재판정 Stale" },
  { id: "single", label: "단일물질" },
] as const;

/**
 * 공개 정적 데모(NEXT_PUBLIC_DEMO_MODE=1) 전용 상단 배너.
 * 기본 폐쇄망 빌드에서는 조건이 거짓으로 접혀 내부 구현과 문구가 번들에서 완전히 제거된다.
 */
export function DemoBanner() {
  if (process.env.NEXT_PUBLIC_DEMO_MODE !== "1") return null;
  return <DemoBannerInner />;
}

function DemoBannerInner() {
  const [scenario, setScenario] = useState("ready");

  useEffect(() => {
    const param = new URLSearchParams(window.location.search).get("judgmentMock");
    const saved = (() => {
      try {
        return window.sessionStorage.getItem("msds.judgmentMock");
      } catch {
        return null;
      }
    })();
    setScenario(param || saved || "ready");
  }, []);

  return (
    <aside
      aria-label="공개 데모 안내"
      className="shrink-0 border-b border-blue-line bg-blue-soft text-sm text-blue2 print:hidden"
    >
      <div className="mx-auto flex min-h-9 max-w-page flex-wrap items-center justify-between gap-x-4 gap-y-1 px-8 py-1.5">
        <p className="font-medium">합성 샘플 데이터 기반 공개 데모 (원본 기업 PoC 데이터 미포함)</p>
        <nav aria-label="데모 시나리오 전환" className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-sub">시나리오:</span>
          {SCENARIOS.map((s) => {
            const active = scenario === s.id;
            return (
              <Link
                key={s.id}
                href={`${routes.review("DEMO-CHEM-001", "hazard")}&judgmentMock=${s.id}`}
                onClick={() => setScenario(s.id)}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "inline-flex min-h-7 items-center rounded-xs px-2.5 py-0.5 text-xs font-medium no-underline",
                  active ? "bg-blue text-white" : "bg-white text-blue2 border border-blue-line",
                )}
              >
                {s.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </aside>
  );
}
