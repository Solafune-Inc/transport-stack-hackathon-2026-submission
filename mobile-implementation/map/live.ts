/**
 * Live GPS buses on the map page. Every bus glides toward its newest GPS report at its own
 * reporting pace (src/logic/live.ts), along the route line when the page knows it. Only buses that
 * pass the selection / zoom filter (src/logic/focus.ts) and are in view are drawn: as labelled
 * chips when there are few on screen, as canvas dots when there are many.
 */
import * as L from 'leaflet';
import { LEVEL_COLORS, NO_DATA_COLOR, levelOf } from '../src/logic/crowding';
import { CHIP_LIMIT, CITY_FILL, busVisible, type BusFilter } from '../src/logic/focus';
import { R, isStale, mergeTracks, trackPosition, type Fix, type Track } from '../src/logic/live';
import { routeParts } from '../src/logic/lookup';
import type { Levels, LiveRow, MapMessage, MapMode, Route } from '../src/types';

const CHIP_EVERY_MS = 50;
const DOT_EVERY_MS = 150;

export interface LiveContext {
  map: L.Map;
  /** canvas for the dots (shared with the stops so both stay tappable) */
  renderer: L.Canvas;
  levels: Levels;
  post(msg: MapMessage): void;
  mode(): MapMode;
  /** key of the selected bus */
  selected(): string | null;
  /** null = nothing selected (every bus, zoomed in only) */
  filter(): BusFilter | null;
  /** colour of a selected route */
  colorOf(route: string): string | null;
  /** route line known to the page (selected routes, or fetched for buses on screen) */
  shape(id: string): Route['shape'] | null;
  /** ask for the route lines of buses on screen that the page does not have yet */
  needShapes(ids: string[]): void;
}

interface Drawn {
  style: string;
  dot?: L.CircleMarker;
  chip?: L.Marker;
}

export class LiveLayer {
  private tracks = new Map<string, Track>();
  private drawn = new Map<string, Drawn>();
  private dotLayer = L.layerGroup();
  private chipLayer = L.layerGroup();
  /** server clock minus local clock, seconds */
  private offset = 0;
  private lastPass = 0;
  private dirty = true;
  private chips = false;
  /** the selected bus when drawn as a dot: a ring above the route lines */
  private ring: L.CircleMarker | null = null;
  private ringKey: string | null = null;

  constructor(private ctx: LiveContext) {
    this.dotLayer.addTo(ctx.map);
    this.chipLayer.addTo(ctx.map);
  }

  update(now: number, rows: LiveRow[]) {
    this.offset = now - Date.now() / 1000;
    mergeTracks(this.tracks, rows, now, (id) => this.ctx.shape(id));
    for (const [key, d] of this.drawn) if (!this.tracks.has(key)) this.hide(key, d);
    this.dirty = true;
  }

  /** forget cached styles (mode / selection changed) */
  restyle() {
    for (const d of this.drawn.values()) d.style = '';
    this.dirty = true;
  }

  /** the view or zoom changed */
  refilter() {
    this.dirty = true;
  }

  /** where a bus is drawn now */
  positionOf(key: string): L.LatLngTuple | null {
    const track = this.tracks.get(key);
    if (!track) return null;
    const p = trackPosition(track, Date.now() / 1000 + this.offset, track.route ? this.ctx.shape(track.route) : null);
    return [p.lat, p.lon];
  }

  /** what is drawn now (for the dev preview and end-to-end checks) */
  probe() {
    const buses: {
      key: string; route: string | null; x: number; y: number; lat: number; lon: number; onLine: boolean; offRoute: boolean;
    }[] = [];
    for (const [key, d] of this.drawn) {
      const marker = d.dot ?? d.chip;
      const track = this.tracks.get(key);
      if (!marker || !track) continue;
      const p = this.ctx.map.latLngToContainerPoint(marker.getLatLng());
      // moving along its route line (true), or between reports without one (hops)
      const onLine = track.leg.along && !!track.route && !!this.ctx.shape(track.route);
      const ll = marker.getLatLng();
      buses.push({
        key, route: track.route, x: Math.round(p.x), y: Math.round(p.y), lat: ll.lat, lon: ll.lng, onLine,
        offRoute: track.row[R.dist] === null,
      });
    }
    return { tracks: this.tracks.size, chips: this.chips, buses };
  }

  private hide(key: string, d: Drawn) {
    if (d.dot) this.dotLayer.removeLayer(d.dot);
    if (d.chip) this.chipLayer.removeLayer(d.chip);
    this.drawn.delete(key);
    if (key === this.ringKey) this.removeRing();
  }

  private removeRing() {
    if (this.ring) this.ctx.map.removeLayer(this.ring);
    this.ring = null;
    this.ringKey = null;
  }

