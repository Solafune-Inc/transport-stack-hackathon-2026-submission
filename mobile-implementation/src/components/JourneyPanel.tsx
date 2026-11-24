import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import { useEffect, useMemo, useState } from 'react';
import { FlatList, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { LEVEL_LABEL, describeLoad } from '../logic/crowding';
import { colorsByNumber } from '../logic/focus';
import { searchStops, type StopGroup } from '../logic/lookup';
import { CHANGE_PENALTY_MIN, changeText, findLeaveLater, sortOptions, toOptions, type JourneyOption, type SortMode } from '../logic/planner';
import { DAY, fmtTime } from '../logic/time';
import { fetchPlan } from '../live/api';
import type { Meta, PlanResponse } from '../types';
import { LevelBadge } from './Badges';
import { TripChips, type SelectedJourney } from './TopBar';
import { C, ui } from './theme';

const SORTS: { key: SortMode; label: string }[] = [
  { key: 'balanced', label: 'Balanced' },
  { key: 'fastest', label: 'Fastest' },
  { key: 'least_crowded', label: 'Least crowded' },
];
const MAX_SHOWN = 8;

const mins = (m: number) => `${Math.round(m)} min`;

/** the answer to one request (from, to, time, server); another request in flight = loading */
type PlanResult = { key: string } & ({ state: 'error'; message: string } | { state: 'ok'; plan: PlanResponse; t: number });

function OptionRow({ option, numbers, colors, capacity, onPress }: {
  option: JourneyOption;
  numbers: string[];
  colors: Record<string, string>;
  capacity: number;
  onPress(): void;
}) {
  const change = changeText(option);
  return (
    <Pressable onPress={onPress} style={styles.option} accessibilityRole="button">
      <TripChips numbers={numbers} colors={colors} />
      <View style={styles.optionMain}>
        <Text style={styles.optionTimes}>
          {fmtTime(option.depart)} → {fmtTime(option.arrive)}
        </Text>
        <Text style={styles.optionSub}>
          {mins(option.rideMin)} {change ? 'trip' : 'ride'} · wait {mins(option.waitMin)} ·{' '}
          {change ? 'busiest bus: ' : ''}
          {describeLoad(option.occ, capacity)}
          {option.confidence === 'low' ? ' · low confidence' : ''}
        </Text>
        {change ? <Text style={styles.optionSub}>{change}</Text> : null}
      </View>
      <LevelBadge level={option.confidence === 'none' ? null : option.level} />
    </Pressable>
  );
}

/** Buses between any two stops (direct or with one change), from the server's timetable, ranked by time and crowding. */
export function JourneyPanel({ url, meta, groups, now, visible, onClose, onSelect }: {
  url: string;
  meta: Meta;
  /** every stop, grouped by name (null while loading) */
  groups: StopGroup[] | null;
  /** seconds since midnight in Delhi */
  now: number;
  visible: boolean;
  onClose(): void;
  onSelect(journey: SelectedJourney): void;
}) {
  const [from, setFrom] = useState<StopGroup | null>(null);
  const [to, setTo] = useState<StopGroup | null>(null);
  const [editing, setEditing] = useState<'from' | 'to' | null>(null);
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<SortMode>('balanced');
  const [queryT, setQueryT] = useState(Math.floor(now));
  const [answer, setAnswer] = useState<PlanResult | null>(null);
  const key = from && to ? `${url}|${from.id}|${to.id}|${queryT}` : null;
  const result = answer && answer.key === key ? answer : null;

  useEffect(() => {
    if (!from || !to || !visible || !key) return;
    let cancelled = false;
    fetchPlan(url, from.id, to.id, queryT)
      .then((plan) => !cancelled && setAnswer({ key, state: 'ok', plan, t: queryT }))
      .catch((e: Error) => !cancelled && setAnswer({ key, state: 'error', message: e.message }));
    return () => {
      cancelled = true;
    };
  }, [url, from, to, queryT, visible, key]);

  const matches = useMemo(() => (groups ? searchStops(groups, query) : []), [groups, query]);
  const plan = result?.state === 'ok' ? result.plan : null;
  const options = useMemo(() => (result?.state === 'ok' ? toOptions(result.plan.options, result.t) : []), [result]);
  const shown = useMemo(() => sortOptions(options, sort).slice(0, MAX_SHOWN), [options, sort]);
  const leaveLater = useMemo(() => findLeaveLater(options), [options]);
  const colors = useMemo(() => {
    if (!plan) return {};
    const ids = [...plan.served_by, ...plan.options.flatMap((o) => (o.legs ?? []).map((l) => l.routeId))];
    return colorsByNumber(ids.map((id) => plan.routes[id]?.number ?? id));
  }, [plan]);
  const numbersOf = (o: JourneyOption) => o.legs.map((l) => plan?.routes[l.routeId]?.number ?? l.routeId);

  const pick = (g: StopGroup) => {
    if (editing === 'from') setFrom(g);
    else setTo(g);
    setEditing(null);
    setQuery('');
    setQueryT(Math.floor(now));
  };

  if (!visible) return null;

  const choose = (o: JourneyOption) => {
    if (!plan || !from || !to) return;
    const numbers = numbersOf(o);
    onSelect({ option: o, numbers, colors: Object.fromEntries(numbers.map((n) => [n, colors[n]])), fromName: from.name, toName: to.name });
  };

  const field = (which: 'from' | 'to', value: StopGroup | null, placeholder: string) => (
    <Pressable
      onPress={() => setEditing(which)}
      style={[styles.field, editing === which && styles.fieldActive]}
      accessibilityRole="button"
      accessibilityLabel={placeholder}
    >
      <MaterialIcons name={which === 'from' ? 'trip-origin' : 'place'} size={18} color={which === 'from' ? C.blue : '#d93025'} />
      <Text style={[styles.fieldText, !value && styles.placeholder]} numberOfLines={1}>
        {value ? value.name : placeholder}
      </Text>
    </Pressable>
  );

  const shift = (s: number) => setQueryT((t) => (((t + s) % DAY) + DAY) % DAY);

  return (
    <View style={[ui.card, styles.panel]}>
      <View style={styles.header}>
        <Text style={styles.title}>Plan a bus trip</Text>
        <Pressable onPress={onClose} hitSlop={12} accessibilityRole="button" accessibilityLabel="Close planner">
          <MaterialIcons name="close" size={22} color={C.sub} />
        </Pressable>
      </View>
      <View style={ui.row}>
        <View style={styles.fields}>
          {field('from', from, 'Choose starting stop')}
          {field('to', to, 'Choose destination stop')}
        </View>
        <Pressable
          onPress={() => {
            setFrom(to);
            setTo(from);
          }}
          style={styles.swap}
          accessibilityRole="button"
          accessibilityLabel="Swap from and to"
        >
          <MaterialIcons name="swap-vert" size={22} color={C.sub} />
        </Pressable>
      </View>

      {editing ? (
        <View style={styles.picker}>
          <TextInput
            autoFocus
            value={query}
            onChangeText={setQuery}
            placeholder="Search any Delhi bus stop"
            placeholderTextColor={C.sub}
            style={styles.search}
          />
          {!groups ? (
            <Text style={ui.note}>Loading stops from the server…</Text>
          ) : !query.trim() ? (
            <Text style={ui.note}>Type part of a stop name, e.g. &quot;Shahdara&quot;.</Text>
          ) : (
            <FlatList
              data={matches}
              keyExtractor={(g) => g.id}
              keyboardShouldPersistTaps="handled"
              style={styles.list}
              ListEmptyComponent={<Text style={ui.note}>No stop matches &quot;{query}&quot;.</Text>}
              renderItem={({ item }) => (
                <Pressable onPress={() => pick(item)} style={styles.stopRow}>
                  <Text style={styles.stopName}>{item.name}</Text>
                  <Text style={styles.stopRoutes}>
                    {item.nRoutes} route{item.nRoutes === 1 ? '' : 's'}
                    {item.ids.length > 1 ? ` · ${item.ids.length} stops (both sides of the road)` : ''}
                  </Text>
                </Pressable>
              )}
            />
          )}
        </View>
      ) : (
        <ScrollView style={styles.results} keyboardShouldPersistTaps="handled">
          {from && to ? (
            <>
              <View style={[ui.row, styles.when]}>
                <MaterialIcons name="schedule" size={16} color={C.sub} />
                <Text style={styles.whenText}>Leaving after {fmtTime(queryT)}</Text>
                <Pressable onPress={() => shift(-3600)} hitSlop={6} style={styles.step} accessibilityRole="button">
                  <Text style={styles.stepText}>−1 h</Text>
                </Pressable>
                <Pressable onPress={() => setQueryT(Math.floor(now))} hitSlop={6} style={styles.step} accessibilityRole="button">
                  <Text style={styles.stepText}>Now</Text>
                </Pressable>
                <Pressable onPress={() => shift(3600)} hitSlop={6} style={styles.step} accessibilityRole="button">
                  <Text style={styles.stepText}>+1 h</Text>
                </Pressable>
              </View>
              <View style={styles.sorts}>
                {SORTS.map((s) => (
                  <Pressable
                    key={s.key}
                    onPress={() => setSort(s.key)}
                    style={[styles.sort, sort === s.key && styles.sortActive]}
                    accessibilityRole="button"
                    accessibilityState={{ selected: sort === s.key }}
                  >
                    <Text style={[styles.sortText, sort === s.key && styles.sortTextActive]}>{s.label}</Text>
                  </Pressable>
                ))}
              </View>
              {!result ? <Text style={ui.note}>Finding buses…</Text> : null}
              {result?.state === 'error' ? (
                <Text style={[ui.note, styles.error]}>Couldn&apos;t plan this trip: {result.message}</Text>
              ) : null}
              {plan && leaveLater ? (
                <Pressable style={styles.tip} onPress={() => choose(leaveLater.option)} accessibilityRole="button">
                  <Text style={styles.tipText}>
                    Less crowded choice: the {numbersOf(leaveLater.option).join(' › ')} at{' '}
                    {fmtTime(leaveLater.option.depart)} ({LEVEL_LABEL[leaveLater.option.level].toLowerCase()} instead of{' '}
                    {LEVEL_LABEL[leaveLater.instead.level].toLowerCase()}), arriving{' '}
                    {leaveLater.extraMin === 0 ? 'at the same time' : `${leaveLater.extraMin} min later`}.
                  </Text>
                </Pressable>
              ) : null}
              {plan
                ? shown.map((o) => (
                    <OptionRow
                      key={`${o.legs.map((l) => `${l.routeId}:${l.trip}`).join('|')}:${o.depart}`}
                      option={o}
                      numbers={numbersOf(o)}
                      colors={colors}
                      capacity={meta.assumptions.capacity}
                      onPress={() => choose(o)}
                    />
                  ))
                : null}
              {plan && !shown.length ? (
                <Text style={ui.note}>
                  {plan.served_by.length
                    ? 'No departures in the 2 hours after this time.'
                    : 'No bus between these stops in this direction, direct or with one change, in the next 2 hours.'}
                </Text>
              ) : null}
              <Text style={ui.note}>
                Times from the GTFS timetable. Crowding = October 2026 e-ticket average on the busiest stretch of your
                ride, for that kind of day (weekday, Saturday or Sunday/holiday); with a change, the busier of the two
                buses. Balanced adds 0/4/10/18 min for seats available / standing room / crowded / packed and{' '}
                {CHANGE_PENALTY_MIN} min per
                change. A change is at the same stop or a short walk (up to 250 m), with at least 2 min to change and
                at most 30 min to wait. Same-named stops across the road count as the same stop.
              </Text>
            </>
          ) : (
            <Text style={ui.note}>
              Choose any two Delhi bus stops to see buses, direct or with one change, and how crowded they will be.
            </Text>
          )}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { padding: 12, maxHeight: '100%', flexShrink: 1 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 },
  title: { fontSize: 17, fontWeight: '800', color: C.text },
  fields: { flex: 1, gap: 6 },
  field: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: C.chip,
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 9,
    borderWidth: 1.5,
    borderColor: 'transparent',
  },
  fieldActive: { borderColor: C.blue, backgroundColor: '#fff' },
  fieldText: { flex: 1, fontSize: 14, color: C.text, fontWeight: '600' },
  placeholder: { color: C.sub, fontWeight: '400' },
  swap: { padding: 8, marginLeft: 4 },
  picker: { marginTop: 8 },
  search: {
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 8,
    fontSize: 14,
    color: C.text,
  },
  list: { maxHeight: 280, marginTop: 4 },
  stopRow: { paddingVertical: 9, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: C.line },
  stopName: { fontSize: 14, color: C.text },
  stopRoutes: { fontSize: 11, color: C.sub, marginTop: 1 },
  results: { marginTop: 8, flexGrow: 0, flexShrink: 1 },
  when: { gap: 6, flexWrap: 'wrap' },
  whenText: { fontSize: 13, color: C.text, fontWeight: '600', marginRight: 2 },
  step: { borderRadius: 12, backgroundColor: C.chip, paddingHorizontal: 8, paddingVertical: 3 },
  stepText: { fontSize: 12, color: C.blueDark, fontWeight: '700' },
  sorts: { flexDirection: 'row', gap: 6, marginVertical: 8 },
  sort: { borderRadius: 16, borderWidth: 1, borderColor: C.line, paddingHorizontal: 12, paddingVertical: 6 },
  sortActive: { backgroundColor: C.blueSoft, borderColor: C.blueSoft },
  sortText: { fontSize: 13, color: C.text },
  sortTextActive: { color: C.blueDark, fontWeight: '700' },
  tip: { backgroundColor: C.tip, borderRadius: 10, padding: 10, marginBottom: 6 },
  tipText: { fontSize: 13, color: C.text, lineHeight: 18 },
  error: { color: '#d93025' },
  option: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  optionMain: { flex: 1, marginHorizontal: 10 },
  optionTimes: { fontSize: 15, fontWeight: '800', color: C.text },
  optionSub: { fontSize: 12, color: C.sub, marginTop: 2 },
});
