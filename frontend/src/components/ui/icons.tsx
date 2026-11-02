import type { ComponentProps } from "react";
import { cn } from "@/lib/cn";

/*
 * 선 아이콘 몇 개. 폐쇄망이라 아이콘 묶음을 받지 않고 여기 그린다.
 * 색은 글자색(currentColor)을 따르고, 뜻은 늘 옆 글자로 전한다 (aria-hidden).
 */
function Svg({ className, children, ...props }: ComponentProps<"svg">) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={cn("size-10 flex-none", className)}
      {...props}
    >
      {children}
    </svg>
  );
}

/** 올리기: 위로 향한 화살표와 받침 */
export function UploadIcon(props: ComponentProps<"svg">) {
  return (
    <Svg {...props}>
      <path d="M12 15V4" />
      <path d="m7 9 5-5 5 5" />
      <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
    </Svg>
  );
}

/** 문서 한 장 (확인하는 중) */
export function FileIcon(props: ComponentProps<"svg">) {
  return (
    <Svg {...props}>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
    </Svg>
  );
}

/** 문서와 체크 (올릴 수 있음) */
export function FileCheckIcon(props: ComponentProps<"svg">) {
  return (
    <Svg {...props}>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
      <path d="m9 14.5 2 2 4-4" />
    </Svg>
  );
}

/** 문서와 느낌표 (올릴 수 없음) */
export function FileAlertIcon(props: ComponentProps<"svg">) {
  return (
    <Svg {...props}>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
      <path d="M12 11.5v3" />
      <path d="M12 17.5h.01" />
    </Svg>
  );
}
