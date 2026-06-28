import React from 'react';
import { Pressable, StyleSheet } from 'react-native';
import { Sym } from './Sym';
import { colors } from '../theme/tokens';
import { GlassView } from './GlassView';

// The single, minimal talk affordance (replaces the old bottom dock).
export function ChatFab({ onPress, bottom }: { onPress: () => void; bottom: number }) {
  return (
    <Pressable onPress={onPress} hitSlop={12} style={({ pressed }) => [styles.wrap, { bottom }, pressed && styles.pressed]}>
      <GlassView intensity={45} style={styles.glass}>
        <Sym sf="bubble.left.and.bubble.right.fill" fallback="chatbubble-ellipses-outline" size={24} color={colors.inkHi} />
      </GlassView>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  wrap: { position: 'absolute', width: 60, height: 60, left: '50%', marginLeft: -30 },
  pressed: { transform: [{ scale: 0.92 }] },
  glass: { width: 60, height: 60, borderRadius: 30, alignItems: 'center', justifyContent: 'center', shadowColor: '#000', shadowOpacity: 0.5, shadowRadius: 18, shadowOffset: { width: 0, height: 12 } },
});
