import type { Direction, NetStop, StopRow } from '../types';

const ROUTE_RE = /^(.*?)(UP|DOWN)(\d*)$/;

/** '623UP' -> ['623', 'UP']; '116AUP2' -> ['116A', 'UP']; 'DS CIRCULAR' -> ['DS CIRCULAR', null] (as the server). */
export function routeParts(id: string): [string, Direction | null] {
  const m = ROUTE_RE.exec(id);
  return m && m[1] ? [m[1], m[2] as Direction] : [id, null];
}

export const toNetStop = ([id, name, lat, lon, nRoutes]: StopRow): NetStop => ({ id, name, lat, lon, nRoutes });

/** "Shahdara Terminal to Nangal Dewat" -> "Nangal Dewat" (null when the description has no "to"). */
export function terminalOf(description: string): string | null {
  const parts = description.split(' to ');
  return parts.length === 2 && parts[1].trim() ? parts[1].trim() : null;
}

/** Rounded people count without false precision. */
export function fmtPeople(n: number): string {
  if (n < 1) return '<1';
  if (n < 20) return String(Math.round(n));
  return String(Math.round(n / 5) * 5);
}

/** Stop name for matching both sides of a road (same rule as the server). */
export const normName = (name: string): string =>
  name.toLowerCase().replace(/[^0-9a-z]+/g, ' ').trim().replace(/\s+/g, ' ');

export function metres(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const dy = (b.lat - a.lat) * 110_540;
  const dx = (b.lon - a.lon) * 111_320 * Math.cos((a.lat * Math.PI) / 180);
  return Math.hypot(dx, dy);
}

/** Stops with the same name this close are one place (e.g. both sides of a road). */
export const SAME_STOP_M = 400;

export interface StopGroup {
  /** the stop with the most routes; the planner sends it to the server */
  id: string;
  name: string;
  ids: string[];
  nRoutes: number;
}

/** One entry per place for the stop search: same-named stops within SAME_STOP_M are merged. */
export function groupStops(stops: NetStop[]): StopGroup[] {
  const byName = new Map<string, NetStop[]>();
  for (const s of stops) {
    const key = normName(s.name);
    const list = byName.get(key);
    if (list) list.push(s);
    else byName.set(key, [s]);
  }
  const groups: StopGroup[] = [];
  for (const list of byName.values()) {
    const left = [...list].sort((a, b) => b.nRoutes - a.nRoutes);
    while (left.length) {
      const head = left[0];
      const members = left.filter((s) => metres(head, s) <= SAME_STOP_M);
      groups.push({
        id: head.id,
        name: head.name,
        ids: members.map((s) => s.id),
        nRoutes: Math.max(...members.map((s) => s.nRoutes)),
      });
      for (const m of members) left.splice(left.indexOf(m), 1);
    }
  }
  return groups.sort((a, b) => a.name.localeCompare(b.name) || b.nRoutes - a.nRoutes);
}

/** Search the grouped stops: names starting with the query first, then containing it. */
export function searchStops(groups: StopGroup[], query: string, max = 60): StopGroup[] {
  const q = normName(query);
  if (!q) return [];
  const starts: StopGroup[] = [];
  const contains: StopGroup[] = [];
  for (const g of groups) {
    const n = normName(g.name);
    if (n.startsWith(q)) starts.push(g);
    else if (n.includes(q)) contains.push(g);
    if (starts.length >= max) break;
  }
  return [...starts, ...contains].slice(0, max);
}
