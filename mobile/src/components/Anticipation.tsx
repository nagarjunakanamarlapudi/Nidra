import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Sym } from './Sym';
import { Sources } from './Sources';
import { colors, fonts, radius } from '../theme/tokens';
import type { Anticipation as AnticipationT } from '../data/models';

// The lead of every world sheet: not "here's what I noticed about you" (a mirror),
// but "here's the move" — anticipatory + actionable, shown with where it came from.
// Dawn-accented (warmth / action) to set it apart from the moon-tinted Insight.
export function Anticipation({
  data,
  onPrimary,
  onSecondary,
}: {
  data: AnticipationT;
  onPrimary?: () => void;
  onSecondary?: () => void;
}) {
  return (
    <View style={styles.card}>
      <LinearGradient
        colors={['rgba(255,178,121,0.16)', 'rgba(255,142,110,0.05)'] as const}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={StyleSheet.absoluteFill}
      />
      <View style={styles.kickerRow}>
        <Sym sf="bolt.fill" fallback="flash" size={12} color={colors.dawn} />
        <Text style={styles.kicker}>{data.kicker}</Text>
      </View>
      <Text style={styles.title}>{data.title}</Text>
      <Text style={styles.why}>{data.why}</Text>
      <Sources sources={data.sources} />
      <View style={styles.actions}>
        <Pressable onPress={onPrimary} style={({ pressed }) => [styles.primary, pressed && styles.pressed]}>
          <Text style={styles.primaryText}>{data.primary}</Text>
        </Pressable>
        {data.secondary ? (
          <Pressable onPress={onSecondary} style={({ pressed }) => [styles.secondary, pressed && styles.pressed]}>
            <Text style={styles.secondaryText}>{data.secondary}</Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radius.lg,
    padding: 18,
    marginTop: 18,
    overflow: 'hidden',
    backgroundColor: 'rgba(255,178,121,0.06)',
    borderWidth: 1,
    borderColor: 'rgba(255,178,121,0.34)',
  },
  kickerRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  kicker: { fontFamily: fonts.uiBold, fontSize: 11, letterSpacing: 1, color: colors.dawn },
  title: { fontFamily: fonts.voiceSemi, fontSize: 21, lineHeight: 27, color: colors.inkHi, marginTop: 11 },
  why: { fontFamily: fonts.ui, fontSize: 14, lineHeight: 21, color: colors.inkMid, marginTop: 10 },
  actions: { flexDirection: 'row', gap: 10, marginTop: 18 },
  primary: { flex: 1, paddingVertical: 14, borderRadius: 16, alignItems: 'center', backgroundColor: colors.dawn },
  primaryText: { fontFamily: fonts.uiSemi, fontSize: 14.5, color: '#2a1206' },
  secondary: {
    flex: 1,
    paddingVertical: 14,
    borderRadius: 16,
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.06)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.16)',
  },
  secondaryText: { fontFamily: fonts.uiSemi, fontSize: 14.5, color: colors.inkHi },
  pressed: { transform: [{ scale: 0.97 }], opacity: 0.95 },
});
