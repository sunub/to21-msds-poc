import type { ReactNode } from "react";
import { Slot } from "./slot";

/** 원문을 왼쪽(12칸 중 5칸)에, 작업 영역을 오른쪽(7칸)에 나란히 둔다. 좁은 화면에서는 위아래로 쌓는다. */
export function Split({ source, children }: { source: ReactNode; children: ReactNode }) {
  return (
    <div className="grid gap-4 lg:grid-cols-12">
      <div className="min-w-0 lg:col-span-5">{source}</div>
      <div className="flex min-w-0 flex-col gap-4 lg:col-span-7">{children}</div>
    </div>
  );
}

/** 원문 쪽 보기 자리: 쪽 이미지·글자, 이전/다음 쪽, 항 바로가기가 들어온다. */
export function SourcePane({ note }: { note?: string }) {
  return <Slot title="원문" note={note ?? "쪽 이미지와 쪽 이동이 들어올 자리"} className="min-h-120" />;
}
