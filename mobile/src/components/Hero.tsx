import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { Sym } from './Sym';
import { colors, fonts } from '../theme/tokens';

// A photo header with the title set over it (used at the top of sheets/details).
// `badge` is an optional top-right chip (the trip uses it for a flight countdown).
export function Hero({
  image,
  kicker,
  title,
  height = 172,
  titleSize = 28,
  badge,
}: {
  image: string;
  kicker: string;
  title: string;
  height?: number;
  titleSize?: number;
  badge?: string;
}) {
  return (
    <View style={[styles.hero, { height }]}>
      <Image source={{ uri: image }} style={StyleSheet.absoluteFill} contentFit="cover" transition={300} />
      <LinearGradient colors={['transparent', 'rgba(7,5,14,0.85)'] as const} style={StyleSheet.absoluteFill} />
      {badge ? (
        <View style={styles.badge}>
          <Sym sf="airplane" fallback="airplane" size={11} color="#fff" />
          <Text style={styles.badgeText}>{badge}</Text>
        </View>
      ) : null}
      <View style={styles.cap}>
        <Text style={styles.kicker}>{kicker}</Text>
        <Text style={[styles.title, { fontSize: titleSize, lineHeight: titleSize + 2 }]}>{title}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  hero: { borderRadius: 24, overflow: 'hidden', backgroundColor: '#2a2440' },
  badge: {
    position: 'absolute',
    top: 13,
    right: 13,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingVertical: 6,
    paddingHorizontal: 11,
    borderRadius: 99,
    backgroundColor: 'rgba(7,5,14,0.5)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.2)',
  },
  badgeText: { fontFamily: fonts.uiSemi, fontSize: 12, color: '#fff' },
  cap: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, padding: 16, justifyContent: 'flex-end' },
  kicker: { fontFamily: fonts.uiSemi, fontSize: 12, letterSpacing: 0.5, color: 'rgba(255,255,255,0.9)', textShadowColor: 'rgba(0,0,0,0.6)', textShadowOffset: { width: 0, height: 1 }, textShadowRadius: 8 },
  title: { fontFamily: fonts.voice, color: '#fff', marginTop: 6, textShadowColor: 'rgba(0,0,0,0.5)', textShadowOffset: { width: 0, height: 2 }, textShadowRadius: 14 },
});
