/*
 * 판정을 읽는 탭(2항, 15항, 성분별 요약)이 함께 쓰는 입구.
 *
 * gate.tsx           입구. 문서·판정 상태를 받아 lib/judgment-gate 의 gateView 로 보일 것을 고른다
 * notice.tsx         안내 카드 틀 (모든 안내가 같은 모양을 쓴다)
 * not-extracted.tsx  추출이 끝나지 않음
 * not-connected.tsx  판정 API가 아직 없음
 * start-judgment.tsx 판정으로 넘긴 적이 없음 → 넘기기
 * failed.tsx         판정 실패
 * error.tsx          판정 상태·결과를 불러오지 못함 (탭이 판정 결과를 받다 실패할 때도 쓴다)
 */
export { JudgmentError } from "./error";
export { JudgmentGate, type JudgmentReady } from "./gate";
export { JudgmentNotice } from "./notice";
