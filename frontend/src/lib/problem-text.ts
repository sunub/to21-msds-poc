/**
 * 서버의 자동 검사 오류 문자열을 검토자가 읽을 수 있는 말로 바꾼다. 순수 함수, 예외를 던지지 않는다.
 *
 * 예시 (tsx 없이 눈으로 확인):
 *  describeProblem("physchem p6:L12 VAPOR_PRESSURE | | | 221 kPa | | temp…: .cond: {'temp': 21.85, 'temp_unit': '°C'} is not valid under any of the given schemas")
 *   → { where: "증기압 · 6쪽 12줄", summary: "°C은(는) 허용되지 않는 표기입니다 (필드: temp_unit)", raw: <원문> }
 *  describeProblem("physchem p6:L13 SOLUBILITY | … cond 열: '칸=값'이 아니거나 모르는 칸 'pH=7' (칸: temp, temp_unit, …)")
 *   → { where: "용해도 · 6쪽 13줄", summary: "조건 'pH=7'를 온도·압력 등 칸으로 나눌 수 없습니다", raw: <원문> }
 */

const ITEM_NAMES: Record<string, string> = {
  VAPOR_PRESSURE: "증기압",
  SOLUBILITY: "용해도",
  LOG_KOW: "옥탄올/물 분배계수",
  VISCOSITY: "점도",
};

const WHERE = /\b[A-Za-z_]+\s+p(\d+):L(\d+)(?:\s+([A-Z][A-Z0-9_]*))?/;
const NOT_VALID = /is not valid under any of the given schemas/;
const FIELD_VALUE = /'([^']+)'\s*:\s*'([^']*)'/;
const UNKNOWN_CELL = /'칸=값'이 아니거나 모르는 칸\s*'([^']+)'/;

export function describeProblem(raw: string): {
  summary: string;
  where: string | null;
  page: number | null;
  line: number | null;
  raw: string;
} {
  const text = typeof raw === "string" ? raw : String(raw);

  let where: string | null = null;
  let page: number | null = null;
  let line: number | null = null;
  const w = WHERE.exec(text);
  if (w) {
    page = Number(w[1]);
    line = Number(w[2]);
    const place = `${w[1]}쪽 ${w[2]}줄`;
    where = w[3] ? `${ITEM_NAMES[w[3]] ?? w[3]} · ${place}` : place;
  }

  let summary = "형식을 확인해 주세요";
  const fv = NOT_VALID.test(text) ? FIELD_VALUE.exec(text) : null;
  const cell = UNKNOWN_CELL.exec(text);
  if (fv) summary = `${fv[2]}은(는) 허용되지 않는 표기입니다 (필드: ${fv[1]})`;
  else if (cell) summary = `조건 '${cell[1]}'를 온도·압력 등 칸으로 나눌 수 없습니다`;

  return { summary, where, page, line, raw: text };
}
