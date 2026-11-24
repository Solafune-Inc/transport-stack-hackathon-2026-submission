import { useState, type ReactNode } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { LEVEL_COLORS, NO_DATA_COLOR, confidenceText, describeLoad, levelOf } from '../logic/crowding';
import { R, fmtAge } from '../logic/live';
import { fmtPeople, routeParts, terminalOf } from '../logic/lookup';
import { fmtTime, hourRange } from '../logic/time';
import { normalizeLiveUrl } from '../live/config';
import { useNow, type LiveStatus } from '../live/useLiveFeed';
import type { Confidence, Direction, LevelName, LiveRow, Meta, NetStop, RouteDetail, StopInfo, StopRoute } from '../types';
import { LevelBadge, RouteChip } from './Badges';
import { HourChart } from './HourChart';
import { Sheet } from './Sheet';
import { C, ui } from './theme';

function Labeled({ label, children }: { label: string; children: ReactNode }) {
  return (
    <View style={styles.labeled}>
      <Text style={styles.label}>{label}</Text>
      {children}
    </View>
  );
}

const levelFor = (occ: number | null, confidence: Confidence, meta: Meta): LevelName | null =>
  occ === null || confidence === 'none' ? null : levelOf(occ, meta.assumptions.levels);

/** "UP → Nangal Dewat" */
function towards(direction: Direction | null, description: string): string {
  const end = terminalOf(description) ?? description;
  return direction ? `${direction} → ${end}` : `→ ${end}`;
}

function StopRouteRow({ route, color, meta, selected, onPress, onRoute }: {
  route: StopRoute;
  color: string;
  meta: Meta;
  selected: boolean;
  onPress(): void;
  onRoute(): void;
}) {
  const level = levelFor(route.occ, route.confidence, meta);
  const first = route.pos === 0;
  const last = route.pos === route.n_stops - 1;
  let status: ReactNode;
  if (!route.serves) status = <Text style={styles.small}>Not at this stop</Text>;
  else if (first) status = <Text style={styles.small}>Starts here</Text>;
  else if (last) status = <Text style={styles.small}>Ends here</Text>;
  else status = <LevelBadge level={level} />;
  let detail: string;
  if (!route.serves) detail = 'Other direction: it stops nearby (e.g. across the road), not here';
  else if (last) detail = 'Last stop of this route';
  else {
    const load = route.occ !== null && route.confidence !== 'none' ? `${describeLoad(route.occ, meta.assumptions.capacity)} · ` : '';
    detail = `${load}next: ${route.next.length ? route.next.map(fmtTime).join(', ') : 'none today'}`;
  }
  return (
    <Pressable
      onPress={onPress}
      style={[styles.arrival, selected && styles.arrivalOn, !route.serves && styles.dim]}
      accessibilityRole="button"
      accessibilityState={{ selected }}
      accessibilityLabel={`Route ${route.number} ${route.direction ?? ''}`}
    >
      <View style={ui.row}>
        <RouteChip number={route.number} color={color} />
        <Text style={styles.towards} numberOfLines={1}>
          {towards(route.direction, route.description)}
        </Text>
        {status}
      </View>
      <Text style={styles.small}>{detail}</Text>
      {selected ? (
        <Pressable onPress={onRoute} accessibilityRole="button">
          <Text style={ui.link}>Route {route.number} crowding by hour ›</Text>
        </Pressable>
      ) : null}
    </Pressable>
  );
}

