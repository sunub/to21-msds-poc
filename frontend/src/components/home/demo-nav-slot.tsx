"use client";

import { useEffect, useState, type ComponentType } from "react";
import { loadDemo } from "@/lib/demo";

/** 데모 모드일 때만 DemoNav 를 불러와 그린다. 꺼진 빌드에서는 로더가 거절되어 아무것도 그리지 않고, demo-nav 도 번들에 없다 */
export function DemoNavSlot() {
  const [Nav, setNav] = useState<ComponentType | null>(null);
  useEffect(() => {
    let alive = true;
    loadDemo
      .homeNav()
      .then((m) => alive && setNav(() => m.DemoNav))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);
  return Nav ? <Nav /> : null;
}
