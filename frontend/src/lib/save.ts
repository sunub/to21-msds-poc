/*
 * 저장 화면·저장 전 경고의 표시 규칙. 화면과 분리한 순수 함수라 서버 없이 시험한다 (save.test.ts).
 * 무엇이 처리할 판정인지는 새로 정하지 않고 15항·2항 탭과 같은 규칙(regulation.ts 의 isUnreviewed·byPriority)을 쓴다.
 */
import type { Finding, JudgmentView } from "@/api/judgment";
import { byPriority, isUnreviewed } from "./regulation.ts";

/** 처리하지 않은 판정 (모든 MSDS, 2항·15항). 급한 순서로 정렬한다 */
export function unreviewedFindings(view: JudgmentView): Finding[] {
  return view.consistency.results
    .flatMap((r) => r.findings)
    .filter((f) => isUnreviewed(f, view.reviews))
    .sort(byPriority);
}

/** 처리한 건수 (서버가 센 값): 확정 = 불일치 확정 + 확인, 예외 승인 */
export function processedCounts(reviews: { "불일치 확정": number; "예외 승인": number; 확인: number }) {
  const confirmed = reviews["불일치 확정"] + reviews.확인;
  const exception = reviews["예외 승인"];
  return { confirmed, exception, total: confirmed + exception };
}

/** 추출값 검수 상태 문구 (저장 개요 values.state) */
export const valuesLabel = (state: "미검수" | "일부" | "완료") =>
  state === "완료" ? "추출값 확인함" : state === "일부" ? "추출값 일부 확인" : "추출값 미검수";
