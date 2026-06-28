import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Sym } from './Sym';
import { colors, fonts, radius } from '../theme/tokens';
import type { Insight as InsightT } from '../data/models';

export function Note({ children, dim }: { children: React.ReactNode; dim?: boolean }) {
  return <Text style={[styles.note, dim && styles.noteDim]}>{children}</Text>;
}

export function MLabel({ children }: { children: React.ReactNode }) {
  return <Text style={styles.mlabel}>{children}</Text>;
}

export function Persona({ children }: { children: React.ReactNode }) {
  return <Text style={styles.persona}>{children}</Text>;
}

export function Insight({ insight }: { insight: InsightT }) {
  return (
    <View style={styles.insight}>
      <Text style={styles.ik}>{insight.kicker}</Text>
      <Text style={styles.it}>{insight.title}</Text>
      <Text style={styles.iw}>{insight.why}</Text>
    </View>
  );
}

export function Cta({ label, onPress, variant = 'moon' }: { label: string; onPress?: () => void; variant?: 'moon' | 'dawn' }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.cta, variant === 'dawn' ? styles.ctaDawn : styles.ctaMoon, pressed && styles.pressed]}>
      <Text style={[styles.ctaText, variant === 'dawn' ? styles.ctaTextDawn : styles.ctaTextMoon]}>{label}</Text>
    </Pressable>
  );
}

export function AskRow({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.ask, pressed && styles.pressed]}>
      <Sym sf="text.bubble" fallback="chatbubble-outline" size={15} color={colors.inkLo} />
      <Text style={styles.askText}>{label}</Text>
    </Pressable>
  );
}

export function Button({ label, onPress, primary }: { label: string; onPress?: () => void; primary?: boolean }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.btn, primary && styles.btnPrimary, pressed && styles.pressed]}>
      <Text style={[styles.btnText, primary && styles.btnTextPrimary]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  note: { fontFamily: fonts.voice, fontSize: 16, lineHeight: 24, color: colors.inkMid, marginTop: 12 },
  noteDim: { fontSize: 14, color: colors.inkLo },
  mlabel: { fontFamily: fonts.uiSemi, fontSize: 11.5, letterSpacing: 1.4, color: colors.inkLo, marginTop: 24, marginBottom: 12 },
  persona: { fontFamily: fonts.voiceItalic, fontSize: 17, lineHeight: 26, color: colors.inkHi, marginTop: 18, paddingLeft: 15, borderLeftWidth: 2, borderLeftColor: 'rgba(201,166,255,0.5)' },
  insight: { borderRadius: radius.lg, padding: 18, marginTop: 16, backgroundColor: 'rgba(201,166,255,0.14)', borderWidth: 1, borderColor: 'rgba(201,166,255,0.4)' },
  ik: { fontFamily: fonts.uiBold, fontSize: 11, letterSpacing: 1, color: colors.moon },
  it: { fontFamily: fonts.voice, fontSize: 20, lineHeight: 24, color: colors.inkHi, marginTop: 10 },
  iw: { fontFamily: fonts.ui, fontSize: 13.5, lineHeight: 20, color: colors.inkMid, marginTop: 9 },
  cta: { marginTop: 18, paddingVertical: 15, borderRadius: 18, alignItems: 'center' },
  ctaMoon: { backgroundColor: colors.moon },
  ctaDawn: { backgroundColor: colors.dawn },
  ctaText: { fontFamily: fonts.uiSemi, fontSize: 15 },
  ctaTextMoon: { color: '#160f2e' },
  ctaTextDawn: { color: '#2a1206' },
  ask: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 18, paddingVertical: 13, paddingHorizontal: 16, borderRadius: 24, backgroundColor: 'rgba(255,255,255,0.06)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.14)' },
  askText: { fontFamily: fonts.ui, fontSize: 14.5, color: colors.inkLo },
  btn: { flex: 1, paddingVertical: 13, borderRadius: 15, alignItems: 'center', backgroundColor: 'rgba(255,255,255,0.08)' },
  btnPrimary: { backgroundColor: colors.dawn },
  btnText: { fontFamily: fonts.uiSemi, fontSize: 14.5, color: colors.inkHi },
  btnTextPrimary: { color: '#2a1206' },
  pressed: { transform: [{ scale: 0.97 }], opacity: 0.95 },
});
