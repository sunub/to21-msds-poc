/**
 * 판정 요청에 쓰는 판정 버전. 한 곳에서만 정한다. 계약에는 별도 검증 번호가 없고 판정 버전(version)만 있다:
 * 화면은 늘 최신("latest")을 읽고, 검토·저장 요청에는 읽은 버전 번호(seen_version)를 실어 보낸다.
 */
export function useValidationId(_docId: string): string {
  return "latest";
}