/** A bus stop: how busy it is, and every route number through it (both directions). */
export function StopDetail({ name, info, error, meta, hour, colors, only, onOnly, onRoute, onClose }: {
  /** name from the stop list, shown while the details load */
  name: string | null;
  info: StopInfo | null;
  error: string | null;
  meta: Meta;
  hour: number;
  /** route number -> colour on the map */
  colors: Record<string, string>;
  /** the route shown on its own, or null for all */
  only: string | null;
  onOnly(routeId: string | null): void;
  onRoute(routeId: string): void;
  onClose(): void;
}) {
  if (!info) {
    return (
      <Sheet title={name ?? 'Bus stop'} subtitle="Bus stop" onClose={onClose}>
        <Text style={[ui.body, error && styles.error]}>{error ? `Couldn't load this stop: ${error}` : 'Loading routes…'}</Text>
      </Sheet>
    );
  }
  const numbers = new Set(info.routes.filter((r) => r.serves).map((r) => r.number));
  const busy = info.busyness;
  const [boardings, alightings] = busy?.[hour] ?? [0, 0];
  const series = busy ? busy.map(([b, a]) => b + a) : [];
  const shown = only ? info.routes.find((r) => r.id === only) : undefined;
  return (
    <Sheet
      title={info.stop.name}
      subtitle={`Bus stop · ${numbers.size} route${numbers.size === 1 ? '' : 's'} stop here`}
      onClose={onClose}
    >
      {busy ? (
        <>
          <Text style={ui.section}>How busy is this stop? ({hourRange(hour)})</Text>
          <Text style={ui.body}>
            ~{fmtPeople(boardings)} boarding · ~{fmtPeople(alightings)} alighting this hour, all routes (estimated)
          </Text>
          <HourChart values={series} colors={series.map(() => C.blue)} current={hour} />
        </>
      ) : null}
      <View style={[ui.row, styles.routesHeader]}>
        <Text style={[ui.section, styles.grow]}>Routes through this stop</Text>
        {only ? (
          <Pressable onPress={() => onOnly(null)} hitSlop={8} accessibilityRole="button">
            <Text style={styles.headerLink}>Show all routes</Text>
          </Pressable>
        ) : null}
      </View>
      <Text style={styles.small}>
        {shown
          ? `Only route ${shown.number} ${shown.direction ?? ''} and its buses are on the map.`
          : 'All their lines (both directions) and only their buses are on the map, at any zoom. Tap a route to show it alone.'}
      </Text>
      {info.routes.map((r) => (
        <StopRouteRow
          key={r.id}
          route={r}
          color={colors[r.number] ?? NO_DATA_COLOR}
          meta={meta}
          selected={r.id === only}
          onPress={() => onOnly(r.id === only ? null : r.id)}
          onRoute={() => onRoute(r.id)}
        />
      ))}
      <Text style={ui.note}>
        Crowding is the October 2026 e-ticketing average for buses arriving here this hour on today&apos;s kind of day
        (weekday, Saturday or Sunday/holiday); next departures are from the GTFS timetable. Boardings and alightings are scaled up from the ~
        {Math.round(meta.assumptions.coverage * 1000) / 10}% mobile-ticket share; alightings count in the hour the
        ticket was bought.
      </Text>
    </Sheet>
  );
}

/** Hourly crowding of one route variant. */
export function RouteSheet({ detail, color, hour, meta, siblings, onSwitch, onClose }: {
  detail: RouteDetail | null;
  color: string;
  hour: number;
  meta: Meta;
  /** other variants of the same route number (e.g. the other direction) */
  siblings: { id: string; direction: Direction | null }[];
  onSwitch(routeId: string): void;
  onClose(): void;
}) {
  if (!detail) {
    return (
      <Sheet title="Route" accent={color} onClose={onClose}>
        <Text style={ui.body}>Loading the route…</Text>
      </Sheet>
    );
  }
  const { route, crowding } = detail;
  const levels = meta.assumptions.levels;
  const values = Array.from({ length: 24 }, (_, h) => crowding[String(h)]?.peak ?? 0);
  const colors = values.map((v, h) =>
    crowding[String(h)]?.confidence === 'none' ? NO_DATA_COLOR : LEVEL_COLORS[levelOf(v, levels)],
  );
  const now = crowding[String(hour)];
  const busiest = values.indexOf(Math.max(...values));
  const km = (route.shape[route.shape.length - 1][2] / 1000).toFixed(1);
  return (
    <Sheet
      title={`Route ${route.number}${route.direction ? ` ${route.direction}` : ''}`}
      subtitle={route.description}
      accent={color}
      onClose={onClose}
    >
      <Labeled label={`Now (${hourRange(hour)}), busiest stretch`}>
        <LevelBadge level={levelFor(now?.peak ?? 0, now?.confidence ?? 'none', meta)} />
      </Labeled>
      <Text style={ui.body}>
        {now && now.confidence !== 'none' ? describeLoad(now.peak, meta.assumptions.capacity) : 'No e-tickets recorded this hour'}
      </Text>
      <Text style={ui.section}>Expected load on the busiest stretch, by hour</Text>
      <HourChart values={values} colors={colors} current={hour} refLine={1} />
      <Text style={ui.note}>
        Dashed line = bus capacity ({meta.assumptions.capacity}). Busiest: {String(busiest).padStart(2, '0')}:00.{' '}
        {route.stops.length} stops · {km} km · {route.trips_per_day} scheduled trips/day.
      </Text>
      <Text style={ui.note}>{confidenceText(now?.confidence ?? 'none')}</Text>
      {siblings.map((s) => (
        <Pressable key={s.id} onPress={() => onSwitch(s.id)} accessibilityRole="button">
          <Text style={ui.link}>Show {s.direction ? `the ${s.direction} direction` : s.id} ›</Text>
        </Pressable>
      ))}
    </Sheet>
  );
}

