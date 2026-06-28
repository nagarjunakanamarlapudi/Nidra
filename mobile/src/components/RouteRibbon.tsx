import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Sym } from './Sym';
import { colors, fonts } from '../theme/tokens';
import type { TripRoute } from '../data/models';

// The route ribbon — a schematic of the journey that makes the geometry self-evident.
// The skipped place (Hakone) hangs off the line as a struck spur, so WHY the decision
// up top makes sense is visible at a glance: Tokyo → Kyoto is one clean hop.
export function RouteRibbon({ data }: { data: TripRoute }) {
  const { cities, leg, skip } = data;
  const first = cities[0];
  const last = cities[cities.length - 1];
  return (
    <View style={styles.ribbon}>
      <LinearGradient
        colors={['rgba(255,255,255,0.10)', 'rgba(255,255,255,0.03)'] as const}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={StyleSheet.absoluteFill}
      />
      <Text style={styles.label}>THE ROUTE</Text>

      <View style={styles.main}>
        <Text style={styles.city}>{first}</Text>
        <View style={styles.dot} />
        <LinearGradient colors={[colors.dawn, colors.moon] as const} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={styles.line} />
        <View style={styles.dot} />
        <Text style={styles.city}>{last}</Text>
      </View>
      {leg ? <Text style={styles.leg}>{leg}</Text> : null}

      {skip ? (
        <View style={styles.spur}>
          <View style={styles.x}>
            <Sym sf="xmark" fallback="close" size={9} color={colors.dawn} />
          </View>
          <Text style={styles.spurText}>
            <Text style={styles.spurBold}>{skip.place}</Text> — {skip.note}
          </Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  ribbon: {
    borderRadius: 22,
    padding: 17,
    marginTop: 18,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.18)',
    backgroundColor: 'rgba(255,255,255,0.02)',
  },
  label: { fontFamily: fonts.uiBold, fontSize: 11, letterSpacing: 1.4, color: colors.inkLo },
  main: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 16 },
  city: { fontFamily: fonts.voiceSemi, fontSize: 16, color: colors.inkHi },
  dot: { width: 11, height: 11, borderRadius: 5.5, backgroundColor: colors.dawn },
  line: { flex: 1, height: 2, borderRadius: 2, marginHorizontal: 2 },
  leg: { fontFamily: fonts.uiMed, fontSize: 11, color: colors.inkMid, textAlign: 'center', marginTop: 7 },
  spur: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
    marginTop: 15,
    paddingTop: 14,
    borderTopWidth: 1,
    borderTopColor: 'rgba(255,255,255,0.12)',
  },
  x: { width: 20, height: 20, borderRadius: 10, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: 'rgba(255,178,121,0.55)' },
  spurText: { flex: 1, fontFamily: fonts.ui, fontSize: 12.5, color: colors.dawn },
  spurBold: { fontFamily: fonts.uiSemi, color: '#fff' },
});
