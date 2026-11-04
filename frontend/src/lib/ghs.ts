/*
 * GHS 그림문자 코드 → 코드별 대표 이미지 (public/msds-labels/ghs). 등급별 이미지·신호어·문구는 label-catalog.ts 에 있다.
 * 폐쇄망에 정적 빌드만 반입하므로 이미지를 빌드에 함께 넣는다.
 */
const GHS_NAMES: Record<string, string> = {
  GHS01: "폭발성",
  GHS02: "인화성",
  GHS03: "산화성",
  GHS04: "고압가스",
  GHS05: "부식성",
  GHS06: "급성 독성",
  GHS07: "경고",
  GHS08: "건강 유해성",
  GHS09: "수생환경 유해성",
};

/** 이미지가 있는 코드면 경로와 대체 글, 없으면 null */
export function ghsPictogram(code: string): { src: string; alt: string } | null {
  if (!Object.hasOwn(GHS_NAMES, code)) return null;
  return { src: `/msds-labels/ghs/${code}.png`, alt: `${code} ${GHS_NAMES[code]} 그림문자` };
}
