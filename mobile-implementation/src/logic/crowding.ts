import type { Confidence, LevelName, Levels, RouteDetail } from '../types';

export const LEVEL_ORDER: LevelName[] = ['Low', 'Medium', 'High', 'Very High'];

export const LEVEL_COLORS: Record<LevelName, string> = {
  Low: '#1e8e3e',
  Medium: '#f9ab00',
  High: '#e8710a',
  'Very High': '#d93025',
};

export const NO_DATA_COLOR = '#9aa0a6';

/**
 * What each level means to a rider, in the Problem 2 brief's words ("seats available, standing room,
 * or crowded"). With a capacity of 60 (35 seated + 25 standing), Low = under 30 on board, so seats are
 * free; Very High = over 60. The level names stay the same in the data and the API.
 */
export const LEVEL_LABEL: Record<LevelName, string> = {
  Low: 'Seats available',
  Medium: 'Standing room',
  High: 'Crowded',
  'Very High': 'Packed',
};

export const hourOf = (t: number): number => Math.floor(t / 3600) % 24;

export function levelOf(occ: number, levels: Levels): LevelName {
  for (const [threshold, name] of levels) {
    if (threshold === null || occ < threshold) return name;
  }
  return levels[levels.length - 1][1];
}

export const levelIndex = (level: LevelName): number => LEVEL_ORDER.indexOf(level);

/** Map colour for an occupancy, grey when there were no tickets. */
export const levelColor = (occ: number | null, confidence: Confidence, levels: Levels): string =>
  occ === null || confidence === 'none' ? NO_DATA_COLOR : LEVEL_COLORS[levelOf(occ, levels)];

/** Occupancy on the segment leaving stop position `pos` during `hour` (0 without tickets). */
export const segmentOcc = (detail: RouteDetail, hour: number, pos: number): number =>
  detail.crowding[String(hour)]?.occ[pos] ?? 0;

export const confidenceOf = (detail: RouteDetail, hour: number): Confidence =>
  detail.crowding[String(hour)]?.confidence ?? 'none';

/**
 * Above this occupancy no passenger count is shown: one ~4.5% mobile-ticket share for every route
 * over-scales some of them (e.g. 717A at ~7.6x capacity), so "~455 on board" wouldn't be credible.
 * The level (Very High) still holds; per-route scaling needs the ETM data.
 */
export const OVER_CAPACITY_OCC = 1.5;

/** Human-readable expected load, rounded to 5 to avoid false precision. */
export function describeLoad(occ: number, capacity: number): string {
  if (occ > OVER_CAPACITY_OCC) return `Over capacity (capacity ${capacity})`;
  const pax = Math.round((occ * capacity) / 5) * 5;
  if (pax < 5) return 'Almost empty';
  return `~${pax} on board · capacity ${capacity}`;
}

export function confidenceText(confidence: Confidence): string {
  if (confidence === 'high') return 'Based on enough October e-tickets and ≥ 2 scheduled buses this hour';
  if (confidence === 'low') return 'Low confidence: few e-tickets or few scheduled buses this hour';
  return 'No e-tickets recorded for this hour';
}
