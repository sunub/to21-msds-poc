"use client";

import { useEffect, useRef, useState } from "react";

export function useObservedHeight<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [height, setHeight] = useState<number>();

  useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === "undefined") return;

    const observer = new ResizeObserver(() => {
      const nextHeight = Math.ceil(element.getBoundingClientRect().height);
      setHeight((current) => current === nextHeight ? current : nextHeight);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return { ref, height };
}
