import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BackHandler, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, useSafeAreaInsets } from 'react-native-safe-area-context';
import { BottomNav } from './src/components/BottomNav';
import { AboutDetail, LiveBusDetail, LiveInfoDetail, RouteSheet, StopDetail } from './src/components/details';
import { JourneyPanel } from './src/components/JourneyPanel';
import { Legend } from './src/components/Legend';
import { LiveBar } from './src/components/LiveBar';
import { Sheet } from './src/components/Sheet';
import { C, ui } from './src/components/theme';
import { TopBar, type SelectedJourney } from './src/components/TopBar';
import { META } from './src/data';
import { fetchRoutes, fetchShapes, fetchStop } from './src/live/api';
import { defaultLiveUrl } from './src/live/config';
import { useLiveFeed, useNow, useStops } from './src/live/useLiveFeed';
import { hourOf } from './src/logic/crowding';
import { ROUTE_PALETTE, colorsByNumber, focusPlan, toMapFocus, type Selection } from './src/logic/focus';
import { istSeconds } from './src/logic/live';
import { groupStops, routeParts } from './src/logic/lookup';
import { MapView, type MapHandle } from './src/map/MapView';
import type { LivePayload, LiveRow, MapCommand, MapMessage, MapMode, MapState, RouteDetail, StopInfo } from './src/types';

const INITIAL: MapState = { mode: 'routes' };

export default function App() {
  return (
    <SafeAreaProvider>
      <StatusBar style="dark" />
      <Main />
    </SafeAreaProvider>
  );
}

interface StopState {
  stopId: string;
  info: StopInfo | null;
  error: string | null;
}

