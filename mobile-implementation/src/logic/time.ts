export const DAY = 86400;

/** "08:05" for seconds since midnight (times past midnight wrap). */
export function fmtTime(t: number): string {
  const s = ((Math.floor(t) % DAY) + DAY) % DAY;
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

/** "08:00–09:00" */
export const hourRange = (h: number): string =>
  `${String(h).padStart(2, '0')}:00–${String((h + 1) % 24).padStart(2, '0')}:00`;
