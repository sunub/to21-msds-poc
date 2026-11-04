/*
 * 검토 이력 탭의 표시 규칙. 화면과 분리한 순수 함수라 서버 없이 시험한다 (history.test.ts).
 * 이력은 두 서버(추출값 A2, 판정 B2)에서 따로 오고, 화면이 시각순으로 합친다 (contracts/6-screens.md).
 */
import type { HistoryEntry } from "@/api/history";

export type HistoryKind = "all" | "judgment" | "values" | "save";
export type HistoryLink = { tab: "hazard" | "regulation" | "values"; finding?: string; msds?: number } | { save: true } | null;

export const KIND_LABEL: Record<Exclude<HistoryKind, "all">, string> = {
  judgment: "판정 처리",
  values: "추출값",
  save: "저장",
};

export function kindOf(entry: HistoryEntry): Exclude<HistoryKind, "all"> {
  if (entry.area === "추출값") return "values";
  if (entry.area === "저장") return "save";
  return "judgment";
}

/**
 * 최근 처리가 위로. 글자가 아니라 시각으로 비교한다(서버마다 시간대 표기가 다를 수 있다).
 * 같은 시각이면 받은 순서의 뒤쪽이 나중 처리다.
 */
export function mergeHistory(...sources: HistoryEntry[][]): HistoryEntry[] {
  return sources
    .flat()
    .map((entry, order) => ({ entry, order, time: Date.parse(entry.at) }))
    .sort((a, b) => b.time - a.time || b.order - a.order)
    .map((x) => x.entry);
}

export const filterHistory = (entries: HistoryEntry[], kind: HistoryKind) =>
  kind === "all" ? entries : entries.filter((e) => kindOf(e) === kind);

/** 기록이 있는 구분만 건수와 함께. 전체는 늘 맨 앞에 둔다 */
export function historyPills(entries: HistoryEntry[]) {
  const kinds = (["judgment", "values", "save"] as const).flatMap((kind) => {
    const count = filterHistory(entries, kind).length;
    return count ? [{ id: kind as HistoryKind, label: `${KIND_LABEL[kind]} ${count}` }] : [];
  });
  return [{ id: "all" as HistoryKind, label: `전체 ${entries.length}` }, ...kinds];
}

/** finding ID 앞의 MSDS 번호. m1/F15:… → 1 */
const msdsOfFinding = (id: string) => Number(/^m(\d+)\//.exec(id)?.[1] ?? 0);

/** 이동 칸이 갈 곳. ref 는 계약상 형식이 느슨해 맞는 값이 있을 때만 쓴다 */
export function linkOf(entry: HistoryEntry): HistoryLink {
  if (entry.area === "저장") return { save: true };
  if (entry.area === "추출값") return { tab: "values" };
  const tab = entry.area === "2항" ? "hazard" : "regulation";
  const finding = entry.ref?.finding_id;
  return finding ? { tab, finding, msds: msdsOfFinding(finding) } : { tab };
}
