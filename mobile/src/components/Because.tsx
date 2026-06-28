import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Sym } from './Sym';
import { colors, fonts } from '../theme/tokens';

// The tiny "why this is here" line under any suggested item — the companion showing
// its reasoning everywhere ("because you searched ramen three times"). It's what
// turns a suggestion into "it knows me." Set in Nidra's voice (Fraunces italic).
export function Because({ children }: { children: React.ReactNode }) {
  return (
    <View style={styles.row}>
      <Sym sf="sparkle" fallback="sparkles" size={10} color={colors.moon2} style={styles.icon} />
      <Text style={styles.text}>{children}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'flex-start', gap: 6, marginTop: 5 },
  icon: { marginTop: 2.5 },
  text: { flex: 1, fontFamily: fonts.voiceItalic, fontSize: 12.5, lineHeight: 17, color: colors.inkLo },
});
