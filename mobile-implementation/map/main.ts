/**
 * Leaflet map page that runs inside the app's WebView (bundled by scripts/build-map.mjs).
 * Zoomed out with nothing selected it is a clean basemap; from DETAIL_ZOOM it shows the stops and
 * live buses in view. A selection (MapFocus: a stop, a bus or a chosen trip) draws its routes, the
 * stops along them and only their buses, at any zoom. Taps on stops and buses are posted to React
 * Native; tapping empty map does nothing (a selection is cleared from its sheet).
 */
import * as L from 'leaflet';
import 'leaflet-polylineoffset';
import { maplibreGL } from '@maplibre/maplibre-gl-leaflet';
import type { FilterSpecification } from 'maplibre-gl';
import { LEVEL_COLORS, NO_DATA_COLOR, levelOf } from '../src/logic/crowding';
import { DETAIL_ZOOM, ROUTE_STOPS_ZOOM, allStopsVisible, busFilterOf, type BusFilter } from '../src/logic/focus';
import { pointAtDistance, sliceShape } from '../src/logic/shape';
import type { MapBoot, MapCommand, MapFocus, MapMessage, MapRoute, Route } from '../src/types';
import { LiveLayer } from './live';
import { STOP_COLOR, StopIcon, pinIcon, stopSize, type StopIconOptions } from './stopIcon';

declare module 'leaflet' {
  interface PolylineOptions {
    offset?: number;
  }
}

declare global {
  interface Window {
    __BOOT__: MapBoot;
    __app: { cmd(c: MapCommand): void; probe(): unknown };
    ReactNativeWebView?: { postMessage(msg: string): void };
  }
}

const { levels } = window.__BOOT__;
const state = { ...window.__BOOT__.state };
/** central Delhi, zoomed out: the clean basemap until the user zooms in or picks something */
const START: { center: L.LatLngTuple; zoom: number } = { center: [28.62, 77.21], zoom: 12 };

function post(msg: MapMessage) {
  const s = JSON.stringify(msg);
  if (window.ReactNativeWebView) window.ReactNativeWebView.postMessage(s);
  else window.dispatchEvent(new CustomEvent('mapmsg', { detail: msg }));
}

// OpenFreeMap: free vector basemaps with no API key, registration or usage limits (their credit is
// added to the attribution control automatically). Google-like "liberty" for routes, muted "positron"
// so crowding colours stand out. The volunteer raster tiles are only a fallback for devices without
// WebGL (tile.openstreetmap.org blocks WebView requests without a referer; CARTO now needs a key).
const BASEMAP_STYLE: Record<'routes' | 'crowding', string> = {
  routes: 'https://tiles.openfreemap.org/styles/liberty',
  crowding: 'https://tiles.openfreemap.org/styles/positron',
};
const FALLBACK_TILES = 'https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png';
const FALLBACK_ATTRIBUTION = '© OpenStreetMap contributors · tiles: Humanitarian OSM Team, OSM France';

const map = L.map('map', { zoomControl: false, minZoom: 10, maxZoom: 18 }).setView(START.center, START.zoom);
map.attributionControl.setPrefix('Leaflet · Bus data: Delhi Transport Stack');
// route lines, the ride of a chosen trip, then stops + live buses, then the tapped stop / bus
for (const [name, z] of [['routes', 410], ['highlight', 415], ['live', 425], ['pin', 430]] as const) {
  map.createPane(name).style.zIndex = String(z);
}
// added after the view is set so a WebGL failure surfaces here, synchronously
let basemap: ReturnType<typeof maplibreGL> | null = null;
let basemapStyle = BASEMAP_STYLE[state.mode];
try {
  basemap = maplibreGL({ style: basemapStyle }).addTo(map);
} catch {
  L.tileLayer(FALLBACK_TILES, { subdomains: 'abc', maxZoom: 19, attribution: FALLBACK_ATTRIBUTION }).addTo(map);
}

/**
 * The basemap's own OpenStreetMap bus-stop icons look like our stop signs but can't be tapped (and
 * don't match the GTFS stops), so the "liberty" style keeps only its rail and airport icons. Applied
 * again whenever the style (re)loads, e.g. when switching tabs.
 */
