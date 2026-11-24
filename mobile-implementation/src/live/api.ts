import type { LivePayload, PlanResponse, Route, RouteDetail, StopInfo, StopsPayload } from '../types';

const TIMEOUT_MS = 8_000;
/** the server answers at most this many routes per request */
const ROUTES_PER_REQUEST = 300;

export async function request(url: string, timeoutMs = TIMEOUT_MS): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: ctrl.signal });
    if (!res.ok) {
      const body = (await res.json().catch(() => null)) as { detail?: string } | null;
      throw new Error(body?.detail ?? `HTTP ${res.status}`);
    }
    return res;
  } catch (e) {
    if (e instanceof Error && e.name === 'AbortError') throw new Error(`No answer within ${timeoutMs / 1000} s`);
    throw e instanceof Error ? e : new Error(String(e));
  } finally {
    clearTimeout(timer);
  }
}

const json = async <T>(url: string, timeoutMs?: number): Promise<T> => (await (await request(url, timeoutMs)).json()) as T;

/** All live buses; null (HTTP 204) when the server has no feed newer than `since`. */
export async function fetchLive(baseUrl: string, since: number | null): Promise<LivePayload | null> {
  const res = await request(`${baseUrl}/api/live${since !== null ? `?since=${since}` : ''}`);
  return res.status === 204 ? null : ((await res.json()) as LivePayload);
}

export const fetchStops = (baseUrl: string) => json<StopsPayload>(`${baseUrl}/api/stops`, 20_000);

export const fetchStop = (baseUrl: string, stopId: string, t: number) =>
  json<StopInfo>(`${baseUrl}/api/stops/${encodeURIComponent(stopId)}?t=${Math.floor(t)}`);

/** Several routes at once (split into batches the server accepts). */
export async function fetchRoutes(baseUrl: string, ids: string[]): Promise<Record<string, RouteDetail>> {
  const out: Record<string, RouteDetail> = {};
  for (let i = 0; i < ids.length; i += ROUTES_PER_REQUEST) {
    const batch = ids.slice(i, i + ROUTES_PER_REQUEST).map(encodeURIComponent).join(',');
    Object.assign(out, (await json<{ routes: Record<string, RouteDetail> }>(`${baseUrl}/api/routes?ids=${batch}`, 30_000)).routes);
  }
  return out;
}

/** Route lines only (much lighter than fetchRoutes). */
export async function fetchShapes(baseUrl: string, ids: string[]): Promise<Record<string, Route['shape']>> {
  const batch = ids.slice(0, ROUTES_PER_REQUEST).map(encodeURIComponent).join(',');
  return (await json<{ shapes: Record<string, Route['shape']> }>(`${baseUrl}/api/shapes?ids=${batch}`, 30_000)).shapes;
}

export const fetchPlan = (baseUrl: string, from: string, to: string, t: number) =>
  json<PlanResponse>(
    `${baseUrl}/api/plan?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}&t=${Math.floor(t)}&transfers=1`,
  );
