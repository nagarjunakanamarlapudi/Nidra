import React from 'react';
import { StyleSheet, View, type ViewStyle } from 'react-native';
import { BlurView } from 'expo-blur';

// Liquid glass: blur + translucent fill + a faint top highlight. Used by the
// chat FAB; sheets build their own (heavier) glass for legibility.
export function GlassView({
  children,
  style,
  intensity = 40,
}: {
  children?: React.ReactNode;
  style?: ViewStyle | ViewStyle[];
  intensity?: number;
}) {
  return (
    <View style={[styles.base, style]}>
      <BlurView intensity={intensity} tint="dark" blurMethod="dimezisBlurView" style={StyleSheet.absoluteFill} />
      <View style={styles.fill} />
      <View style={styles.highlight} />
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  base: { overflow: 'hidden' },
  fill: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(255,255,255,0.12)' },
  highlight: { position: 'absolute', top: 0, left: 0, right: 0, height: 1, backgroundColor: 'rgba(255,255,255,0.4)' },
});
