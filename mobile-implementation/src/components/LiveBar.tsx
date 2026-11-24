import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { fmtAge, istSeconds } from '../logic/live';
import { fmtTime } from '../logic/time';
import { useNow, type LiveStatus } from '../live/useLiveFeed';
import { C } from './theme';

const RED = '#d93025';

function statusLine(status: LiveStatus, phoneNow: number): { text: string; error: boolean } {
  if (status.state === 'ok') {
    const p = status.payload;
    const feedAge = phoneNow + status.offset - p.feed_time;
    return {
      text: `${p.stats.vehicles.toLocaleString()} buses · feed published ${fmtAge(feedAge)} ago · new every ~25 s`,
      error: false,
    };
  }
  if (status.state === 'error') return { text: `Server not reachable (${status.message}). Tap for help`, error: true };
  return { text: 'Connecting to the server…', error: false };
}

/** Delhi clock + live feed status; tap for the server address and feed details. */
export function LiveBar({ status, onInfo }: { status: LiveStatus; onInfo(): void }) {
  const phoneNow = useNow(true);
  const offset = status.state === 'connecting' ? 0 : status.offset;
  const { text, error } = statusLine(status, phoneNow);
  return (
    <Pressable onPress={onInfo} style={styles.wrap} accessibilityRole="button" accessibilityLabel="Live data details">
      <View style={styles.row}>
        <View style={[styles.badge, error && styles.badgeError]}>
          <MaterialIcons name={error ? 'wifi-off' : 'fiber-manual-record'} size={12} color="#fff" />
          <Text style={styles.badgeText}>LIVE</Text>
        </View>
        <View style={styles.texts}>
          <Text style={styles.clock}>
            {fmtTime(istSeconds(phoneNow + offset))} <Text style={styles.caption}>IST · real GPS positions</Text>
          </Text>
          <Text style={[styles.caption, error && styles.errorText]} numberOfLines={2}>
            {text}
          </Text>
        </View>
        <MaterialIcons name="info-outline" size={20} color={C.sub} />
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  wrap: {
    backgroundColor: '#fff',
    paddingHorizontal: 12,
    paddingTop: 8,
    paddingBottom: 10,
    borderTopWidth: 1,
    borderColor: C.line,
  },
  row: { flexDirection: 'row', alignItems: 'center' },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    backgroundColor: RED,
    borderRadius: 12,
    paddingHorizontal: 8,
    paddingVertical: 5,
  },
  badgeError: { backgroundColor: C.sub },
  badgeText: { color: '#fff', fontWeight: '800', fontSize: 12 },
  texts: { flex: 1, marginHorizontal: 10 },
  clock: { fontSize: 18, fontWeight: '800', color: C.text },
  caption: { fontSize: 11, fontWeight: '400', color: C.sub },
  errorText: { color: RED },
});
