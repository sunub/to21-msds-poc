import { validationIdFor } from "@/lib/demo";

/**
 * 판정 요청에 쓰는 검증 번호를 얻는 한 곳. 모든 판정·성분 요청이 이 값을 쓴다.
 * 데모 문서는 데모 번호, 그 외에는 "latest" (서버 확정 후 교체: 문서 응답의 검증 번호).
 */
export function useValidationId(docId: string): string {
  return validationIdFor(docId);
}
