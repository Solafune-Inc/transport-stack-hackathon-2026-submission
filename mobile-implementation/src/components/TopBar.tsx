import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import { Fragment } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { JourneyOption } from '../logic/planner';
import { fmtTime } from '../logic/time';
import { LevelBadge, RouteChip } from './Badges';
import { C, ui } from './theme';

export interface SelectedJourney {
  option: JourneyOption;
  /** route number of each ride, in order */
  numbers: string[];
  /** colour per route number */
  colors: Record<string, string>;
  fromName: string;
  toName: string;
}

/** The route chips of a trip: "620" or "620 › 534". */
export function TripChips({ numbers, colors }: { numbers: string[]; colors: Record<string, string> }) {
  return (
    <View style={styles.chips}>
      {numbers.map((n, i) => (
        <Fragment key={`${i}:${n}`}>
          {i > 0 ? <MaterialIcons name="chevron-right" size={16} color={C.sub} /> : null}
          <RouteChip number={n} color={colors[n]} />
        </Fragment>
      ))}
    </View>
  );
}

export function TopBar({ journey, onSearch, onAbout, onClear }: {
  journey: SelectedJourney | null;
  onSearch(): void;
  onAbout(): void;
  onClear(): void;
}) {
  if (journey) {
    return (
      <View style={[ui.card, styles.bar]}>
        <Pressable onPress={onSearch} style={styles.journey} accessibilityRole="button" accessibilityLabel="Edit trip">
          <TripChips numbers={journey.numbers} colors={journey.colors} />
          <View style={styles.journeyText}>
            <Text style={styles.journeyTimes}>
              {fmtTime(journey.option.depart)} → {fmtTime(journey.option.arrive)}
            </Text>
            <Text style={styles.journeyStops} numberOfLines={1}>
              {journey.fromName} → {journey.toName}
            </Text>
          </View>
          <LevelBadge level={journey.option.confidence === 'none' ? null : journey.option.level} />
        </Pressable>
        <Pressable onPress={onClear} hitSlop={10} style={styles.icon} accessibilityRole="button" accessibilityLabel="Clear trip">
          <MaterialIcons name="close" size={22} color={C.sub} />
        </Pressable>
      </View>
    );
  }
  return (
    <View style={[ui.card, styles.bar]}>
      <Pressable onPress={onSearch} style={styles.search} accessibilityRole="search" accessibilityLabel="Plan a trip">
        <MaterialIcons name="search" size={22} color={C.sub} />
        <Text style={styles.placeholder}>Plan a trip · From → To</Text>
      </Pressable>
      <Pressable onPress={onAbout} hitSlop={10} style={styles.icon} accessibilityRole="button" accessibilityLabel="About">
        <MaterialIcons name="info-outline" size={22} color={C.sub} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: { flexDirection: 'row', alignItems: 'center', borderRadius: 28, paddingLeft: 14, paddingRight: 6, minHeight: 50 },
  search: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 13 },
  placeholder: { fontSize: 15, color: C.sub },
  icon: { padding: 8 },
  journey: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8 },
  journeyText: { flex: 1 },
  journeyTimes: { fontSize: 15, fontWeight: '800', color: C.text },
  journeyStops: { fontSize: 12, color: C.sub },
  chips: { flexDirection: 'row', alignItems: 'center' },
});
