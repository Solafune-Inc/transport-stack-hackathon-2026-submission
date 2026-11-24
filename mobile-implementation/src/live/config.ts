import Constants from 'expo-constants';

export const LIVE_API_PORT = 8787;

/**
 * Where the live API (src/api/main.py) runs: EXPO_PUBLIC_LIVE_API_URL if set, else the Mac that
 * serves this app in development (Expo Go reports its address), else the page's host on web.
 */
export function defaultLiveUrl(): string {
  const env = process.env.EXPO_PUBLIC_LIVE_API_URL;
  if (env) return env.replace(/\/+$/, '');
  const host = Constants.expoConfig?.hostUri?.split(':')[0];
  if (host && !host.endsWith('.exp.direct')) return `http://${host}:${LIVE_API_PORT}`;
  const page = typeof window !== 'undefined' ? window.location?.hostname : undefined;
  return `http://${page || 'localhost'}:${LIVE_API_PORT}`;
}

/** Accepts "192.168.1.5", "192.168.1.5:8787" or a full URL. */
export function normalizeLiveUrl(input: string): string {
  let url = input.trim().replace(/\/+$/, '');
  if (!/^https?:\/\//.test(url)) url = `http://${url}`;
  if (!/:\d+$/.test(url.replace(/^https?:\/\//, ''))) url = `${url}:${LIVE_API_PORT}`;
  return url;
}
