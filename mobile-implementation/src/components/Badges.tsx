import { StyleSheet, Text, View } from 'react-native';
import { LEVEL_COLORS, LEVEL_LABEL, NO_DATA_COLOR } from '../logic/crowding';
import type { LevelName } from '../types';
import { C } from './theme';

export function LevelBadge({ level }: { level: LevelName | null }) {
  const background = level ? LEVEL_COLORS[level] : NO_DATA_COLOR;
  return (
    <View style={[styles.badge, { backgroundColor: background }]}>
      <Text style={[styles.badgeText, { color: level === 'Medium' ? C.text : '#fff' }]}>
        {level ? LEVEL_LABEL[level] : 'No data'}
      </Text>
    </View>
  );
}

export function RouteChip({ number, color }: { number: string; color: string }) {
  return (
    <View style={[styles.chip, { backgroundColor: color }]}>
      <Text style={styles.chipText} numberOfLines={1}>
        {number}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: { borderRadius: 10, paddingHorizontal: 8, paddingVertical: 3, alignSelf: 'flex-start' },
  badgeText: { fontSize: 12, fontWeight: '700' },
  chip: { borderRadius: 8, paddingHorizontal: 7, paddingVertical: 3, minWidth: 40, maxWidth: 110, alignItems: 'center' },
  chipText: { color: '#fff', fontWeight: '800', fontSize: 13 },
});
