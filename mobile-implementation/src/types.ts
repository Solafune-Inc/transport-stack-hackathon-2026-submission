export type LevelName = 'Low' | 'Medium' | 'High' | 'Very High';
export type Confidence = 'high' | 'low' | 'none';
export type Direction = 'UP' | 'DOWN';
/** occupancy thresholds, e.g. [[0.5, 'Low'], …, [null, 'Very High']] */
export type Levels = [number | null, LevelName][];

/** assets/data/meta.json, exported by src/export_mobile_data.py */
export interface Meta {
  attribution: string;
  generated_at: string;
  sources: Record<string, string>;
  assumptions: {
    coverage: number;
    capacity: number;
    days: number;
    min_trips_day_high_conf: number;
    min_pax_month_high_conf: number;
    levels: Levels;
  };
  changes: string[];
}

export interface RouteStop {
  stop_id: string;
  dist_m: number;
}

/** One route variant, e.g. 623UP (route number 623, direction UP). */
export interface Route {
  id: string;
  number: string;
  /** null for routes without an UP/DOWN variant (e.g. circular services) */
  direction: Direction | null;
  description: string;
  canonical_trip: string;
  /** [lat, lon, cumulative distance in metres] */
  shape: [number, number, number][];
  stops: RouteStop[];
  trips_per_day: number;
}

export interface HourCrowding {
  /** occupancy (load / capacity) on the segment after each stop position; empty = no tickets */
  occ: number[];
  peak: number;
  level: LevelName;
  confidence: Confidence;
  trips_day: number;
}

/** GET /api/routes/{id} (and each entry of GET /api/routes?ids=). */
export interface RouteDetail {
  route: Route;
  crowding: Record<string, HourCrowding>;
}

/** GET /api/stops row: [id, name, lat, lon, route variants stopping there] */
export type StopRow = [string, string, number, number, number];

export interface StopsPayload {
  fields: string[];
  stops: StopRow[];
}

export interface NetStop {
  id: string;
  name: string;
  lat: number;
  lon: number;
  nRoutes: number;
}

/** A route variant through a stop's route number, from GET /api/stops/{id}. */
export interface StopRoute {
  id: string;
  number: string;
  direction: Direction | null;
  description: string;
  /** false = this variant of the route number does not stop here (e.g. it uses the stop across the road) */
  serves: boolean;
  pos: number | null;
  n_stops: number;
  /** expected occupancy of buses arriving here this hour (null: not served, first stop or no tickets) */
  occ: number | null;
  confidence: Confidence;
  /** next scheduled departures here, seconds since midnight (may be > 86400 = tomorrow) */
  next: number[];
}

export interface StopInfo {
  stop: { id: string; name: string; lat: number; lon: number; n_routes_all: number };
  t: number;
  /** estimated people per day boarding / alighting, one pair per hour (all routes) */
  busyness: [number, number][] | null;
  routes: StopRoute[];
}

/** One direct bus from GET /api/plan. */
/** One bus ride of a planned trip. */
export interface PlanLeg {
  routeId: string;
  trip: number;
  fromPos: number;
  toPos: number;
  fromStop: string;
  toStop: string;
  fromName: string;
  toName: string;
  depart: number;
  arrive: number;
  occ: number;
  level: LevelName;
  confidence: Confidence;
}

/** A trip option from GET /api/plan; the top-level fields describe the whole trip (crowding = worst ride). */
export interface PlanOptionRaw {
  routeId: string;
  trip: number;
  fromPos: number;
  toPos: number;
  fromStop: string;
  toStop: string;
  depart: number;
  arrive: number;
  occ: number;
  level: LevelName;
  confidence: Confidence;
  /** the rides, in order (with ?transfers=1; one ride for a direct bus) */
  legs?: PlanLeg[];
  /** changes of bus (0 = direct) */
  changes?: number;
  /** straight-line metres walked between the two stops of a change */
  walk_m?: number;
  /** walking time for that change, seconds */
  walk_s?: number;
}

export interface RouteSummary {
  number: string;
  direction: Direction | null;
  description: string;
}

export interface PlanResponse {
  /** the stops used at each end (the chosen stop + same-named stops nearby) */
  from: string[];
  to: string[];
  t: number;
  served_by: string[];
  routes: Record<string, RouteSummary>;
  options: PlanOptionRaw[];
}

export type MapMode = 'routes' | 'crowding';

/**
 * One live bus from GET /api/live: [key, route, lat, lon, dist_m, pos, kmh, ts, occ, conf,
 * prev_ts, prev_lat, prev_lon, prev_dist_m]. route = GTFS route_short_name (null if not in the
 * timetable); dist_m / pos = distance along the route and segment index (null when > 200 m off
 * its route); ts = GPS fix time (epoch s); occ = expected occupancy of that segment for the fix's
 * hour (null = no tickets); conf 1/0; prev_* = the previous GPS fix on the same route (or nulls).
 */
export type LiveRow = [
  string, string | null, number, number, number | null, number | null, number, number, number | null, 0 | 1 | null,
  number | null, number | null, number | null, number | null,
];

export interface LivePayload {
  /** server clock (epoch s) when this response was sent */
  now: number;
  /** last upstream error, if the feed below is stale */
  error: string | null;
  feed_time: number;
  fetched_at: number;
  fields: string[];
  stats: { vehicles: number; on_route: number; off_route: number; unknown_route: number; routes: number };
  vehicles: LiveRow[];
}

export interface Highlight {
  routeId: string;
  fromPos: number;
  toPos: number;
}

/** A route line drawn on the map, with the crowding of the current hour. */
export interface MapRoute {
  id: string;
  number: string;
  direction: Direction | null;
  color: string;
  shape: Route['shape'];
  stops: RouteStop[];
  occ: number[];
  confidence: Confidence;
}

/** What the map shows while a stop, a bus or a trip is selected. */
export interface MapFocus {
  routes: MapRoute[];
  /** only buses on these routes are drawn ... */
  busRoutes: string[];
  /** ... plus these buses (the selected one) */
  busKeys: string[];
  /** the tapped stop, always drawn */
  pinStop: string | null;
  /** the rides of a chosen trip */
  highlights: Highlight[];
  /** zoom the map to the highlights */
  fit: boolean;
}

/** Commands sent from React Native into the map page. */
export interface MapCommand {
  mode?: MapMode;
  /** every stop: [id, lat, lon] (sent once) */
  stops?: [string, number, number][];
  /** null = nothing selected: stops and buses only when zoomed in */
  focus?: MapFocus | null;
  /** live key of the bus whose sheet is open */
  selectedBus?: string | null;
  /** a new GET /api/live response (only the fields the map needs) */
  liveData?: { now: number; rows: LiveRow[] };
  /** route lines asked for with `needShapes` */
  shapes?: Record<string, Route['shape']>;
}

/** Messages posted from the map page back to React Native. */
export type MapMessage =
  | { type: 'ready' }
  /** zoomed in far enough that stops and buses show without a selection */
  | { type: 'zoom'; detail: boolean }
  | { type: 'tap'; kind: 'live'; key: string }
  | { type: 'tap'; kind: 'stop'; stopId: string }
  /** route lines of buses on screen, so they move along their road between GPS reports */
  | { type: 'needShapes'; ids: string[] };

export interface MapState {
  mode: MapMode;
}

/** Data injected into the map page as window.__BOOT__. */
export interface MapBoot {
  levels: Levels;
  state: MapState;
}
