import {
  DETAIL_ZOOM,
  ROUTE_PALETTE,
  allStopsVisible,
  busFilterOf,
  busVisible,
  colorsByNumber,
  focusPlan,
  toMapFocus,
  type FocusContext,
} from '../logic/focus';
import type { RouteDetail, StopInfo, StopRoute } from '../types';

const stopRoute = (id: string, number: string, serves = true): StopRoute => ({
  id, number, direction: id.endsWith('DOWN') ? 'DOWN' : 'UP', description: 'A to B', serves,
  pos: serves ? 1 : null, n_stops: 5, occ: null, confidence: 'none', next: [],
});
const info: StopInfo = {
  stop: { id: 'S1', name: 'Stop', lat: 28, lon: 77, n_routes_all: 3 },
  t: 0,
  busyness: null,
  routes: [stopRoute('10UP', '10'), stopRoute('10DOWN', '10', false), stopRoute('20UP', '20')],
};
const ctx: FocusContext = { stopInfo: info, routeOfBus: (key) => (key === 'bus1' ? '20UP' : null), journey: [] };

describe('focusPlan', () => {
  it('shows every route through a tapped stop (both directions) and only their buses, or one route alone', () => {
    expect(focusPlan({ kind: 'stop', stopId: 'S1', only: null }, ctx)).toEqual({
      routeIds: ['10UP', '10DOWN', '20UP'], busKeys: [], pinStop: 'S1', highlights: [],
    });
    expect(focusPlan({ kind: 'stop', stopId: 'S1', only: '10DOWN' }, ctx)?.routeIds).toEqual(['10DOWN']);
    // another stop's details are not used while the tapped one loads
    expect(focusPlan({ kind: 'stop', stopId: 'S2', only: null }, ctx)?.routeIds).toEqual([]);
  });

  it("shows a tapped bus's own route, and keeps the bus or stop under an opened route sheet", () => {
    expect(focusPlan({ kind: 'live', key: 'bus1' }, ctx)).toMatchObject({ routeIds: ['20UP'], busKeys: ['bus1'] });
    expect(focusPlan({ kind: 'live', key: 'unknown' }, ctx)).toMatchObject({ routeIds: [], busKeys: ['unknown'] });
    const fromStop = focusPlan({ kind: 'route', routeId: '10UP', parent: { kind: 'stop', stopId: 'S1', only: null } }, ctx);
    expect(fromStop).toMatchObject({ routeIds: ['10UP'], pinStop: 'S1', busKeys: [] });
    const fromBus = focusPlan({ kind: 'route', routeId: '20UP', parent: { kind: 'live', key: 'bus1' } }, ctx);
    expect(fromBus).toMatchObject({ routeIds: ['20UP'], busKeys: ['bus1'] });
  });

  it('falls back to the chosen trip, else nothing (the zoom decides)', () => {
    const journey = [{ routeId: '20UP', fromPos: 1, toPos: 4 }];
    expect(focusPlan(null, { ...ctx, journey })).toMatchObject({ routeIds: ['20UP'], highlights: journey });
    const change = [journey[0], { routeId: '10UP', fromPos: 2, toPos: 7 }];
    expect(focusPlan(null, { ...ctx, journey: change })).toMatchObject({ routeIds: ['20UP', '10UP'], highlights: change });
    expect(focusPlan({ kind: 'about' }, ctx)).toBeNull();
  });
});

describe('what the map draws', () => {
  it('with nothing selected: stops and buses only when zoomed in', () => {
    expect(busVisible('10UP', 'b', DETAIL_ZOOM - 1, null)).toBe(false);
    expect(busVisible('10UP', 'b', DETAIL_ZOOM, null)).toBe(true);
    expect(allStopsVisible(DETAIL_ZOOM - 1, false)).toBe(false);
    expect(allStopsVisible(DETAIL_ZOOM, false)).toBe(true);
  });

  it("with a selection: only its routes' buses (and the selected bus), at any zoom, and not every stop", () => {
    const filter = busFilterOf(toMapFocus({ routeIds: ['10UP'], busKeys: ['x'], pinStop: null, highlights: [] }, {}, {}, 8, false));
    expect(busVisible('10UP', 'b', 10, filter)).toBe(true);
    expect(busVisible('20UP', 'b', 18, filter)).toBe(false);
    expect(busVisible(null, 'x', 10, filter)).toBe(true);
    expect(allStopsVisible(18, true)).toBe(false);
  });

  it('colours each route number once, in order, and draws loaded routes with the crowding of the hour', () => {
    const colors = colorsByNumber(['10', '10', '20']);
    expect(colors).toEqual({ 10: ROUTE_PALETTE[0], 20: ROUTE_PALETTE[1] });
    const detail: RouteDetail = {
      route: { id: '10UP', number: '10', direction: 'UP', description: '', canonical_trip: 't', shape: [], stops: [], trips_per_day: 9 },
      crowding: { 8: { occ: [0.2, 0.9], peak: 0.9, level: 'High', confidence: 'high', trips_day: 3 } },
    };
    const focus = toMapFocus({ routeIds: ['10UP', '20UP'], busKeys: [], pinStop: null, highlights: [] }, { '10UP': detail }, colors, 8, false);
    expect(focus.routes).toEqual([expect.objectContaining({ id: '10UP', color: ROUTE_PALETTE[0], occ: [0.2, 0.9], confidence: 'high' })]);
    expect(focus.busRoutes).toEqual(['10UP', '20UP']);
  });
});
