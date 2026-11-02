import type { ComponentProps } from "react";
import { cn } from "@/lib/cn";

/** 체크박스와 글자를 한 줄에 묶는다. 글자를 눌러도 켜지고 꺼진다. */
export function Checkbox({
  label,
  className,
  ...props
}: Omit<ComponentProps<"input">, "type"> & { label: string }) {
  return (
    <label className={cn("inline-flex cursor-pointer items-center gap-2", className)}>
      <input type="checkbox" className="size-4 accent-blue" {...props} />
      {label}
    </label>
  );
}
