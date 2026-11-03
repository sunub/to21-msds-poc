/*
 * 서버가 준 파일(Blob)을 내려받게 하거나 새 탭에서 연다 (리포트: html·xlsx·pdf·json).
 * 브라우저에서만 부른다.
 */
export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.append(a);
  a.click();
  a.remove();
  // 내려받기가 시작된 뒤에 주소를 거둔다
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** 새 탭에서 연다 (HTML 미리 보기). 팝업이 막히면 false */
export function openBlob(blob: Blob): boolean {
  const url = URL.createObjectURL(blob);
  const tab = window.open(url, "_blank");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
  return tab !== null;
}
