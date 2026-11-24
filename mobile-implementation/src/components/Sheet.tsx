import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import type { ReactNode } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { C, ui } from './theme';

export function Sheet({ title, subtitle, accent, onClose, children }: {
  title: string;
  subtitle?: string;
  accent?: string;
  onClose(): void;
  children: ReactNode;
}) {
  return (
    <View style={[ui.card, styles.sheet]}>
      <View style={styles.header}>
        {accent ? <View style={[styles.accent, { backgroundColor: accent }]} /> : null}
        <View style={styles.titles}>
          <Text style={styles.title}>{title}</Text>
          {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
        </View>
        <Pressable onPress={onClose} hitSlop={12} accessibilityRole="button" accessibilityLabel="Close">
          <MaterialIcons name="close" size={22} color={C.sub} />
        </Pressable>
      </View>
      <ScrollView style={styles.body} contentContainerStyle={styles.content}>
        {children}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  sheet: { paddingTop: 12, paddingHorizontal: 14, flexShrink: 1 },
  header: { flexDirection: 'row', alignItems: 'flex-start' },
  accent: { width: 5, alignSelf: 'stretch', borderRadius: 3, marginRight: 10 },
  titles: { flex: 1, marginRight: 8 },
  title: { fontSize: 17, fontWeight: '800', color: C.text },
  subtitle: { fontSize: 13, color: C.sub, marginTop: 2 },
  body: { marginTop: 4, flexGrow: 0, flexShrink: 1 },
  content: { paddingBottom: 12 },
});
