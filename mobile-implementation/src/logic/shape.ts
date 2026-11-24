import type { Route } from '../types';

/** Point at distance `d` (m) along a shape, clamped to its ends. */
export function pointAtDistance(shape: Route['shape'], d: number): [number, number] {
  if (d <= shape[0][2]) return [shape[0][0], shape[0][1]];
  const last = shape[shape.length - 1];
  if (d >= last[2]) return [last[0], last[1]];
  let lo = 0;
  let hi = shape.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (shape[mid][2] <= d) lo = mid;
    else hi = mid;
  }
  const a = shape[lo];
  const b = shape[hi];
  const f = b[2] === a[2] ? 0 : (d - a[2]) / (b[2] - a[2]);
  return [a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])];
}

/** Shape points between two distances along the route (for segment colouring / highlights). */
export function sliceShape(shape: Route['shape'], d0: number, d1: number): [number, number][] {
  const out: [number, number][] = [pointAtDistance(shape, d0)];
  for (const p of shape) if (p[2] > d0 && p[2] < d1) out.push([p[0], p[1]]);
  out.push(pointAtDistance(shape, d1));
  return out;
}