const NO_BUS_POI: FilterSpecification = ['match', ['get', 'class'], ['airport', 'rail'], true, false];
function hideBasemapBusStops() {
  const m = basemap?.getMaplibreMap();
  if (!m?.getLayer('poi_transit')) return;
  if (JSON.stringify(m.getFilter('poi_transit')) !== JSON.stringify(NO_BUS_POI)) m.setFilter('poi_transit', NO_BUS_POI);
}
basemap?.getMaplibreMap().on('styledata', hideBasemapBusStops);

const routeRenderer = L.canvas({ pane: 'routes', padding: 0.3 });
// Stops and live bus dots share one canvas: Leaflet only hit-tests the topmost canvas, so a
// separate bus canvas would swallow taps meant for the stops underneath.
const tapRenderer = L.canvas({ pane: 'live', padding: 0.3, tolerance: 6 });

let focus: MapFocus | null = null;
let busFilter: BusFilter | null = null;
let selectedBus: string | null = null;
const routeColor = new Map<string, string>();
const routeShape = new Map<string, Route['shape']>();
/** route lines of buses that were on screen, so every bus moves along its road between reports */
const shapeCache = new Map<string, Route['shape']>();
/** route id -> when its line was asked for (asked again if it has not arrived in SHAPE_RETRY_MS) */
const shapeAsked = new Map<string, number>();
const SHAPE_RETRY_MS = 20_000;
const SHAPES_PER_REQUEST = 300;
/** stops along the selected routes -> worst occupancy of buses arriving there (null: none known) */
let routeStops = new Map<string, number | null>();

// --- Stops -----------------------------------------------------------------------------------
let stopIds: string[] = [];
const stopPos = new Map<string, L.LatLngTuple>();
const stopLayer = L.layerGroup().addTo(map);
const stopMarkers = new Map<string, { marker: L.CircleMarker; look: string }>();

/** Sign colour: blue, or on the Crowding tab how full buses arrive (stops of the selected routes). */
function stopColors(id: string): { fill: string; glyph: string } {
  const occ = routeStops.get(id);
  if (!focus || state.mode !== 'crowding' || occ === undefined || occ === null) return { fill: STOP_COLOR, glyph: '#fff' };
  const fill = LEVEL_COLORS[levelOf(occ, levels)];
  return { fill, glyph: fill === LEVEL_COLORS.Medium ? '#202124' : '#fff' };
}

function stopStyle(id: string): StopIconOptions {
  const { fill, glyph } = stopColors(id);
  // tapped like a circle of the sign's half size (+ the renderer's tolerance)
  return { radius: stopSize(map.getZoom()) / 2, stroke: false, fillColor: fill, glyph };
}

/** Draw the stops that should show at this zoom / selection, only those in (or near) the view. */
function refreshStops() {
  const zoom = map.getZoom();
  const view = map.getBounds().pad(0.25);
  const wanted = new Set<string>();
  if (focus) {
    if (zoom >= ROUTE_STOPS_ZOOM) {
      for (const id of routeStops.keys()) {
        const p = stopPos.get(id);
        if (p && view.contains(p)) wanted.add(id);
      }
    }
  } else if (allStopsVisible(zoom, false)) {
    for (const id of stopIds) if (view.contains(stopPos.get(id)!)) wanted.add(id);
  }
  if (focus?.pinStop) wanted.delete(focus.pinStop); // drawn by the pin, above the buses
  for (const [id, s] of stopMarkers) {
    if (wanted.has(id)) continue;
    stopLayer.removeLayer(s.marker);
    stopMarkers.delete(id);
  }
  for (const id of wanted) {
    const style = stopStyle(id);
    const look = `${style.radius}|${style.fillColor}`;
    const s = stopMarkers.get(id);
    if (!s) {
      const marker = new StopIcon(stopPos.get(id)!, { ...style, renderer: tapRenderer, bubblingMouseEvents: false });
      marker.on('click', () => post({ type: 'tap', kind: 'stop', stopId: id }));
      marker.addTo(stopLayer);
      marker.bringToBack(); // under the buses
      stopMarkers.set(id, { marker, look });
    } else if (s.look !== look) {
      s.marker.setStyle(style);
      s.marker.setRadius(style.radius!);
      s.look = look;
    }
  }
}

// --- The tapped stop -------------------------------------------------------------------------
let pin: L.Marker | null = null;
function drawPin() {
  if (pin) map.removeLayer(pin);
  pin = null;
  const id = focus?.pinStop;
  const p = id ? stopPos.get(id) : undefined;
  if (!id || !p) return;
  const { fill, glyph } = stopColors(id);
  // not interactive: a tap on it reaches the bus dots underneath
  pin = L.marker(p, { pane: 'pin', icon: pinIcon(fill, glyph), interactive: false, keyboard: false }).addTo(map);
}

