import type { LiveRow, Route } from '../types';
import { pointAtDistance } from './shape';
import { DAY } from './time';

/**
 * Live buses glide toward each new GPS report instead of jumping. Most buses report about every
 * 25–30 s, but some only every few minutes, so a single fixed delay leaves those buses frozen.
 * Instead, when a newer report arrives, the bus is animated from where it is drawn to that report
 * over the time until its next report should arrive (its learned cadence, or its own reporting
 * interval if longer), so it keeps moving and reaches each report about when the next comes in.
 * The glide follows the route line, so the bus stays on its road. A bus with no usable route line
 * (more than 200 m off its route, or on a route missing from GTFS) instead hops to each report:
 * a straight glide between reports ~150 m apart would cut across blocks at every bend.
 */
/** Shortest / longest time a bus takes to glide to its newest report (some buses report only every ~4 min). */
const GLIDE_MIN_S = 5;
const GLIDE_MAX_S = 300;
/** Gaps between arriving reports longer than this are outliers, not the bus's cadence. */
const CADENCE_MAX_S = 60;
/** Used until a bus's report cadence is known (the feed is published about every 25–27 s). */
const GLIDE_DEFAULT_S = 27;
/** How much each new gap between arriving reports updates the learned cadence. */
const CADENCE_WEIGHT = 0.4;
/** No newer report for this long (or its own reporting interval + a minute): it stopped reporting. */
export const STALE_S = 150;
/** A first report already older than this is stale straight away. */
const FIRST_STALE_S = 300;
/** Small backward moves along the route are GPS jitter: the bus holds still instead. */
const BACK_JITTER_M = 60;
/** Faster than this between reports means the along-route distance is not trustworthy. */
const MAX_SPEED_MS = 25;
/** Farther than this (or than the bus could drive since its last report): jump, don't glide across the city. */
const JUMP_M = 3000;
/** Glide a bit longer than the usual cadence so a slightly late report doesn't make the bus pause. */
const GLIDE_SLACK = 1.15;
/** How long a bus without a route line takes to move to its newest report. */
export const HOP_S = 1.5;
const IST_OFFSET_S = 5.5 * 3600;

export const R = {
  key: 0, route: 1, lat: 2, lon: 3, dist: 4, pos: 5, kmh: 6, ts: 7, occ: 8, conf: 9,
  prevTs: 10, prevLat: 11, prevLon: 12, prevDist: 13,
} as const;

export interface Fix {
  ts: number;
  lat: number;
  lon: number;
  dist: number | null;
}

/** One glide: from `from` (a drawn position) to the report `to`, starting at `start` (server clock). */
export interface Leg {
  from: Fix;
  to: Fix;
  start: number;
  dur: number;
  /** move along the route line (both ends have a route distance and the bus moved forward) */
  along: boolean;
}

export interface Track {
  route: string | null;
  /** last reports, newest last (at most a few) */
  fixes: Fix[];
  row: LiveRow;
  leg: Leg;
  /** server time when a newer report last arrived (an old first report counts from its own time) */
  updatedAt: number;
  /** learned seconds between this bus's new reports arriving */
  cadence: number;
}

type ShapeOf = (routeId: string) => Route['shape'] | null | undefined;

/** Seconds since midnight in Delhi (IST, no DST) for an epoch time. */
export const istSeconds = (epoch: number): number => (((epoch + IST_OFFSET_S) % DAY) + DAY) % DAY;

function metres(a: Fix, b: Fix): number {
  const dy = (b.lat - a.lat) * 110_540;
  const dx = (b.lon - a.lon) * 111_320 * Math.cos((a.lat * Math.PI) / 180);
  return Math.hypot(dx, dy);
}

/**
 * Leg from a drawn position to a new report, lasting `glide` s (when the next report should
 * arrive); `interval` = seconds between the bus's last two reports, for the plausibility checks.
 */
export function makeLeg(from: Fix, to: Fix, start: number, interval: number | null, glide = GLIDE_DEFAULT_S): Leg {
  const dur = Math.min(GLIDE_MAX_S, Math.max(GLIDE_MIN_S, glide));
  const along = from.dist !== null && to.dist !== null ? to.dist - from.dist : null;
  if (along !== null && along < 0 && along > -BACK_JITTER_M) {
    return { from, to: from, start, dur: 0, along: true };
  }
  const reach = Math.max(interval ?? 0, dur) * MAX_SPEED_MS;
  const alongOk = along !== null && along >= 0 && along <= reach + 100;
  if (!alongOk && metres(from, to) > Math.max(JUMP_M, reach)) return { from, to, start, dur: 0, along: false };
  return { from, to, start, dur: alongOk ? dur : Math.min(dur, HOP_S), along: alongOk };
}

