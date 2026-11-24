/**
 * Bus-stop signs on the map page: a rounded square with a white border and a bus symbol.
 * Stops are drawn on the canvas they share with the live bus dots (so both stay tappable, see
 * map/main.ts), as a pre-rendered image per look, which keeps hundreds of them cheap to redraw.
 * The tapped stop is a bigger DOM version of the same sign, above the buses.
 */
import * as L from 'leaflet';

/** Material Icons "directions_bus" (Apache-2.0), 24 × 24 */
const BUS_GLYPH =
  'M4 16c0 .88.39 1.67 1 2.22V20c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1h8v1c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1.78c.61-.55 1-1.34 1-2.22V6c0-3.5-3.58-4-8-4s-8 .5-8 4v10zm3.5 1c-.83 0-1.5-.67-1.5-1.5S6.67 14 7.5 14s1.5.67 1.5 1.5S8.33 17 7.5 17zm9 0c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm1.5-6H6V6h12v5z';

export const STOP_COLOR = '#1a73e8';
/** sprites are drawn at this many device pixels per CSS pixel, so they stay sharp on phones */
const SPRITE_SCALE = 3;
/** room around the sign for its soft outline */
const PAD = 2;
const sprites = new Map<string, HTMLCanvasElement>();

/** Sign size (CSS px) for a zoom level: small along a selected route zoomed out, bigger up close. */
export const stopSize = (zoom: number): number => (zoom >= 16 ? 22 : zoom >= 14 ? 18 : 14);

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function sprite(size: number, fill: string, glyph: string): HTMLCanvasElement {
  const key = `${size}|${fill}|${glyph}`;
  const cached = sprites.get(key);
  if (cached) return cached;
  const total = size + 2 * PAD;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = Math.ceil(total * SPRITE_SCALE);
  const ctx = canvas.getContext('2d')!;
  ctx.scale(SPRITE_SCALE, SPRITE_SCALE);
  const border = Math.max(1.5, size / 10);
  const r = size * 0.24;
  ctx.fillStyle = 'rgba(32, 33, 36, 0.35)'; // soft edge so the white border shows on white roads
  roundRect(ctx, PAD - 1, PAD - 0.5, size + 2, size + 2, r + 1);
  ctx.fill();
  ctx.fillStyle = '#fff';
  roundRect(ctx, PAD, PAD, size, size, r);
  ctx.fill();
  ctx.fillStyle = fill;
  roundRect(ctx, PAD + border, PAD + border, size - 2 * border, size - 2 * border, Math.max(1, r - border / 2));
  ctx.fill();
  const g = (size - 2 * border) * 0.8;
  ctx.translate(PAD + (size - g) / 2, PAD + (size - g) / 2);
  ctx.scale(g / 24, g / 24);
  ctx.fillStyle = glyph;
  ctx.fill(new Path2D(BUS_GLYPH));
  sprites.set(key, canvas);
  return canvas;
}

export interface StopIconOptions extends L.CircleMarkerOptions {
  /** colour of the bus symbol */
  glyph: string;
}

interface CanvasInternals {
  _drawing: boolean;
  _ctx: CanvasRenderingContext2D;
}

/**
 * A stop sign on a Leaflet canvas renderer. It behaves like a circle marker of radius size / 2 for
 * taps, culling and redraws; only the drawing is replaced.
 */
export const StopIcon = L.CircleMarker.extend({
  _updatePath(this: L.CircleMarker & { _renderer: CanvasInternals; _point: L.Point; _radius: number; _empty(): boolean }) {
    if (!this._renderer._drawing || this._empty()) return;
    const o = this.options as StopIconOptions;
    const img = sprite(Math.round(this._radius * 2), o.fillColor ?? STOP_COLOR, o.glyph);
    const total = img.width / SPRITE_SCALE;
    this._renderer._ctx.drawImage(img, this._point.x - total / 2, this._point.y - total / 2, total, total);
  },
}) as unknown as new (latlng: L.LatLngExpression, options: StopIconOptions) => L.CircleMarker;

/** The tapped stop: the same sign, bigger and outlined, as a DOM marker above the buses. */
export function pinIcon(fill: string, glyph: string): L.DivIcon {
  return L.divIcon({
    className: 'stop-pin-icon',
    html: `<div class="stop-pin" style="background:${fill}"><svg viewBox="0 0 24 24"><path fill="${glyph}" d="${BUS_GLYPH}"/></svg></div>`,
    iconSize: [0, 0],
  });
}
