This is an Expo/React Native mobile application. Prioritize mobile-first patterns, performance, and cross-platform compatibility.

## Expo has changed — do not trust your training data

Expo ships breaking changes every SDK release. APIs you remember are likely renamed, moved, or removed. Before writing any code that touches an Expo, EAS, or React Native API:

1. Read the major version of the `expo` package in `package.json`.
2. Fetch the matching versioned docs: `https://docs.expo.dev/versions/v<major>.0.0/`
3. For anything else, fetch https://docs.expo.dev/llms.txt — an index of all Expo docs with corrections to common LLM misconceptions. Follow its links to the specific page you need; never answer from memory.

## Commands

Use `bunx` instead of `npx` if the project uses bun (`bun.lock` present).

```bash
npx expo install <package>  # ALWAYS use instead of npm/yarn/pnpm/bun add — resolves SDK-compatible versions
npx expo start              # start the dev server
npx expo lint               # lint
npx tsc --noEmit            # typecheck
npx expo-doctor             # diagnose dependency and config issues
npx expo install --fix      # fix incompatible package versions
```

Run lint and typecheck before declaring any task done.

## This app's structure

- Single screen, no navigation library: `App.tsx` composes the map, top bar, bottom bar (Bus Routes / Crowding), live status bar, detail sheets and the journey planner from `src/components/`.
- What the map shows comes from `src/logic/focus.ts`: nothing selected = stops and live buses only from zoom 14; a selected stop / bus / chosen trip becomes a `MapFocus` (its routes, only their buses, at any zoom). A selection is cleared only by closing its sheet or Android Back, never by tapping the map.
- The map is a Leaflet + MapLibre page (`map/main.ts`) bundled by `scripts/build-map.mjs` into the gitignored `src/map/mapHtml.generated.ts` and hosted in `react-native-webview` (`src/map/MapView.tsx`; `MapView.web.tsx` uses an iframe). React Native sends `MapCommand`s; the page posts `MapMessage`s (`src/types.ts`).
- Pure logic shared by the app, the map page and the tests lives in `src/logic/` (no React Native imports there).
- Data: everything (stops, routes, crowding, planner, live buses) comes from the Python server (`../src/api/main.py`, port 8787) through `src/live/api.ts`; `map/live.ts` draws the buses. The Transport Stack API key lives only in the repo-root `.env` read by that server. Never add it to this folder's `.env` or any `EXPO_PUBLIC_*` variable.
- The only bundled data is `assets/data/meta.json` (attribution + crowding assumptions), exported by `src/export_mobile_data.py` at the repo root; regenerate it rather than editing it.
- On the map page, stops and live bus dots must share one canvas renderer: Leaflet only delivers taps to the topmost canvas.
- See `README.md` for run, data and credit details.

## Building with EAS

Use EAS to build, sign, and submit the app in the cloud (`eas build`, `eas submit`) and to ship over-the-air updates (`eas update`) — no local Xcode or Android Studio required. Run EAS CLI as `bunx eas-cli <command>` in Bun projects, or `npx eas-cli@latest <command>` otherwise; substitute that for bare `eas` in docs examples.
Docs: https://docs.expo.dev/eas/index.md

## Rules

- If `ios/` and `android/` directories do not exist, they are generated (Continuous Native Generation). Never create or edit them by hand — configure native behavior in `app.json` and config plugins.
- Expo Go only includes its bundled native modules. After adding a library with native code, the app needs a development build: `npx expo run:ios|android` locally, or `eas build --profile development`.
- Prefer recommended Expo modules over third-party libraries, and check your available skills before adding dependencies. Docs: https://docs.expo.dev/versions/latest/index.md
