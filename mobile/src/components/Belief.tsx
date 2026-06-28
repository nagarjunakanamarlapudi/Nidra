import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { colors, fonts } from '../theme/tokens';
import type { Belief as BeliefT } from '../data/models';

// A belief — either plain, or a "revised tonight" diff (old struck-through → new).
// Companion voice: confidence is language ("I'm fairly sure"), never a percent.
export function Belief({ belief }: { belief: BeliefT }) {
  return (
    <View style={styles.card}>
      {belief.newText ? (
        <>
          <Text style={styles.rev}>↻ I CHANGED MY MIND</Text>
          <Text style={styles.old}>{belief.oldText}</Text>
          <Text style={styles.new}>{belief.newText}</Text>
        </>
      ) : (
        <Text style={styles.text}>{belief.text}</Text>
      )}
      <Text style={styles.sure}>{belief.sure}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { padding: 15, marginBottom: 10, borderRadius: 20, backgroundColor: 'rgba(255,255,255,0.05)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.08)' },
  rev: { fontFamily: fonts.uiBold, fontSize: 10.5, letterSpacing: 1, color: colors.moon, marginBottom: 8 },
  old: { fontFamily: fonts.voiceR, fontSize: 14.5, color: colors.inkLo, textDecorationLine: 'line-through' },
  new: { fontFamily: fonts.voice, fontSize: 17, lineHeight: 22, color: colors.inkHi, marginTop: 3 },
  text: { fontFamily: fonts.voice, fontSize: 17, lineHeight: 22, color: colors.inkHi },
  sure: { fontFamily: fonts.ui, fontSize: 12.5, color: colors.inkLo, marginTop: 9 },
});
