import { Pressable, StyleSheet, Text, View } from 'react-native';
import { C } from './theme';

interface Props {
  values: number[];
  colors: string[];
  current: number;
  height?: number;
  /** draw a dashed reference line at this value (e.g. occupancy 1.0 = capacity) */
  refLine?: number;
  onPick?(hour: number): void;
}

/** 24 bars, one per hour of the day; tap a bar to jump the map to that hour. */
export function HourChart({ values, colors, current, height = 64, refLine, onPick }: Props) {
  const max = Math.max(refLine ? refLine * 1.2 : 0, ...values, 1e-9);
  return (
    <View>
      <View style={[styles.bars, { height }]}>
        {refLine !== undefined && (
          <View style={[styles.ref, { bottom: (refLine / max) * height }]} pointerEvents="none" />
        )}
        {values.map((v, h) => (
          <Pressable
            key={h}
            style={styles.col}
            onPress={() => onPick?.(h)}
            accessibilityLabel={`${h}:00`}
          >
            <View
              style={[
                styles.bar,
                { height: Math.max(2, (v / max) * height), backgroundColor: colors[h] },
                h === current && styles.current,
              ]}
            />
          </Pressable>
        ))}
      </View>
      <View style={styles.axis}>
        {['00', '06', '12', '18', '23'].map((h) => (
          <Text key={h} style={styles.tick}>
            {h}
          </Text>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  bars: { flexDirection: 'row', alignItems: 'flex-end', marginTop: 6 },
  col: { flex: 1, height: '100%', justifyContent: 'flex-end', paddingHorizontal: 1 },
  bar: { borderTopLeftRadius: 2, borderTopRightRadius: 2 },
  current: { borderWidth: 2, borderColor: C.text },
  ref: { position: 'absolute', left: 0, right: 0, borderTopWidth: 1, borderColor: C.sub, borderStyle: 'dashed' },
  axis: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 2 },
  tick: { fontSize: 10, color: C.sub },
});
