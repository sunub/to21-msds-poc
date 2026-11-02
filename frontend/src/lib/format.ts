/** 화면에 보이는 날짜·크기 표기. 시각은 늘 한국 시간으로 보여 준다. */

const PARTS = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

/** "2026.10.31 오전 10:12" */
export function formatDateTime(iso: string) {
  const p = Object.fromEntries(PARTS.formatToParts(new Date(iso)).map((x) => [x.type, x.value]));
  return `${p.year}.${p.month}.${p.day} ${p.dayPeriod} ${p.hour}:${p.minute}`;
}

/** 오늘 날짜 (한국 시간) "YYYY-MM-DD" */
export function todayKst() {
  return new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Seoul" });
}

/** 482113 → "471KB", 3_500_000 → "3.3MB" */
export function formatBytes(n: number) {
  if (n < 1024 * 1024) return `${Math.max(1, Math.round(n / 1024))}KB`;
  return `${(n / 1024 / 1024).toFixed(1)}MB`;
}
