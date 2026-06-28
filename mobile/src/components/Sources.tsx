import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Sym } from './Sym';
import { colors, fonts } from '../theme/tokens';
import type { SourceKind } from '../data/models';

// Each surface → its label, SF Symbol, and color. The chips make the cross-surface
// join legible: you can SEE an inference was stitched from calendar + messages + web.
const SOURCE: Record<SourceKind, { label: string; sf: string; fallback: any; color: string }> = {
  calendar: { label: 'Calendar', sf: 'calendar', fallback: 'calendar-outline', color: colors.cal },
  messages: { label: 'Messages', sf: 'message.fill', fallback: 'chatbubble', color: colors.mail },
  email: { label: 'Email', sf: 'envelope.fill', fallback: 'mail', color: colors.mail },
  web: { label: 'Browsing', sf: 'safari.fill', fallback: 'compass', color: colors.web },
  reading: { label: 'Highlights', sf: 'book.fill', fallback: 'book', color: colors.read },
  docs: { label: 'Docs', sf: 'doc.text.fill', fallback: 'document-text', color: colors.moon2 },
  maps: { label: 'Maps', sf: 'map.fill', fallback: 'map', color: colors.web },
  photos: { label: 'Photos', sf: 'photo.fill', fallback: 'image', color: colors.dawn },
  finance: { label: 'Finance', sf: 'creditcard.fill', fallback: 'card', color: colors.web },
  patterns: { label: 'Your patterns', sf: 'waveform', fallback: 'pulse', color: colors.inkLo },
};

export function Sources({ sources }: { sources: SourceKind[] }) {
  return (
    <View style={styles.wrap}>
      <Text style={styles.lead}>stitched from</Text>
      {sources.map((s) => {
        const m = SOURCE[s];
        return (
          <View key={s} style={styles.chip}>
            <Sym sf={m.sf} fallback={m.fallback} size={12} color={m.color} />
            <Text style={[styles.label, { color: m.color }]}>{m.label}</Text>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 7, marginTop: 14 },
  lead: { fontFamily: fonts.ui, fontSize: 11.5, color: colors.inkLo, marginRight: 1 },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingVertical: 5,
    paddingHorizontal: 9,
    borderRadius: 99,
    backgroundColor: 'rgba(255,255,255,0.06)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.1)',
  },
  label: { fontFamily: fonts.uiSemi, fontSize: 11.5 },
});