// --- Routes of the selection -----------------------------------------------------------------
const routeLayer = L.layerGroup().addTo(map);
/** UP and DOWN are drawn side by side where they share a street */
const offsetOf = (r: MapRoute) => (r.direction === 'UP' ? -3 : r.direction === 'DOWN' ? 3 : 0);
const latlngs = (r: MapRoute) => r.shape.map((p) => [p[0], p[1]] as L.LatLngTuple);

function drawRoutes() {
  routeLayer.clearLayers();
  if (!focus) return;
  const base = { renderer: routeRenderer, interactive: false };
  for (const r of focus.routes) {
    L.polyline(latlngs(r), { ...base, color: '#fff', weight: 8, offset: offsetOf(r) }).addTo(routeLayer);
  }
  for (const r of focus.routes) {
    if (state.mode === 'routes') {
      L.polyline(latlngs(r), { ...base, color: r.color, weight: 4.5, opacity: 0.9, offset: offsetOf(r) }).addTo(routeLayer);
      continue;
    }
    // one multi-line per crowding colour keeps busy stops with hundreds of routes cheap to draw
    const byColor = new Map<string, L.LatLngTuple[][]>();
    for (let k = 0; k < r.stops.length - 1; k++) {
      const color =
        r.confidence === 'none' || !r.occ.length ? NO_DATA_COLOR : LEVEL_COLORS[levelOf(r.occ[k] ?? 0, levels)];
      const part = sliceShape(r.shape, r.stops[k].dist_m, r.stops[k + 1].dist_m);
      const list = byColor.get(color);
      if (list) list.push(part);
      else byColor.set(color, [part]);
    }
    for (const [color, parts] of byColor) {
      L.polyline(parts, { ...base, color, weight: 5.5, opacity: 0.95, offset: offsetOf(r) }).addTo(routeLayer);
    }
  }
}

// --- The rides of a chosen trip (one per bus) ------------------------------------------------
const hlLayer = L.layerGroup().addTo(map);
let fitted: string | null = null;
function drawHighlight() {
  hlLayer.clearLayers();
  const hs = focus?.highlights ?? [];
  if (!hs.length) fitted = null;
  const bounds: L.LatLngExpression[] = [];
  for (const h of hs) {
    const r = focus?.routes.find((x) => x.id === h.routeId);
    if (!r) return; // wait until every ride's route has loaded
    const ll = sliceShape(r.shape, r.stops[h.fromPos].dist_m, r.stops[h.toPos].dist_m);
    L.polyline(ll, { pane: 'highlight', color: '#fff', weight: 12, interactive: false }).addTo(hlLayer);
    L.polyline(ll, { pane: 'highlight', color: r.color, weight: 7, interactive: false }).addTo(hlLayer);
    for (const pos of [h.fromPos, h.toPos]) {
      const stop = r.stops[pos];
      L.circleMarker(stopPos.get(stop.stop_id) ?? pointAtDistance(r.shape, stop.dist_m), {
        pane: 'pin', radius: 7, color: r.color, weight: 3, fillColor: '#fff', fillOpacity: 1, interactive: false,
      }).addTo(hlLayer);
    }
    bounds.push(...ll);
  }
  const key = hs.map((h) => `${h.routeId}|${h.fromPos}|${h.toPos}`).join(',');
  if (hs.length && focus?.fit && fitted !== key) {
    fitted = key;
    map.fitBounds(L.latLngBounds(bounds), { paddingTopLeft: [24, 170], paddingBottomRight: [24, 40], maxZoom: 15 });
  }
}

// --- Live GPS buses --------------------------------------------------------------------------
const live = new LiveLayer({
  map,
  renderer: tapRenderer,
  levels,
  post,
  mode: () => state.mode,
  selected: () => selectedBus,
  filter: () => busFilter,
  colorOf: (route) => routeColor.get(route) ?? null,
  shape: (id) => routeShape.get(id) ?? shapeCache.get(id) ?? null,
  needShapes(ids) {
    const now = Date.now();
    const ask = ids.filter((id) => now - (shapeAsked.get(id) ?? -Infinity) > SHAPE_RETRY_MS).slice(0, SHAPES_PER_REQUEST);
    if (!ask.length) return;
    for (const id of ask) shapeAsked.set(id, now);
    post({ type: 'needShapes', ids: ask });
  },
});

