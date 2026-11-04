import type { ReactNode } from "react";
import { Pane } from "@/components/shell/layout";

/** 판정 입구의 안내 카드 틀. alert 이면 화면 읽기 도구가 바로 읽는다 */
export function JudgmentNotice({
  paneTitle,
  title,
  alert,
  children,
}: {
  paneTitle: string;
  title: string;
  alert?: boolean;
  children: ReactNode;
}) {
  return (
    <Pane title={paneTitle}>
      <div role={alert ? "alert" : "status"} className="flex flex-col items-center gap-3 py-10 text-center">
        <h3 className="text-lg font-bold">{title}</h3>
        {children}
      </div>
    </Pane>
  );
}
