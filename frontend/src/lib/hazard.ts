/*
 * 2항 탭의 표시 규칙. 화면과 분리한 순수 함수라 서버 없이 시험한다 (hazard.test.ts).
 * 판정을 새로 계산하지 않는다. 처리 대상·정렬·문구는 15항과 같은 규칙(regulation.ts)을 쓴다.
 */
import type { Finding, FindingDisplay, JudgmentView } from "@/api/judgment";
import { byPriority, isMatch, isNote, needsAction } from "./regulation.ts";

/** 시안 2.3 의 건수 알약 순서. 전체는 null 이다 */
export const HAZARD_FILTERS = ["불일치", "경계", "근거부족", "경고", "일치"] as const;
export type HazardFilter = (typeof HAZARD_FILTERS)[number];

export const isHazardFilter = (value: string | null): value is HazardFilter =>
  HAZARD_FILTERS.some((filter) => filter === value);

/** 고른 MSDS 의 2항 판정 */
export function hazardFindings(view: JudgmentView, msdsIndex: number) {
  const result = view.consistency.results.find((r) => r.msds_index === msdsIndex) ?? view.consistency.results[0];
  return result.findings.filter((f) => f.section === "2");
}

/**
 * 건수 알약. 전체는 범위 외·참고를 뺀 판정 수다 (시안: 전체 9 = 불일치 1 + 경계 0 + 근거부족 2 + 경고 1 + 일치 5).
 * 엔진은 표시 요소 경고도 불일치·낮음으로 내므로 경고 알약은 있을 때만 보인다.
 */
export function hazardFilterItems(findings: Finding[]) {
  const judged = findings.filter((f) => !isNote(f));
  return [
    { id: "all", label: `전체 ${judged.length}` },
    ...HAZARD_FILTERS.flatMap((filter) => {
      const count = judged.filter((f) => f.verdict === filter).length;
      return filter === "경고" && count === 0 ? [] : [{ id: filter, label: `${filter} ${count}` }];
    }),
  ];
}

export type HazardTable = {
  /** 바로 보이는 줄 */
  rows: Finding[];
  /** 전체 보기에서 접어 두는 일치 줄 */
  matches: Finding[];
  /** 전체 보기 아래에 따로 접어 두는 범위 외·참고 줄 */
  notes: Finding[];
};

export function buildHazardTable(findings: Finding[], filter: HazardFilter | null): HazardTable {
  if (filter) {
    return { rows: findings.filter((f) => !isNote(f) && f.verdict === filter).sort(byPriority), matches: [], notes: [] };
  }
  return { rows: findings.filter(needsAction).sort(byPriority), matches: findings.filter(isMatch), notes: findings.filter(isNote) };
}

/** 고른 줄이 지금 거르기로 표에 없는가 */
export const hiddenByFilter = (finding: Finding, filter: HazardFilter | null) =>
  filter !== null && (isNote(finding) || finding.verdict !== filter);

export type ValueEmphasis = "differ" | "same" | "neutral";

/** 값 칩의 강조. 불일치만 틀린 값과 맞는 값으로 가른다. 경계·근거부족은 기준값이 정답이 아니어서 중립이다 */
export function valueEmphasis(finding: Finding): ValueEmphasis {
  if (isNote(finding)) return "neutral";
  if (finding.verdict === "불일치") return "differ";
  return finding.verdict === "일치" ? "same" : "neutral";
}

/** 원문 쪽 버튼. 같은 항·쪽은 한 번만 보인다 */
export function sourceTabs(display: FindingDisplay | null | undefined) {
  const seen = new Set<string>();
  return (display?.source_pages ?? []).flatMap((source) => {
    const id = `${source.section}:${source.page}`;
    if (seen.has(id)) return [];
    seen.add(id);
    return [{ id, label: `${source.section}항 p.${source.page}`, page: source.page }];
  });
}

/**
 * 먼저 열 쪽. 판정한 항(2항·15항)의 근거 쪽이고, 없으면 그 항 첫 쪽이다.
 * 다른 항 근거(3항 성분표, 11항 독성값)는 버튼으로 옮겨 간다. "…항 첫 쪽을 보여 줍니다" 안내와 맞춘다.
 */
export function ownSectionPage(display: FindingDisplay | null | undefined, section: number, firstPage: number) {
  return display?.source_pages.find((source) => source.section === section)?.page ?? firstPage;
}

/** 원문 쪽 버튼. 판정한 항 근거가 없으면 그 항 첫 쪽 버튼을 앞에 둬 돌아올 수 있게 한다. 근거가 없으면 버튼도 없다 */
export function sectionTabs(display: FindingDisplay | null | undefined, section: number, firstPage: number) {
  const tabs = sourceTabs(display);
  if (!tabs.length || tabs.some((tab) => tab.id.startsWith(`${section}:`))) return tabs;
  return [{ id: `${section}:${firstPage}`, label: `${section}항 p.${firstPage}`, page: firstPage }, ...tabs];
}

/** 상세의 접힘 제목. 2항 밖 근거 쪽(11항 독성값 등)을 함께 적는다 */
export function basisTitle(display: FindingDisplay) {
  const others = sourceTabs(display).filter((tab) => !tab.id.startsWith("2:"));
  const title = display.calc_lines.length > 0 ? "판단 근거와 계산 과정" : "판단 근거";
  return others.length ? `${title} · ${others.map((tab) => tab.label).join(", ")}` : title;
}
