"use client";

import { useRef, useState, type DragEvent, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Button } from "./button";

/**
 * 고른 파일의 상태. 상자 전체의 테두리·바탕이 바뀌어 한눈에 알 수 있게 한다.
 * - idle: 아직 없음 (점선)
 * - checking: 고른 파일을 확인하는 중
 * - ready: 확인을 통과함 (초록 실선·연초록 바탕)
 * - invalid: 올릴 수 없음 (빨강 실선·연빨강 바탕)
 * 끌고 들어오는 동안은 상태와 상관없이 파란 바탕이다.
 */
export type DropzoneStatus = "idle" | "checking" | "ready" | "invalid";

const STATUS_STYLE: Record<DropzoneStatus, string> = {
  idle: "border-dashed border-outline bg-white",
  checking: "border-dashed border-blue-line bg-white",
  ready: "border-solid border-grn bg-grn-soft",
  invalid: "border-solid border-red bg-red-soft",
};

/**
 * 파일 끌어 놓기 영역: 상자에 놓거나 "파일 선택" 버튼으로 고른다. 두 길 모두 onFiles 하나로 모인다.
 * 키보드로는 버튼만 쓴다 (상자는 초점을 받지 않는다). 파일 개수·형식 검사는 쓰는 쪽이 하고 status 로 알려 준다.
 * children 에 함수를 주면 끌고 들어오는 중인지(over)를 받아 안내 문구를 바꿀 수 있다.
 */
export function Dropzone({
  onFiles,
  accept,
  disabled,
  status = "idle",
  buttonLabel = "파일 선택",
  inputId,
  describedBy,
  className,
  children,
}: {
  onFiles: (files: File[]) => void;
  accept?: string;
  disabled?: boolean;
  status?: DropzoneStatus;
  buttonLabel?: string;
  inputId?: string;
  describedBy?: string;
  className?: string;
  children?: ReactNode | ((over: boolean) => ReactNode);
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  // dragenter·dragleave 는 안쪽 요소를 지날 때도 나므로 깊이로 센다
  const [depth, setDepth] = useState(0);
  const over = depth > 0 && !disabled;

  const stop = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  return (
    <div
      onDragEnter={(e) => {
        stop(e);
        setDepth((d) => d + 1);
      }}
      onDragOver={(e) => {
        stop(e);
        e.dataTransfer.dropEffect = disabled ? "none" : "copy";
      }}
      onDragLeave={(e) => {
        stop(e);
        setDepth((d) => Math.max(0, d - 1));
      }}
      onDrop={(e) => {
        stop(e);
        setDepth(0);
        if (!disabled && e.dataTransfer.files.length) onFiles([...e.dataTransfer.files]);
      }}
      data-status={over ? "over" : status}
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-md border p-8 text-center transition-colors",
        over ? "border-dashed border-blue bg-sel" : STATUS_STYLE[status],
        disabled && "opacity-60",
        className,
      )}
    >
      {/* 상태가 바뀌면 화면 읽기 프로그램에도 알린다 */}
      <div aria-live="polite" className="flex flex-col items-center gap-2">
        {typeof children === "function" ? children(over) : children}
      </div>
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept={accept}
        disabled={disabled}
        aria-describedby={describedBy}
        tabIndex={-1}
        className="sr-only"
        onChange={(e) => {
          const files = e.target.files;
          if (files?.length) onFiles([...files]);
          // 같은 파일을 다시 골라도 onChange 가 나도록 비운다
          e.target.value = "";
        }}
      />
      <Button
        // 파일이 준비되면 다음 행동(추출 시작)이 주인공이므로 이 버튼은 한 단계 낮춘다
        variant={status === "ready" ? "default" : "primary"}
        size="lg"
        className="mt-1"
        disabled={disabled}
        aria-describedby={describedBy}
        onClick={() => inputRef.current?.click()}
      >
        {buttonLabel}
      </Button>
    </div>
  );
}
