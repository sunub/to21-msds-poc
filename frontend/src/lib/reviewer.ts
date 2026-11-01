"use client";

/*
 * 검토자 이름. 서버로 보내지 않고 이 브라우저(localStorage)에만 둔다 (명세 8. 인증·사용자 없음).
 * 목록의 검증 조건과 머리줄이 같은 값을 보도록 한 곳에서 읽고 쓴다.
 * 저장소를 쓸 수 없는 환경(사생활 보호 창 등)에서는 이 탭 안에서만 기억한다.
 */
import { useSyncExternalStore } from "react";

const KEY = "msds.reviewer";
const EVENT = "msds:reviewer";

let memory = "";

function read(): string {
  try {
    return window.localStorage.getItem(KEY) ?? memory;
  } catch {
    return memory;
  }
}

export function setReviewer(name: string) {
  memory = name;
  try {
    window.localStorage.setItem(KEY, name);
  } catch {
    // 저장소를 못 쓰면 memory 에만 남긴다
  }
  window.dispatchEvent(new Event(EVENT));
}

function subscribe(onChange: () => void) {
  // 같은 탭은 EVENT, 다른 탭은 storage 로 알린다
  window.addEventListener(EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

/** 지금 검토자 이름. 정적 빌드·첫 그림에서는 빈 값이고, 브라우저에서 저장된 값으로 바뀐다. */
export function useReviewer() {
  return useSyncExternalStore(subscribe, read, () => "");
}
