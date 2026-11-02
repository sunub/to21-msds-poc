/*
 * 검토 이력 목록. 계약에는 이력 목록 API 가 없다(검토 상태의 history_count 만 있다).
 * 그래서 이력 목록은 이 브라우저 탭의 sessionStorage 에 문서별로 쌓는다. 서버 이력 API 가 생기면 이 파일의 두 함수만 바꾼다:
 *   loadHistory(docId)            이력을 읽는다
 *   appendHistory(docId, entry)   이력 한 줄을 더한다
 * 저장소를 못 쓰거나 값이 깨져 있어도 화면은 정상 동작한다 (이 호출 안에서만 처리).
 */
export type HistoryKind = "confirm" | "exception" | "undo";

export type HistoryEntry = {
  id: string;
  /** ISO-8601, 시간대 +09:00 */
  at: string;
  reviewer: string;
  kind: HistoryKind;
  findingId: string;
  section: 2 | 15;
  /** 항목명 (예: "급성 독성(흡입)") */
  target: string;
  opinion: string;
};

const storageKey = (docId: string) => `msds.review-history.${docId}`;

export function loadHistory(docId: string): HistoryEntry[] {
  try {
    const raw = window.sessionStorage.getItem(storageKey(docId));
    const data: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(data) ? (data as HistoryEntry[]) : [];
  } catch {
    return [];
  }
}

/** 이력 한 줄을 더하고 더한 뒤의 전체 목록을 돌려준다 */
export function appendHistory(docId: string, entry: HistoryEntry, current: HistoryEntry[]): HistoryEntry[] {
  const next = [...current, entry];
  try {
    window.sessionStorage.setItem(storageKey(docId), JSON.stringify(next));
  } catch {
    // 저장소를 못 쓰면 이 탭 안의 상태로만 둔다
  }
  return next;
}

/** 한국 표준시(+09:00) ISO 문자열 */
export function kstNow(): string {
  const shifted = new Date(Date.now() + 9 * 60 * 60 * 1000);
  return `${shifted.toISOString().slice(0, 19)}+09:00`;
}

let seq = 0;
export const newHistoryId = () => `hist_${Date.now().toString(36)}_${(seq++).toString(36)}`;
