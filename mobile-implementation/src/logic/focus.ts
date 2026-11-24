import type { Highlight, MapFocus, MapRoute, RouteDetail, StopInfo } from '../types';

/**
 * What the map shows:
 * - nothing selected: stops and live buses only from DETAIL_ZOOM in; zoomed out, just the basemap;
 * - a stop: every route number through it (both directions), only buses on those routes, at any
 *   zoom; tapping a route in its sheet narrows it to that route;
 * - a bus: its own route and the buses on it;
 * - a chosen trip: its routes, with the rides highlighted.
 * A selection is cleared only by closing its sheet (or Android Back), never by tapping the map.
 */
export const DETAIL_ZOOM = 14;
/** stops along the selected routes appear from this zoom */
export const ROUTE_STOPS_ZOOM = 13;
/** up to this many buses on screen get labelled chips; more are drawn as dots */
export const CHIP_LIMIT = 60;
/** buses with no route colour (nothing selected, Bus Routes tab) */
export const CITY_FILL = '#455a64';
/** one colour per route number, in the order the selection lists them */
export const ROUTE_PALETTE = [
  '#1a73e8', '#8e24aa', '#0b8043', '#e37400', '#d81b60', '#00897b',
  '#5e35b1', '#6d4c41', '#039be5', '#9e9d24', '#f4511e', '#3949ab',
];

export type Selection =
  | { kind: 'stop'; stopId: string; only: string | null }
  | { kind: 'live'; key: string }
  /** the hourly crowding sheet of a route, opened from a stop or bus sheet (closing returns there) */
  | { kind: 'route'; routeId: string; parent: Selection }
  | { kind: 'liveInfo' }
  | { kind: 'about' }
  | null;

export interface FocusPlan {
  routeIds: string[];
  busKeys: string[];
  pinStop: string | null;
  highlights: Highlight[];
}

export interface FocusContext {
  /** details of the selected stop, once loaded */
  stopInfo: StopInfo | null;
  /** route of a live bus (null when unknown) */
  routeOfBus(key: string): string | null;
  /** the rides of the chosen trip (none = no trip) */
  journey: Highlight[];
}

/** Routes, buses and pinned stop for a selection; null = nothing selected (zoom decides). */
export function focusPlan(sel: Selection, ctx: FocusContext): FocusPlan | null {
  switch (sel?.kind) {
    case 'stop': {
      const info = ctx.stopInfo?.stop.id === sel.stopId ? ctx.stopInfo : null;
      const routeIds = sel.only ? [sel.only] : info ? info.routes.map((r) => r.id) : [];
      return { routeIds, busKeys: [], pinStop: sel.stopId, highlights: [] };
    }
    case 'live': {
      const route = ctx.routeOfBus(sel.key);
      return { routeIds: route ? [route] : [], busKeys: [sel.key], pinStop: null, highlights: [] };
    }
    case 'route': {
      const parent = focusPlan(sel.parent, ctx);
      return { routeIds: [sel.routeId], busKeys: parent?.busKeys ?? [], pinStop: parent?.pinStop ?? null, highlights: [] };
    }
    default:
      return ctx.journey.length
        ? { routeIds: [...new Set(ctx.journey.map((h) => h.routeId))], busKeys: [], pinStop: null, highlights: ctx.journey }
        : null;
  }
}

/** A colour per route number, in order of first appearance. */
export function colorsByNumber(numbers: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const n of numbers) {
    if (!(n in out)) out[n] = ROUTE_PALETTE[Object.keys(out).length % ROUTE_PALETTE.length];
  }
  return out;
}

/** The focus the map draws: loaded routes only (others appear as they arrive), crowding for `hour`. */
export function toMapFocus(
  plan: FocusPlan,
  details: Record<string, RouteDetail>,
  colors: Record<string, string>,
  hour: number,
  fit: boolean,
): MapFocus {
  const routes: MapRoute[] = [];
  for (const id of plan.routeIds) {
    const d = details[id];
    if (!d) continue;
    const hc = d.crowding[String(hour)];
    routes.push({
      id,
      number: d.route.number,
      direction: d.route.direction,
      color: colors[d.route.number] ?? ROUTE_PALETTE[0],
      shape: d.route.shape,
      stops: d.route.stops,
      occ: hc?.occ ?? [],
      confidence: hc?.confidence ?? 'none',
    });
  }
  return { routes, busRoutes: plan.routeIds, busKeys: plan.busKeys, pinStop: plan.pinStop, highlights: plan.highlights, fit };
}

export interface BusFilter {
  routes: Set<string>;
  keys: Set<string>;
}

export const busFilterOf = (focus: MapFocus | null): BusFilter | null =>
  focus ? { routes: new Set(focus.busRoutes), keys: new Set(focus.busKeys) } : null;

/** Is a live bus drawn? Selected routes' buses at any zoom; with no selection, all when zoomed in. */
export function busVisible(route: string | null, key: string, zoom: number, filter: BusFilter | null): boolean {
  if (!filter) return zoom >= DETAIL_ZOOM;
  return filter.keys.has(key) || (route !== null && filter.routes.has(route));
}

/** Are all stops in view drawn? Only with no selection and zoomed in (a selection shows its own). */
export const allStopsVisible = (zoom: number, focused: boolean): boolean => !focused && zoom >= DETAIL_ZOOM;
