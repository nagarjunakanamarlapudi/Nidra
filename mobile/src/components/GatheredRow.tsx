import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Image } from 'expo-image';
import { Sym } from './Sym';
import { colors, fonts } from '../theme/tokens';
import type { GatheredItem } from '../data/models';

// One "what I've gathered" row: thumbnail (emoji fallback) + name + Nidra's line.
export function GatheredRow({ item, onPress }: { item: GatheredItem; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.row, pressed && styles.pressed]}>
      <View style={styles.thumb}>
        <Text style={styles.emoji}>{item.glyph}</Text>
        <Image source={{ uri: item.image }} style={StyleSheet.absoluteFill} contentFit="cover" transition={200} />
      </View>
      <View style={styles.grow}>
        <Text style={styles.name}>{item.name}</Text>
        <Text style={styles.say}>{item.say}</Text>
      </View>
      <Sym sf="chevron.right" fallback="chevron-forward" size={14} color={colors.inkLo} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 13, padding: 14, marginBottom: 10, borderRadius: 20, backgroundColor: 'rgba(255,255,255,0.06)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.08)' },
  pressed: { transform: [{ scale: 0.985 }], backgroundColor: 'rgba(255,255,255,0.1)' },
  thumb: { width: 46, height: 46, borderRadius: 13, overflow: 'hidden', alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(255,255,255,0.06)' },
  emoji: { fontSize: 20 },
  grow: { flex: 1, minWidth: 0 },
  name: { fontFamily: fonts.uiSemi, fontSize: 15, color: colors.inkHi },
  say: { fontFamily: fonts.voiceR, fontSize: 13.5, color: colors.inkMid, marginTop: 3 },
});