const CONF: Record<string, Confidence> = { '1': 'high', '0': 'low' };

/** A bus from the live GPS feed: its route, speed, fix age and expected crowding where it is. */
export function LiveBusDetail({ row, detail, color, stops, offset, meta, onRoute, onClose }: {
  row: LiveRow;
  /** its route, once loaded (null: loading or not in the timetable) */
  detail: RouteDetail | null;
  color: string;
  stops: Map<string, NetStop>;
  /** server clock minus phone clock (s) */
  offset: number;
  meta: Meta;
  onRoute(routeId: string): void;
  onClose(): void;
}) {
  const phoneNow = useNow(true);
  const routeId = row[R.route];
  const pos = row[R.pos];
  const occ = row[R.occ];
  const confidence = occ === null ? 'none' : CONF[String(row[R.conf])] ?? 'none';
  const [number] = routeId ? routeParts(routeId) : ['?'];
  const end = detail ? terminalOf(detail.route.description) : null;
  const title = routeId ? `${number}${end ? ` → ${end}` : ''}` : 'Bus on a route not in the timetable';
  const next = detail && pos !== null ? detail.route.stops[pos + 1]?.stop_id : undefined;
  return (
    <Sheet
      title={title}
      subtitle={`Live GPS · ${row[R.kmh]} km/h · reported ${fmtAge(phoneNow + offset - row[R.ts])} ago`}
      accent={routeId ? color : '#455a64'}
      onClose={onClose}
    >
      <Labeled label="Expected crowding on this stretch now">
        <LevelBadge level={levelFor(occ, confidence, meta)} />
      </Labeled>
      <Text style={ui.body}>
        {occ !== null
          ? describeLoad(occ, meta.assumptions.capacity)
          : pos === null && routeId
            ? 'More than 200 m from its usual route line right now, so no estimate'
            : 'No e-tickets recorded for this route at this hour'}
      </Text>
      {occ !== null ? <Text style={ui.note}>{confidenceText(confidence)}</Text> : null}
      {next ? (
        <Labeled label="Next stop">
          <Text style={ui.body}>{stops.get(next)?.name ?? next}</Text>
        </Labeled>
      ) : routeId && !detail ? (
        <Text style={ui.note}>Loading the route…</Text>
      ) : null}
      <Text style={ui.note}>
        Only this bus&apos;s route and the buses on it are on the map. Position from the Delhi GTFS-RT feed (vehicle id
        hidden); buses report about every 25–30 s and glide to their latest report in between. Crowding is the
        October 2026 e-ticketing average for this route, hour and stretch on today&apos;s kind of day (weekday, Saturday
        or Sunday/holiday): an estimate, not a live passenger count.
      </Text>
      {detail ? (
        <Pressable onPress={() => onRoute(detail.route.id)} accessibilityRole="button">
          <Text style={ui.link}>Route {number} crowding by hour ›</Text>
        </Pressable>
      ) : null}
    </Sheet>
  );
}

/** Live feed status, where the app looks for the server, and how to start it. */
export function LiveInfoDetail({ url, status, onUrl, onClose }: {
  url: string;
  status: LiveStatus;
  onUrl(url: string): void;
  onClose(): void;
}) {
  const [draft, setDraft] = useState(url);
  const payload = status.state === 'ok' || status.state === 'error' ? status.payload : null;
  return (
    <Sheet title="Live bus positions" subtitle="Delhi GTFS-RT feed via our server" onClose={onClose}>
      {status.state === 'error' ? (
        <Text style={[ui.body, styles.error]}>Can&apos;t reach {url}: {status.message}</Text>
      ) : null}
      {payload ? (
        <Text style={ui.body}>
          {payload.stats.vehicles.toLocaleString()} buses on {payload.stats.routes.toLocaleString()} routes;{' '}
          {payload.stats.on_route.toLocaleString()} are on their route line and get a crowding estimate.
          {payload.error ? ` Feed update failed (${payload.error}); showing the last good one.` : ''}
        </Text>
      ) : null}
      <Text style={ui.section}>Server address</Text>
      <View style={styles.urlRow}>
        <TextInput
          value={draft}
          onChangeText={setDraft}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          placeholder="http://192.168.1.5:8787"
          placeholderTextColor={C.sub}
          style={styles.url}
          onSubmitEditing={() => onUrl(normalizeLiveUrl(draft))}
        />
        <Pressable onPress={() => onUrl(normalizeLiveUrl(draft))} style={styles.connect} accessibilityRole="button">
          <Text style={styles.connectText}>Connect</Text>
        </Pressable>
      </View>
      <Text style={ui.note}>
        Stops, routes, crowding, the trip planner and live buses all come from this server; the Transport Stack API
        key stays on it, never in the app. Start it on the Mac from the repo root with &quot;python
        src/api/main.py&quot;, keep the phone on the same Wi-Fi, and use the Mac&apos;s Wi-Fi address (port 8787).
      </Text>
    </Sheet>
  );
}