  private placeRing(key: string, p: Fix, color: string) {
    if (!this.ring) {
      this.ring = L.circleMarker([p.lat, p.lon], {
        pane: 'pin', radius: 8, color: '#202124', weight: 3, fillOpacity: 1, bubblingMouseEvents: false,
      });
      this.ring.on('click', () => this.ringKey && this.ctx.post({ type: 'tap', kind: 'live', key: this.ringKey }));
      this.ring.addTo(this.ctx.map);
    }
    this.ringKey = key;
    this.ring.setLatLng([p.lat, p.lon]);
    this.ring.setStyle({ fillColor: color });
  }

  draw(nowMs: number) {
    if (!this.dirty && nowMs - this.lastPass < (this.chips ? CHIP_EVERY_MS : DOT_EVERY_MS)) return;
    this.dirty = false;
    this.lastPass = nowMs;

    const t = Date.now() / 1000 + this.offset;
    const { map, levels } = this.ctx;
    const zoom = map.getZoom();
    const view = map.getBounds().pad(0.2);
    const filter = this.ctx.filter();
    const mode = this.ctx.mode();
    const selected = this.ctx.selected();
    const shown: [string, Track, Fix][] = [];
    const missing = new Set<string>();
    for (const [key, track] of this.tracks) {
      if (!busVisible(track.route, key, zoom, filter)) continue;
      const shape = track.route ? this.ctx.shape(track.route) : null;
      const p = trackPosition(track, t, shape);
      if (key !== selected && !view.contains([p.lat, p.lon])) continue;
      shown.push([key, track, p]);
      if (track.route && !shape && track.leg.along) missing.add(track.route);
    }
    if (missing.size) this.ctx.needShapes([...missing]);
    const keep = new Set(shown.map(([key]) => key));
    for (const [key, d] of this.drawn) if (!keep.has(key)) this.hide(key, d);
    if (selected === null || !keep.has(selected)) this.removeRing();

    this.chips = shown.length <= CHIP_LIMIT;
    for (const [key, track, p] of shown) {
      let d = this.drawn.get(key);
      if (!d) {
        d = { style: '' };
        this.drawn.set(key, d);
      }
      const occ = track.row[R.occ];
      const color =
        mode === 'crowding'
          ? occ === null ? NO_DATA_COLOR : LEVEL_COLORS[levelOf(occ, levels)]
          : (track.route && this.ctx.colorOf(track.route)) || CITY_FILL;
      const faded = isStale(track, t);
      const isSelected = key === selected;
      const style = `${color}|${faded}|${isSelected}|${this.chips}`;
      if (this.chips) this.drawChip(key, d, track, p, color, style, faded, isSelected);
      else this.drawDot(key, d, p, color, style, faded, isSelected);
    }
  }

  private drawDot(key: string, d: Drawn, p: Fix, color: string, style: string, faded: boolean, selected: boolean) {
    if (d.chip) {
      this.chipLayer.removeLayer(d.chip);
      d.chip = undefined;
    }
    if (!d.dot) {
      d.dot = L.circleMarker([p.lat, p.lon], { renderer: this.ctx.renderer, radius: 5, bubblingMouseEvents: false });
      d.dot.on('click', () => this.ctx.post({ type: 'tap', kind: 'live', key }));
      d.dot.addTo(this.dotLayer);
    } else {
      d.dot.setLatLng([p.lat, p.lon]);
    }
    if (selected) this.placeRing(key, p, color);
    if (style === d.style) return;
    d.style = style;
    d.dot.setStyle({
      color: '#fff',
      weight: 1,
      fillColor: color,
      fillOpacity: faded ? 0.25 : 0.95,
      opacity: faded ? 0.3 : 1,
    });
  }

  private drawChip(key: string, d: Drawn, track: Track, p: Fix, color: string, style: string, faded: boolean, selected: boolean) {
    if (d.dot) {
      this.dotLayer.removeLayer(d.dot);
      d.dot = undefined;
    }
    if (key === this.ringKey) this.removeRing();
    if (!d.chip) {
      const label = track.route ? routeParts(track.route)[0] : '?';
      d.chip = L.marker([p.lat, p.lon], {
        icon: L.divIcon({ className: 'bus-icon', html: `<div class="bus live">${escapeHtml(label)}</div>`, iconSize: [0, 0] }),
        keyboard: false,
        zIndexOffset: selected ? 1000 : 150,
      });
      d.chip.on('click', () => this.ctx.post({ type: 'tap', kind: 'live', key }));
      d.chip.addTo(this.chipLayer);
      d.style = '';
    } else {
      d.chip.setLatLng([p.lat, p.lon]);
    }
    const el = d.chip.getElement()?.firstElementChild as HTMLElement | null | undefined;
    if (!el || style === d.style) return;
    d.style = style;
    el.style.background = color;
    el.style.color = color === LEVEL_COLORS.Medium ? '#202124' : '#fff';
    el.classList.toggle('sel', selected);
    el.classList.toggle('stale', faded);
    d.chip.setZIndexOffset(selected ? 1000 : 150);
  }
}

const escapeHtml = (s: string) =>
  s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
