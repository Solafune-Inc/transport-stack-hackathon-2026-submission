import { HOP_S, isStale, istSeconds, legPosition, makeLeg, mergeTracks, trackPosition, type Track } from '../logic/live';
import type { LiveRow } from '../types';

const row = (key: string, route: string | null, ts: number, lat: number, dist: number | null): LiveRow => [
  key, route, lat, 77, dist, dist === null ? null : 0, 20, ts, 0.5, 1, null, null, null, null,
];
const withPrev = (r: LiveRow, ts: number, lat: number, dist: number | null): LiveRow => {
  const out = [...r] as LiveRow;
  out[10] = ts; out[11] = lat; out[12] = 77; out[13] = dist;
  return out;
};

// an L-shaped route: east 1 km, then north 1 km
const shape: [number, number, number][] = [[28, 77, 0], [28, 77.01, 1000], [28.01, 77.01, 2000]];

describe('mergeTracks', () => {
  it('starts a new bus gliding from its previous report so it moves from the first response', () => {
    const tracks = new Map<string, Track>();
    mergeTracks(tracks, [withPrev(row('a', '623UP', 130, 28.2, 300), 100, 28.1, 10)], 1000);
    const t = tracks.get('a')!;
    expect(t.leg).toMatchObject({ start: 1000, dur: 30, along: true });
    expect(trackPosition(t, 1000).lat).toBeCloseTo(28.1);
    expect(trackPosition(t, 1015).dist).toBeCloseTo(155);
    expect(trackPosition(t, 1030).lat).toBeCloseTo(28.2);
  });

  it('glides to a newer report from where the bus is drawn, with no jump', () => {
    const tracks = new Map<string, Track>();
    mergeTracks(tracks, [withPrev(row('a', '623UP', 130, 28, 600), 100, 28, 0)], 1000);
    const before = trackPosition(tracks.get('a')!, 1010, shape);
    const next = row('a', '623UP', 160, 28, 900);
    next[3] = 77.009;
    mergeTracks(tracks, [next], 1010, () => shape);
    const t = tracks.get('a')!;
    expect(trackPosition(t, 1010, shape)).toMatchObject({ lat: before.lat, lon: before.lon, dist: before.dist });
    expect(t.leg.along).toBe(true);
    expect(t.leg.dur).toBeGreaterThanOrEqual(30);
    expect(trackPosition(t, 1010 + t.leg.dur / 2, shape).dist).toBeCloseTo((before.dist! + 900) / 2);
    expect(trackPosition(t, 1010 + t.leg.dur, shape).dist).toBeCloseTo(900);
  });

  it('keeps a bus that reports only every few minutes moving, and fresh, until its next report', () => {
    const tracks = new Map<string, Track>();
    mergeTracks(tracks, [withPrev(row('a', '623UP', 1000, 28.2, 2400), 760, 28.1, 0)], 1000);
    const t = tracks.get('a')!;
    expect(t.leg.dur).toBe(240);
    expect(trackPosition(t, 1120).dist).toBeCloseTo(1200);
    expect(isStale(t, 1250)).toBe(false);
    expect(isStale(t, 1310)).toBe(true);
  });

  it('ignores repeated reports, drops buses that left the feed, and restarts on a route switch', () => {
    const tracks = new Map<string, Track>();
    mergeTracks(tracks, [row('a', '623UP', 990, 28.1, 10), row('b', '319UP', 990, 28.2, 5)], 1000);
    mergeTracks(tracks, [row('a', '623UP', 990, 28.1, 10)], 1030);
    expect(tracks.get('a')!.updatedAt).toBe(1000);
    expect(tracks.has('b')).toBe(false);
    mergeTracks(tracks, [row('a', '623DOWN', 1023, 28.2, 0)], 1060);
    expect(tracks.get('a')!.fixes).toHaveLength(1);
  });

  it('marks a bus stale once it stops sending new reports, or at once if its first report is old', () => {
    const tracks = new Map<string, Track>();
    mergeTracks(tracks, [row('a', '623UP', 990, 28.1, 10), row('old', '623UP', 400, 28.1, 10)], 1000);
    expect(isStale(tracks.get('a')!, 1100)).toBe(false);
    expect(isStale(tracks.get('a')!, 1200)).toBe(true);
    expect(isStale(tracks.get('old')!, 1000)).toBe(true);
  });
});

describe('legs', () => {
  it('follow the route line around corners instead of cutting across', () => {
    const leg = makeLeg({ ts: 0, lat: 28, lon: 77.005, dist: 500 }, { ts: 60, lat: 28.005, lon: 77.01, dist: 1500 }, 0, 60, 60);
    expect(legPosition(leg, 30, shape)).toMatchObject({ lat: 28, lon: 77.01, dist: 1000 });
  });

  it('hold still on small backward GPS jitter but jump across implausibly long gaps', () => {
    const jitter = makeLeg({ ts: 0, lat: 28, lon: 77, dist: 900 }, { ts: 30, lat: 28, lon: 77, dist: 870 }, 0, 30);
    expect(legPosition(jitter, 15, shape).dist).toBe(900);
    const far = makeLeg({ ts: 0, lat: 28, lon: 77, dist: null }, { ts: 30, lat: 28.1, lon: 77, dist: null }, 0, 30);
    expect(far.dur).toBe(0);
  });

  it('hop quickly to the next report when there is no route line to follow, instead of cutting across blocks', () => {
    const offRoute = makeLeg({ ts: 0, lat: 28, lon: 77, dist: null }, { ts: 30, lat: 28.002, lon: 77, dist: null }, 0, 30);
    expect(offRoute.dur).toBe(HOP_S);
    expect(legPosition(offRoute, HOP_S / 2).lat).toBeCloseTo(28.001);
    expect(legPosition(offRoute, HOP_S).lat).toBe(28.002);
    // on its route, the same move glides along the line until the next report is due
    const onRoute = makeLeg({ ts: 0, lat: 28, lon: 77.002, dist: 200 }, { ts: 30, lat: 28, lon: 77.004, dist: 400 }, 0, 30, 30);
    expect(onRoute).toMatchObject({ along: true, dur: 30 });
  });
});

it('converts epoch seconds to the time of day in Delhi', () => {
  expect(istSeconds(Date.UTC(2026, 10, 19, 6, 30) / 1000)).toBe(12 * 3600);
  expect(istSeconds(Date.UTC(2026, 10, 19, 20, 0) / 1000)).toBe(1.5 * 3600);
});
