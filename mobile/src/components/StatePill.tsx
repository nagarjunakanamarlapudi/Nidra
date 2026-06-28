import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Sym } from './Sym';
import { colors, fonts } from '../theme/tokens';
import type { TripState } from '../data/models';

// The per-item status pill — one small, consistent system across the trip template.
// verified/pick carry an SF Symbol (we never hand-draw glyphs); book/saved are text.
const STATE: Record<
  TripState,
  { label: string; color: string; bg: string; border: string; dashed?: boolean; sf?: string; fb?: any }
> = {
  verified: { label: 'verified', color: colors.web, bg: 'rgba(127,224,214,0.13)', border: 'rgba(127,224,214,0.32)', sf: 'checkmark', fb: 'checkmark' },
  pick: { label: 'my pick', color: colors.dawn, bg: 'rgba(255,178,121,0.14)', border: 'rgba(255,178,121,0.34)', sf: 'star.fill', fb: 'star' },
  book: { label: 'to book', color: '#FFC27A', bg: 'transparent', border: 'rgba(255,194,122,0.5)', dashed: true },
  saved: { label: 'saved', color: colors.inkMid, bg: 'rgba(255,255,255,0.07)', border: 'rgba(255,255,255,0.13)' },
};

export function StatePill({ kind, label }: { kind: TripState; label?: string }) {
  const s = STATE[kind];
  return (
    <View style={[styles.pill, { backgroundColor: s.bg, borderColor: s.border, borderStyle: s.dashed ? 'dashed' : 'solid' }]}>
      {s.sf ? <Sym sf={s.sf} fallback={s.fb} size={9.5} color={s.color} /> : null}
      <Text style={[styles.text, { color: s.color }]}>{label ?? s.label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    alignSelf: 'flex-start',
    paddingVertical: 4,
    paddingHorizontal: 9,
    borderRadius: 8,
    borderWidth: 1,
  },
  text: { fontFamily: fonts.uiSemi, fontSize: 10.5 },
});