export function AboutDetail({ meta, onClose }: { meta: Meta; onClose(): void }) {
  const a = meta.assumptions;
  return (
    <Sheet title="About this prototype" subtitle="Crowdedness-aware journey planner · Problem 2" onClose={onClose}>
      <Text style={ui.section}>The map</Text>
      <Text style={ui.body}>
        Every Delhi bus stop and every live bus. Zoom in to see the stops and buses around you; tap a stop to see all
        its routes in both directions and only their buses, or tap a bus to see its route. Close the sheet to go back
        to the plain map.
      </Text>
      <Text style={ui.section}>How crowding is estimated</Text>
      <Text style={ui.body}>
        A month of Delhi mobile e-tickets (October 2026) records where each passenger boarded and got off. Adding
        boardings and subtracting alightings along each route gives the load on every road segment, scaled to one bus
        using the ~{a.coverage * 100}% mobile-ticket share and the scheduled buses per hour. Capacity is taken as{' '}
        {a.capacity} people. Above 1.5× capacity the app says &quot;Over capacity&quot; instead of a count: one
        mobile-ticket share for all routes over-scales some of them until per-route data (ETM) arrives. Weekdays, Saturdays and Sundays/public holidays differ a lot (a Sunday morning carries about a
        third of a weekday&apos;s riders), so each hour is scaled to the kind of day the bus runs on, from October&apos;s
        tickets on that kind of day. Estimates with fewer than {a.min_pax_month_high_conf} passengers in the month or
        fewer than {a.min_trips_day_high_conf} scheduled buses in the hour are marked low confidence.
      </Text>
      <Text style={ui.section}>Trip planner</Text>
      <Text style={ui.body}>
        Buses between any two stops (same-named stops across the road count too) in the next 2 hours, from the
        GTFS timetable, ranked by time and expected crowding: direct, or with one change of bus at the same stop or
        a short walk away (up to 250 m, at least 2 min to change, at most 30 min to wait).
      </Text>
      <Text style={ui.section}>Credits</Text>
      <Text style={ui.body}>
        {meta.attribution}
        {'\n'}Live positions: Delhi Buses GTFS-RT feed, Delhi Transport Stack.
        {'\n'}Basemap: OpenFreeMap, © OpenMapTiles, map data © OpenStreetMap contributors.
        {'\n'}Built with Expo / React Native, react-native-webview, Leaflet, MapLibre GL JS, MapLibre GL Leaflet and
        Leaflet.PolylineOffset; server with FastAPI, uvicorn, pandas, NumPy and gtfs-realtime-bindings.
      </Text>
    </Sheet>
  );
}

const styles = StyleSheet.create({
  labeled: { marginTop: 10, gap: 4 },
  label: { fontSize: 12, color: C.sub, fontWeight: '600' },
  routesHeader: { marginTop: 4 },
  grow: { flex: 1 },
  headerLink: { fontSize: 13, color: C.blue, fontWeight: '700', marginTop: 8 },
  arrival: {
    paddingVertical: 7,
    paddingHorizontal: 4,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  arrivalOn: { backgroundColor: C.blueSoft, borderRadius: 8 },
  dim: { opacity: 0.6 },
  towards: { flex: 1, marginHorizontal: 8, fontSize: 13, color: C.text },
  small: { fontSize: 12, color: C.sub, marginTop: 3 },
  error: { color: '#d93025', marginBottom: 6 },
  urlRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  url: {
    flex: 1,
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 8,
    fontSize: 14,
    color: C.text,
  },
  connect: { backgroundColor: C.blue, borderRadius: 10, paddingHorizontal: 14, paddingVertical: 9 },
  connectText: { color: '#fff', fontWeight: '700', fontSize: 14 },
});
