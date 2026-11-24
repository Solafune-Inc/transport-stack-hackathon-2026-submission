import { useEffect, useRef, useState } from 'react';
import { AppState } from 'react-native';
import { toNetStop } from '../logic/lookup';
import type { LivePayload, NetStop } from '../types';
import { fetchLive, fetchStops } from './api';

/** The phone checks this often; the server answers 204 (no body) until it has a newer feed. */
const POLL_MS = 2_000;
const STOPS_RETRY_MS = 5_000;

export type LiveStatus =
  | { state: 'connecting' }
  /** offset = server clock minus phone clock (s), so ages can tick between responses */
  | { state: 'ok'; payload: LivePayload; offset: number }
  | { state: 'error'; message: string; payload: LivePayload | null; offset: number };

/** Seconds since the epoch on the phone, re-rendering every `everyMs` while `enabled`. */
export function useNow(enabled: boolean, everyMs = 1_000): number {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    if (!enabled) return;
    const id = setInterval(() => setNow(Date.now() / 1000), everyMs);
    return () => clearInterval(id);
  }, [enabled, everyMs]);
  return now;
}

/**
 * Checks GET /api/live every 2 s while the app is in the foreground. Only a newer feed is
 * downloaded (`?since=` + 204), so new GPS reports reach the map within ~2 s of the server.
 */
export function useLiveFeed(baseUrl: string, onPayload: (p: LivePayload) => void): LiveStatus {
  // tagged with the server it came from, so switching servers shows "connecting" straight away
  const [tagged, setTagged] = useState<{ url: string; status: LiveStatus }>({ url: baseUrl, status: { state: 'connecting' } });
  const onPayloadRef = useRef(onPayload);

  useEffect(() => {
    onPayloadRef.current = onPayload;
  }, [onPayload]);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let last: LivePayload | null = null;
    let offset = 0;
    const setStatus = (status: LiveStatus) => setTagged({ url: baseUrl, status });
    const tick = async () => {
      if (AppState.currentState === 'active') {
        try {
          const payload = await fetchLive(baseUrl, last ? last.feed_time : null);
          if (stopped) return;
          if (payload) {
            last = payload;
            offset = payload.now - Date.now() / 1000;
            onPayloadRef.current(payload);
            setStatus({ state: 'ok', payload, offset });
          } else if (last) {
            const payload = last;
            setTagged((t) => (t.url === baseUrl && t.status.state === 'ok' ? t : { url: baseUrl, status: { state: 'ok', payload, offset } }));
          }
        } catch (e) {
          if (stopped) return;
          setStatus({ state: 'error', message: (e as Error).message, payload: last, offset });
        }
      }
      if (!stopped) timer = setTimeout(tick, POLL_MS);
    };
    tick();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [baseUrl]);

  return tagged.url === baseUrl ? tagged.status : { state: 'connecting' };
}

/** Every stop, loaded once from GET /api/stops (retried until the server answers). */
export function useStops(baseUrl: string): NetStop[] | null {
  const [stops, setStops] = useState<NetStop[] | null>(null);
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = async () => {
      try {
        const payload = await fetchStops(baseUrl);
        if (!stopped) setStops(payload.stops.map(toNetStop));
      } catch {
        if (!stopped) timer = setTimeout(load, STOPS_RETRY_MS);
      }
    };
    load();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [baseUrl]);
  return stops;
}
