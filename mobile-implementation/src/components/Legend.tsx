import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { LEVEL_COLORS, LEVEL_LABEL, NO_DATA_COLOR } from '../logic/crowding';
import type { Levels } from '../types';
import { C, ui } from './theme';

function levelRanges(levels: Levels) {
  let lower = 0;
  return levels.map(([threshold, name]) => {
    const text =
      threshold === null ? `over ${Math.round(lower * 100)}% full` : `${Math.round(lower * 100)}–${Math.round(threshold * 100)}% full`;
    lower = threshold ?? lower;
    return { name, text };
  });
}

/** Crowding scale; collapses to a strip on tap or while a trip / sheet is open. */
export function Legend({ levels, compact }: { levels: Levels; compact: boolean }) {
  const [collapsed, setCollapsed] = useState(false);
  const small = compact || collapsed;
  const ranges = levelRanges(levels);
  return (
    <View style={[ui.card, styles.box, small && styles.boxSmall]}>
      <Pressable
        onPress={() => setCollapsed(!collapsed)}
        style={styles.header}
        accessibilityRole="button"
        accessibilityLabel={small ? 'Expand legend' : 'Collapse legend'}
      >
        <Text style={styles.title}>Expected crowding</Text>
        <MaterialIcons name={small ? 'expand-more' : 'expand-less'} size={18} color={C.sub} />
      </Pressable>
      {small ? (
        <View style={styles.strip}>
          {ranges.map(({ name }) => (
            <View key={name} style={[styles.dot, { backgroundColor: LEVEL_COLORS[name] }]} />
          ))}
          <Text style={styles.stripText}>seats → packed</Text>
        </View>
      ) : (
        <>
          {ranges.map(({ name, text }) => (
            <View key={name} style={styles.item}>
              <View style={[styles.swatch, { backgroundColor: LEVEL_COLORS[name] }]} />
              <Text style={styles.label}>
                {LEVEL_LABEL[name]} <Text style={styles.range}>{text}</Text>
              </Text>
            </View>
          ))}
          <View style={styles.item}>
            <View style={[styles.swatch, { backgroundColor: NO_DATA_COLOR }]} />
            <Text style={styles.label}>No tickets</Text>
          </View>
          <Text style={styles.hint}>
            Buses: expected crowding where each one is now. Routes of a selected stop or bus: each stretch this hour;
            their stops: how full arriving buses are.
          </Text>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  box: { padding: 10, width: 196 },
  boxSmall: { width: 168, paddingVertical: 8 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 },
  title: { fontSize: 13, fontWeight: '800', color: C.text },
  strip: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  dot: { width: 14, height: 6, borderRadius: 3 },
  stripText: { fontSize: 10.5, color: C.sub, marginLeft: 2 },
  item: { flexDirection: 'row', alignItems: 'center', marginVertical: 1.5 },
  swatch: { width: 14, height: 6, borderRadius: 3, marginRight: 6 },
  label: { fontSize: 12, color: C.text, fontWeight: '600' },
  range: { fontWeight: '400', color: C.sub },
  hint: { fontSize: 10.5, color: C.sub, marginTop: 4, lineHeight: 14 },
});