/** Where the bus is drawn at time `t` (server clock): along the route line when it is known. */
export function legPosition(leg: Leg, t: number, shape?: Route['shape'] | null): Fix {
  const f = leg.dur <= 0 ? 1 : Math.min(1, Math.max(0, (t - leg.start) / leg.dur));
  const { from, to } = leg;
  if (f >= 1) return to;
  if (leg.along) {
    const dist = (from.dist as number) + f * ((to.dist as number) - (from.dist as number));
    if (shape) {
      const [lat, lon] = pointAtDistance(shape, dist);
      return { ts: t, lat, lon, dist };
    }
    return { ts: t, lat: from.lat + f * (to.lat - from.lat), lon: from.lon + f * (to.lon - from.lon), dist };
  }
  return { ts: t, lat: from.lat + f * (to.lat - from.lat), lon: from.lon + f * (to.lon - from.lon), dist: null };
}

export const trackPosition = (track: Track, t: number, shape?: Route['shape'] | null): Fix =>
  legPosition(track.leg, t, shape);

export function isStale(track: Track, now: number): boolean {
  const f = track.fixes;
  const interval = f.length >= 2 ? f[f.length - 1].ts - f[f.length - 2].ts : 0;
  return now - track.updatedAt > Math.max(STALE_S, Math.min(interval, GLIDE_MAX_S) + 60);
}

/**
 * Fold a feed response (received at server time `now`) into the per-bus tracks. A bus with a
 * newer report starts gliding to it from where it is drawn now; a new bus glides from its previous
 * report (sent by the server) so it moves from the first response. Buses missing from the feed
 * are dropped; a bus that switches route starts over.
 */
export function mergeTracks(tracks: Map<string, Track>, rows: LiveRow[], now: number, shapeOf?: ShapeOf, keep = 4): void {
  const seen = new Set<string>();
  for (const row of rows) {
    const key = row[R.key];
    seen.add(key);
    const fix: Fix = { ts: row[R.ts], lat: row[R.lat], lon: row[R.lon], dist: row[R.dist] };
    const track = tracks.get(key);
    if (!track || track.route !== row[R.route]) {
      const prevTs = row[R.prevTs];
      const prevLat = row[R.prevLat];
      const prevLon = row[R.prevLon];
      const prev =
        prevTs !== null && prevLat !== null && prevLon !== null && prevTs < fix.ts
          ? { ts: prevTs, lat: prevLat, lon: prevLon, dist: row[R.prevDist] }
          : null;
      tracks.set(key, {
        route: row[R.route],
        fixes: prev ? [prev, fix] : [fix],
        row,
        leg: prev
          ? makeLeg(prev, fix, now, fix.ts - prev.ts, Math.max(GLIDE_DEFAULT_S, fix.ts - prev.ts))
          : { from: fix, to: fix, start: now, dur: 0, along: false },
        updatedAt: now - fix.ts > FIRST_STALE_S ? fix.ts : now,
        cadence: GLIDE_DEFAULT_S,
      });
      continue;
    }
    track.row = row;
    const last = track.fixes[track.fixes.length - 1];
    if (fix.ts <= last.ts) continue;
    const gap = now - track.updatedAt;
    if (gap >= GLIDE_MIN_S && gap <= CADENCE_MAX_S) track.cadence += CADENCE_WEIGHT * (gap - track.cadence);
    const shape = track.route && shapeOf ? shapeOf(track.route) : null;
    const interval = fix.ts - last.ts;
    // glide until this bus's next report should arrive: its usual cadence, or longer for a bus
    // that only reports every few minutes
    track.leg = makeLeg(legPosition(track.leg, now, shape), fix, now, interval, Math.max(track.cadence * GLIDE_SLACK, interval));
    track.fixes.push(fix);
    if (track.fixes.length > keep) track.fixes.shift();
    track.updatedAt = now;
  }
  for (const key of [...tracks.keys()]) if (!seen.has(key)) tracks.delete(key);
}

/** "12 s", "3 min" */
export function fmtAge(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return s < 90 ? `${s} s` : `${Math.round(s / 60)} min`;
}
