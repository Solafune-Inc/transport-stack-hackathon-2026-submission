import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { MapMode } from '../types';
import { C } from './theme';

const ITEMS: { mode: MapMode; icon: 'directions-bus' | 'groups'; label: string }[] = [
  { mode: 'routes', icon: 'directions-bus', label: 'Bus Routes' },
  { mode: 'crowding', icon: 'groups', label: 'Crowding' },
];

export function BottomNav({ mode, onChange, bottomInset }: {
  mode: MapMode;
  onChange(mode: MapMode): void;
  bottomInset: number;
}) {
  return (
    <View style={[styles.bar, { paddingBottom: Math.max(bottomInset, 8) }]} accessibilityRole="tablist">
      {ITEMS.map((item) => {
        const active = item.mode === mode;
        return (
          <Pressable
            key={item.mode}
            onPress={() => onChange(item.mode)}
            style={styles.item}
            accessibilityRole="tab"
            accessibilityState={{ selected: active }}
          >
            <View style={[styles.pill, active && styles.pillActive]}>
              <MaterialIcons name={item.icon} size={24} color={active ? C.blueDark : C.sub} />
            </View>
            <Text style={[styles.label, active && styles.labelActive]}>{item.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: { flexDirection: 'row', backgroundColor: '#fff', paddingTop: 6 },
  item: { flex: 1, alignItems: 'center' },
  pill: { paddingHorizontal: 20, paddingVertical: 4, borderRadius: 16 },
  pillActive: { backgroundColor: C.blueSoft },
  label: { fontSize: 12, marginTop: 2, color: C.sub, fontWeight: '600' },
  labelActive: { color: C.blueDark },
});