function Main() {
  const insets = useSafeAreaInsets();
  const map = useRef<MapHandle>(null);
  const [mode, setMode] = useState<MapMode>(INITIAL.mode);
  const [selection, setSelection] = useState<Selection>(null);
  const [plannerOpen, setPlannerOpen] = useState(false);
  const [journey, setJourney] = useState<SelectedJourney | null>(null);
  const [url, setUrl] = useState(defaultLiveUrl);
  const [zoomDetail, setZoomDetail] = useState(false);
  const [routes, setRoutes] = useState<Record<string, RouteDetail>>({});
  const [stopState, setStopState] = useState<StopState | null>(null);
  const requested = useRef(new Set<string>());

  const send = useCallback((cmd: MapCommand) => map.current?.send(cmd), []);

  const onLivePayload = useCallback(
    (p: LivePayload) => send({ liveData: { now: p.now, rows: p.vehicles } }),
    [send],
  );
  const liveStatus = useLiveFeed(url, onLivePayload);
  const offset = liveStatus.state === 'connecting' ? 0 : liveStatus.offset;
  const livePayload = liveStatus.state === 'connecting' ? null : liveStatus.payload;
  const liveRows = useMemo(
    () => new Map<string, LiveRow>(livePayload?.vehicles.map((r) => [r[0], r]) ?? []),
    [livePayload],
  );

  // Delhi time: the hour picks the crowding shown, the minute refreshes a stop's next departures
  const phoneNow = useNow(true, 15_000);
  const istNow = istSeconds(phoneNow + offset);
  const hour = hourOf(istNow);
  const minuteT = Math.floor(istNow / 60) * 60;

  const stops = useStops(url);
  const stopById = useMemo(() => new Map(stops?.map((s) => [s.id, s]) ?? []), [stops]);
  const groups = useMemo(() => (stops ? groupStops(stops) : null), [stops]);
  useEffect(() => {
    if (stops) send({ stops: stops.map((s) => [s.id, s.lat, s.lon] as [string, number, number]) });
  }, [stops, send]);

  // the stop or bus sheet underneath a route sheet
  const base = selection?.kind === 'route' ? selection.parent : selection;
  const stopId = base?.kind === 'stop' ? base.stopId : null;
  const busKey = base?.kind === 'live' ? base.key : null;
  const busRoute = busKey ? liveRows.get(busKey)?.[1] ?? null : null;

  useEffect(() => {
    if (!stopId) return;
    let cancelled = false;
    setStopState((s) => (s?.stopId === stopId ? s : { stopId, info: null, error: null }));
    fetchStop(url, stopId, minuteT)
      .then((info) => !cancelled && setStopState({ stopId, info, error: null }))
      .catch(
        (e: Error) =>
          !cancelled && setStopState((s) => ({ stopId, info: s?.stopId === stopId ? s.info : null, error: e.message })),
      );
    return () => {
      cancelled = true;
    };
  }, [url, stopId, minuteT]);
  const stopInfo = stopState && stopState.stopId === stopId ? stopState.info : null;

  const journeyHl = useMemo(
    () => (journey ? journey.option.legs.map(({ routeId, fromPos, toPos }) => ({ routeId, fromPos, toPos })) : []),
    [journey],
  );
  const plan = useMemo(
    () => focusPlan(selection, { stopInfo, routeOfBus: () => busRoute, journey: journeyHl }),
    [selection, stopInfo, busRoute, journeyHl],
  );
  const colors = useMemo((): Record<string, string> => {
    if (stopId && stopInfo) return colorsByNumber(stopInfo.routes.map((r) => r.number));
    if (!selection && journey) return journey.colors;
    return colorsByNumber((plan?.routeIds ?? []).map((id) => routeParts(id)[0]));
  }, [stopId, stopInfo, selection, journey, plan]);

  // fetch the routes to draw that are not cached yet (one request for all of them)
  useEffect(() => {
    const missing = (plan?.routeIds ?? []).filter((id) => !routes[id] && !requested.current.has(id));
    if (!missing.length) return;
    missing.forEach((id) => requested.current.add(id));
    fetchRoutes(url, missing)
      .then((got) => setRoutes((prev) => ({ ...prev, ...got })))
      .catch(() => missing.forEach((id) => requested.current.delete(id)));
  }, [plan, routes, url]);

  const fitJourney = !selection && journey !== null;
  const mapFocus = useMemo(
    () => (plan ? toMapFocus(plan, routes, colors, hour, fitJourney) : null),
    [plan, routes, colors, hour, fitJourney],
  );
  useEffect(() => {
    send({ focus: mapFocus });
  }, [mapFocus, send]);
  useEffect(() => {
    send({ selectedBus: busKey });
  }, [busKey, send]);

  const onMessage = useCallback((msg: MapMessage) => {
    if (msg.type === 'zoom') {
      setZoomDetail(msg.detail);
    } else if (msg.type === 'needShapes') {
      // straight to the map page (it caches them); a failed request is asked for again later.
      // A server started before /api/shapes existed still has the lines in /api/routes.
      fetchShapes(url, msg.ids)
        .catch(async () =>
          Object.fromEntries(Object.entries(await fetchRoutes(url, msg.ids)).map(([id, d]) => [id, d.route.shape])),
        )
        .then((shapes) => send({ shapes }))
        .catch(() => undefined);
    } else if (msg.type === 'tap') {
      setPlannerOpen(false);
      if (msg.kind === 'live') setSelection({ kind: 'live', key: msg.key });
      else setSelection((s) => (s?.kind === 'stop' && s.stopId === msg.stopId ? s : { kind: 'stop', stopId: msg.stopId, only: null }));
    }
  }, [url, send]);

  /** a route sheet returns to the stop / bus sheet it was opened from; others clear the selection */
  const close = useCallback(() => setSelection((s) => (s?.kind === 'route' ? s.parent : null)), []);

  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      if (selection) {
        close();
        return true;
      }
      if (plannerOpen) {
        setPlannerOpen(false);
        return true;
      }
      return false;
    });
    return () => sub.remove();
  }, [selection, plannerOpen, close]);

  const changeMode = (m: MapMode) => {
    setMode(m);
    send({ mode: m });
  };

  const chooseJourney = (j: SelectedJourney) => {
    setJourney(j);
    setPlannerOpen(false);
    setSelection(null);
  };

  const openRoute = (routeId: string) => setSelection((s) => ({ kind: 'route', routeId, parent: s?.kind === 'route' ? s.parent : s }));

  let detail = null;
  if (selection?.kind === 'stop') {
    const sel = selection;
    detail = (
      <StopDetail
        name={stopById.get(sel.stopId)?.name ?? null}
        info={stopInfo}
        error={stopState?.stopId === sel.stopId ? stopState.error : null}
        meta={META}
        hour={hour}
        colors={colors}
        only={sel.only}
        onOnly={(only) => setSelection({ ...sel, only })}
        onRoute={openRoute}
        onClose={close}
      />
    );
  } else if (selection?.kind === 'live') {
    const row = liveRows.get(selection.key);
    const routeId = row?.[1];
    detail = row ? (
      <LiveBusDetail
        row={row}
        detail={routeId ? routes[routeId] ?? null : null}
        color={routeId ? colors[routeParts(routeId)[0]] ?? ROUTE_PALETTE[0] : ROUTE_PALETTE[0]}
        stops={stopById}
        offset={offset}
        meta={META}
        onRoute={openRoute}
        onClose={close}
      />
    ) : (
      <Sheet title="Bus" onClose={close}>
        <Text style={ui.body}>This bus is no longer in the live feed.</Text>
      </Sheet>
    );
  } else if (selection?.kind === 'route') {
    const sel = selection;
    const [number] = routeParts(sel.routeId);
    const siblings =
      stopId && stopInfo
        ? stopInfo.routes.filter((r) => r.number === number && r.id !== sel.routeId).map(({ id, direction }) => ({ id, direction }))
        : [];
    detail = (
      <RouteSheet
        detail={routes[sel.routeId] ?? null}
        color={colors[number] ?? ROUTE_PALETTE[0]}
        hour={hour}
        meta={META}
        siblings={siblings}
        onSwitch={(routeId) => setSelection({ ...sel, routeId })}
        onClose={close}
      />
    );
  } else if (selection?.kind === 'liveInfo') {
    detail = <LiveInfoDetail key={url} url={url} status={liveStatus} onUrl={setUrl} onClose={close} />;
  } else if (selection?.kind === 'about') {
    detail = <AboutDetail meta={META} onClose={close} />;
  }

  const showZoomHint = !zoomDetail && !plan && !detail && !plannerOpen;

  return (
    <View style={styles.root}>
      <View style={styles.mapArea}>
        <MapView ref={map} levels={META.assumptions.levels} initial={INITIAL} onMessage={onMessage} />

        <View style={[styles.top, { top: insets.top + 8 }]} pointerEvents="box-none">
          <TopBar
            journey={journey}
            onSearch={() => {
              setSelection(null);
              setPlannerOpen(true);
            }}
            onAbout={() => {
              setPlannerOpen(false);
              setSelection({ kind: 'about' });
            }}
            onClear={() => setJourney(null)}
          />
          {mode === 'crowding' ? (
            <View style={styles.underBar} pointerEvents="box-none">
              <Legend levels={META.assumptions.levels} compact={journey !== null || selection !== null} />
            </View>
          ) : null}
        </View>

        {showZoomHint ? (
          <View style={styles.hintWrap} pointerEvents="none">
            <Text style={[ui.card, styles.hint]}>Zoom in to see bus stops and live buses</Text>
          </View>
        ) : null}

        {detail ? <View style={styles.sheetWrap}>{detail}</View> : null}

        <View
          style={[styles.plannerWrap, { top: insets.top + 8 }]}
          pointerEvents={plannerOpen ? 'box-none' : 'none'}
        >
          <JourneyPanel
            url={url}
            meta={META}
            groups={groups}
            now={istNow}
            visible={plannerOpen}
            onClose={() => setPlannerOpen(false)}
            onSelect={chooseJourney}
          />
        </View>
      </View>

      <LiveBar status={liveStatus} onInfo={() => setSelection({ kind: 'liveInfo' })} />
      <BottomNav mode={mode} onChange={changeMode} bottomInset={insets.bottom} />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#fff' },
  mapArea: { flex: 1 },
  top: { position: 'absolute', left: 12, right: 12 },
  underBar: { flexDirection: 'row', justifyContent: 'flex-end', marginTop: 8 },
  hintWrap: { position: 'absolute', left: 0, right: 0, bottom: 34, alignItems: 'center' },
  hint: { fontSize: 13, fontWeight: '600', color: C.text, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 18, overflow: 'hidden' },
  sheetWrap: { position: 'absolute', left: 8, right: 8, bottom: 8, maxHeight: '60%' },
  plannerWrap: { position: 'absolute', left: 8, right: 8, bottom: 8 },
});
