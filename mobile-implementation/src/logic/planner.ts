import type { Confidence, LevelName, PlanLeg, PlanOptionRaw } from '../types';
import { levelIndex } from './crowding';

export type SortMode = 'balanced' | 'fastest' | 'least_crowded';

/** Minutes of extra travel a rider would accept to avoid each crowding level ("Balanced" sort). */
export const CROWD_PENALTY_MIN: Record<LevelName, number> = { Low: 0, Medium: 4, High: 10, 'Very High': 18 };
/** Minutes of extra travel a rider would accept to avoid one change of bus ("Balanced" sort). */
export const CHANGE_PENALTY_MIN = 5;

export interface JourneyOption {
  routeId: string;
  trip: number;
  fromPos: number;
  toPos: number;
  fromStop: string;
  toStop: string;
  depart: number;
  arrive: number;
  waitMin: number;
  rideMin: number;
  totalMin: number;
  occ: number;
  level: LevelName;
  confidence: Confidence;
  /** the rides in order: one for a direct bus, two with a change */
  legs: PlanLeg[];
  changes: number;
  walkMin: number;
  score: number;
}

export interface LeaveLater {
  option: JourneyOption;
  instead: JourneyOption;
  extraMin: number;
}

/** Server options (GET /api/plan) for a rider leaving at `t`, with the balanced score. */
export function toOptions(raw: PlanOptionRaw[], t: number): JourneyOption[] {
  return raw.map(({ legs, changes, walk_m: _walkM, walk_s, ...o }) => {
    const totalMin = (o.arrive - t) / 60;
    const rides = legs ?? [{ ...o, fromName: '', toName: '' }];
    const n = changes ?? rides.length - 1;
    return {
      ...o,
      waitMin: (o.depart - t) / 60,
      rideMin: (o.arrive - o.depart) / 60,
      totalMin,
      legs: rides,
      changes: n,
      walkMin: (walk_s ?? 0) / 60,
      score: totalMin + CROWD_PENALTY_MIN[o.level] + CHANGE_PENALTY_MIN * n,
    };
  });
}

/** "Change at X · wait ~6 min", or "Change at X → walk ~2 min to Y · wait ~4 min"; '' if direct. */
export function changeText(o: JourneyOption): string {
  if (o.legs.length < 2) return '';
  const [a, b] = o.legs;
  const wait = Math.max(0, Math.round((b.depart - a.arrive) / 60 - o.walkMin));
  const walk = a.toStop === b.fromStop ? '' : ` → walk ~${Math.max(1, Math.round(o.walkMin))} min to ${b.fromName}`;
  return `Change at ${a.toName}${walk} · wait ~${wait} min`;
}

export function sortOptions(options: JourneyOption[], sort: SortMode): JourneyOption[] {
  const cmp: Record<SortMode, (a: JourneyOption, b: JourneyOption) => number> = {
    fastest: (a, b) => a.arrive - b.arrive || a.changes - b.changes,
    least_crowded: (a, b) => levelIndex(a.level) - levelIndex(b.level) || a.arrive - b.arrive,
    balanced: (a, b) => a.score - b.score || a.arrive - b.arrive,
  };
  return [...options].sort(cmp[sort]);
}

/**
 * If the earliest-arriving option (what a time-only planner shows) is High or Very High,
 * suggest the earliest less-crowded option with as many changes arriving at most `maxExtraMin` later.
 */
export function findLeaveLater(options: JourneyOption[], maxExtraMin = 45): LeaveLater | null {
  if (!options.length) return null;
  const first = sortOptions(options, 'fastest')[0];
  const firstLevel = levelIndex(first.level);
  if (firstLevel < levelIndex('High')) return null;
  const better = sortOptions(
    options.filter(
      (o) => o.changes === first.changes && levelIndex(o.level) < firstLevel && o.arrive - first.arrive <= maxExtraMin * 60,
    ),
    'fastest',
  )[0];
  if (!better) return null;
  return { option: better, instead: first, extraMin: Math.round((better.arrive - first.arrive) / 60) };
}
