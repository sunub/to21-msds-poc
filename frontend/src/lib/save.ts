/*
 * 저장 화면(3.1~3.2)의 표시 규칙. 화면과 분리한 순수 함수라 서버 없이 시험한다 (save.test.ts).
 * 건수를 새로 계산하지 않는다. save-overview 가 준 값을 고르고 문장으로 만든다.
 */
import type { ReportInclude, SaveOverview, Snapshot, VerdictCounts } from "@/api/save";
import type { Tone } from "@/components/ui";

/** 시안의 요약 줄 순서. 참고·범위 외는 판정이 아니어서 세지 않는다 */
const VERDICTS: { verdict: keyof VerdictCounts; tone: Tone }[] = [
  { verdict: "불일치", tone: "danger" },
  { verdict: "경계", tone: "warning" },
  { verdict: "근거부족", tone: "neutral" },
  { verdict: "경고", tone: "warning" },
  { verdict: "일치", tone: "success" },
];

export function verdictSummary(total: VerdictCounts) {
  return VERDICTS.map(({ verdict, tone }) => ({ verdict, tone, count: total[verdict] }));
}

const PROCESSED = ["불일치 확정", "예외 승인", "확인"] as const;

/** '처리 4건 (불일치 확정 1 · 예외 승인 1 · 확인 2)' */
export function processedText(reviews: SaveOverview["reviews"]) {
  const parts = PROCESSED.filter((k) => reviews[k] > 0).map((k) => `${k} ${reviews[k]}`);
  const total = PROCESSED.reduce((n, k) => n + reviews[k], 0);
  return parts.length ? `처리 ${total}건 (${parts.join(" · ")})` : `처리 ${total}건`;
}

export type SaveState =
  | { kind: "none" }
  /** 최근 저장본이 지금 판정·값과 같다 */
  | { kind: "current"; snapshot: Snapshot }
  /** 저장한 뒤 값을 고쳤거나 다시 판정했다. 다시 저장해야 지금 내용이 남는다 */
  | { kind: "changed"; snapshot: Snapshot };

/**
 * 판정 버전과 넘김 번호로만 비교한다. 저장 뒤의 검토 처리는 save-overview 에 처리 번호가 없어 여기서 알 수 없다
 * (그 차이는 서버의 데이터 등급이 맡는다).
 */
export function saveState(ov: SaveOverview): SaveState {
  const last = ov.snapshots[0];
  if (!last) return { kind: "none" };
  const same = last.version === ov.version && last.handoff_seq === ov.handoff_seq;
  return { kind: same ? "current" : "changed", snapshot: last };
}

export function headline(ov: SaveOverview): { title: string; body: string } {
  const state = saveState(ov);
  const unreviewed = ov.reviews.미검토;
  if (state.kind === "none") {
    return {
      title: "검토 결과를 저장합니다",
      body: unreviewed
        ? `처리하지 않은 판정 ${unreviewed}건은 "미검토"로 기록됩니다. 저장한 뒤 재생성 MSDS와 판정이 담긴 PDF로 내려받을 수 있습니다.`
        : "결과를 데이터베이스에 저장하고, 재생성 MSDS와 판정이 담긴 PDF로 내려받을 수 있습니다.",
    };
  }
  if (state.kind === "changed") {
    return {
      title: "저장한 뒤 바뀐 내용이 있습니다",
      body: "추출값을 고쳤거나 다시 판정했습니다. 다시 저장해야 지금 내용이 데이터베이스에 남습니다.",
    };
  }
  if (unreviewed) {
    return {
      title: "저장했습니다. 처리하지 않은 판정이 남아 있습니다",
      body: '결과를 데이터베이스에 저장했습니다. 미검토 판정은 그대로 "미검토"로 기록되고, PDF에도 같은 표시가 붙습니다.',
    };
  }
  return {
    title: "검토를 마쳤습니다",
    body: "결과를 데이터베이스에 저장하고, 재생성 MSDS와 판정이 담긴 PDF로 내려받을 수 있습니다.",
  };
}

/** 값의 출처별 칸 수. 서버는 칸 검수를 확인·수정·되돌림만 기록한다 (추가·삭제는 없다) */
export function valueRows(values: SaveOverview["values"]) {
  return [
    { label: "확인함", count: values.confirmed },
    { label: "수정됨", count: values.edited },
    { label: "미검수 (확인하지 않음)", count: values.model_as_is },
  ];
}

/** PDF 구성. 표지는 늘 들어가고, 나머지는 서버 include 칸 하나씩이다 */
export const REPORT_PARTS: { key: keyof ReportInclude; label: string; note: string }[] = [
  { key: "regenerated_msds", label: "재생성 MSDS", note: "최종 값으로 만든 16항 문서" },
  { key: "findings_2", label: "2항 판정 표", note: "처리 상태와 검토자 의견" },
  { key: "findings_15", label: "15항 판정 표", note: "처리 상태와 검토자 의견" },
  { key: "components", label: "성분별 요약", note: "기준 분류와 ATE" },
  { key: "history", label: "부록 · 처리 이력", note: "누가 언제 무엇을 처리했는지" },
];

export function reportInclude(picked: Partial<Record<keyof ReportInclude, boolean>>): ReportInclude {
  return Object.fromEntries(REPORT_PARTS.map((p) => [p.key, !!picked[p.key]])) as ReportInclude;
}

/** 서버가 Content-Disposition 으로 준 이름. 다른 출처라 헤더를 못 읽으면 원본 파일 이름으로 짓는다 */
export function reportFileName(disposition: string | null, sourceFilename: string, format: string) {
  const encoded = disposition && /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1];
  if (encoded) return decodeURIComponent(encoded);
  return `${sourceFilename.replace(/\.pdf$/i, "")}_MSDS_검토결과.${format}`;
}
