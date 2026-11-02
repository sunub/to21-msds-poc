import { Fragment } from "react";

/** 글 속의 날짜(2025-01-01)는 줄이 바뀌어도 쪼개지지 않게 묶는다 */
export function NoBreakDates({ text }: { text: string }) {
  return (
    <>
      {text.split(/(\d{4}-\d{2}-\d{2})/).map((part, i) =>
        i % 2 === 1 ? (
          <span key={i} className="whitespace-nowrap">
            {part}
          </span>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        ),
      )}
    </>
  );
}
