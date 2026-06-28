import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Sources } from './Sources';
import { colors, fonts } from '../theme/tokens';
import type { TripDecision as TripDecisionT } from '../data/models';

// C1 · "Nidra speaks." The anticipatory call still LEADS the sheet, but it's framed
// as the companion talking (Fraunces, no container, no amber alarm) — a dawn primary
// action and a quiet alternative. The decision, not a dashboard, is the first thing.
export function TripDecision({
  data,
  onPrimary,
  onSecondary,
}: {
  data: TripDecisionT;
  onPrimary?: () => void;
  onSecondary?: () => void;
}) {
  return (
    <View style={styles.wrap}>
      <Text style={styles.speak}>{data.text}</Text>
      <View style={styles.actions}>
        <Pressable onPress={onPrimary} style={({ pressed }) => [styles.primary, pressed && styles.pressed]}>
          <Text style={styles.primaryText}>{data.primary}</Text>
        </Pressable>
        {data.secondary ? (
          <Pressable onPress={onSecondary} style={({ pressed }) => [styles.ghost, pressed && styles.ghostPressed]}>
            <Text style={styles.ghostText}>{data.secondary}</Text>
          </Pressable>
        ) : null}
      </View>
      <Sources sources={data.sources} />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginTop: 18 },
  speak: { fontFamily: fonts.voice, fontSize: 17, lineHeight: 26, color: colors.inkHi },
  actions: { flexDirection: 'row', alignItems: 'center', gap: 18, marginTop: 16 },
  primary: { paddingVertical: 12, paddingHorizontal: 20, borderRadius: 13, backgroundColor: colors.dawn },
  primaryText: { fontFamily: fonts.uiSemi, fontSize: 14, color: '#2a1206' },
  ghost: { paddingVertical: 6 },
  ghostText: { fontFamily: fonts.uiSemi, fontSize: 14, color: colors.inkLo },
  pressed: { transform: [{ scale: 0.97 }], opacity: 0.95 },
  ghostPressed: { opacity: 0.6 },
});