/**
 * Pan a just-tapped stop or bus into the upper part of the map: the sheet that opens covers up to
 * the lower 60%.
 */
function reveal(ll: L.LatLngTuple | null) {
  if (!ll) return;
  const size = map.getSize();
  const p = map.latLngToContainerPoint(ll);
  const dx = p.x < 40 ? p.x - 40 : p.x > size.x - 40 ? p.x - (size.x - 40) : 0;
  const dy = p.y > size.y * 0.38 || p.y < 120 ? p.y - size.y * 0.3 : 0;
  if (dx || dy) map.panBy([dx, dy]);
}

// --- Selection, mode, zoom -------------------------------------------------------------------
function applyFocus(f: MapFocus | null) {
  const newPin = f?.pinStop && f.pinStop !== focus?.pinStop ? f.pinStop : null;
  focus = f;
  busFilter = busFilterOf(f);
  routeColor.clear();
  routeShape.clear();
  routeStops = new Map();
  for (const r of f?.routes ?? []) {
    routeColor.set(r.id, r.color);
    routeShape.set(r.id, r.shape);
    r.stops.forEach((s, k) => {
      const occ = k > 0 && r.occ.length && r.confidence !== 'none' ? r.occ[k - 1] : null;
      const was = routeStops.get(s.stop_id);
      routeStops.set(s.stop_id, occ === null ? (was ?? null) : Math.max(was ?? 0, occ));
    });
  }
  drawRoutes();
  drawHighlight();
  drawPin();
  refreshStops();
  live.restyle();
  if (newPin) reveal(stopPos.get(newPin) ?? null);
}

function applyMode() {
  if (basemap && basemapStyle !== BASEMAP_STYLE[state.mode]) {
    basemapStyle = BASEMAP_STYLE[state.mode];
    basemap.getMaplibreMap().setStyle(basemapStyle);
  }
  drawRoutes();
  drawPin();
  refreshStops();
  live.restyle();
}

let lastDetail: boolean | null = null;
function postZoom() {
  const detail = map.getZoom() >= DETAIL_ZOOM;
  if (detail === lastDetail) return;
  lastDetail = detail;
  post({ type: 'zoom', detail });
}

map.on('moveend zoomend', () => {
  refreshStops();
  live.refilter();
  postZoom();
});

window.__app = {
  cmd(c: MapCommand) {
    if (c.stops) {
      stopIds = c.stops.map((s) => s[0]);
      stopPos.clear();
      for (const [id, lat, lon] of c.stops) stopPos.set(id, [lat, lon]);
      drawPin();
      drawHighlight();
      refreshStops();
    }
    if (c.mode !== undefined && c.mode !== state.mode) {
      state.mode = c.mode;
      applyMode();
    }
    if (c.focus !== undefined) applyFocus(c.focus);
    if (c.selectedBus !== undefined) {
      if (c.selectedBus && c.selectedBus !== selectedBus) reveal(live.positionOf(c.selectedBus));
      selectedBus = c.selectedBus;
      live.restyle();
    }
    if (c.liveData) live.update(c.liveData.now, c.liveData.rows);
    if (c.shapes) {
      for (const [id, shape] of Object.entries(c.shapes)) if (shape.length > 1) shapeCache.set(id, shape);
      live.refilter();
    }
  },
  /** what is drawn now (for the dev preview and end-to-end checks; read-only) */
  probe() {
    const point = (ll: L.LatLngExpression) => {
      const p = map.latLngToContainerPoint(ll);
      return { x: Math.round(p.x), y: Math.round(p.y) };
    };
    return {
      zoom: map.getZoom(),
      mode: state.mode,
      stops: [...stopMarkers.keys()].map((id) => ({ id, ...point(stopPos.get(id)!) })),
      pinStop: focus?.pinStop ?? null,
      routes: focus?.routes.map((r) => r.id) ?? [],
      busRoutes: focus?.busRoutes ?? null,
      highlight: hlLayer.getLayers().length > 0,
      shapes: shapeCache.size,
      ...live.probe(),
    };
  },
};

function frame(now: number) {
  live.draw(now);
  requestAnimationFrame(frame);
}

requestAnimationFrame(frame);
post({ type: 'ready' });
postZoom();
