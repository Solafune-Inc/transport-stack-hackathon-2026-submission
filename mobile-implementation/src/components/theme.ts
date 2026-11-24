import { StyleSheet } from 'react-native';

export const C = {
  text: '#202124',
  sub: '#5f6368',
  line: '#dadce0',
  chip: '#f1f3f4',
  blue: '#1a73e8',
  blueSoft: '#e8f0fe',
  blueDark: '#174ea6',
  tip: '#fef7e0',
};

export const ui = StyleSheet.create({
  card: {
    backgroundColor: '#fff',
    borderRadius: 16,
    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.18)',
  },
  row: { flexDirection: 'row', alignItems: 'center' },
  section: { fontSize: 13, fontWeight: '700', color: C.text, marginTop: 12, marginBottom: 4 },
  body: { fontSize: 14, color: C.text, lineHeight: 20 },
  note: { fontSize: 12, color: C.sub, lineHeight: 17, marginTop: 6 },
  link: { fontSize: 14, color: C.blue, fontWeight: '600', paddingVertical: 8 },
});
