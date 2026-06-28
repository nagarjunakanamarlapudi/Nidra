import React, { useEffect } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import Animated, {
  Easing,
  interpolate,
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { fonts, photoScrim, radius, worldGrades } from '../theme/tokens';
import type { World } from '../data/models';
import { useSheets } from './SheetContext';

// A floating, photo-forward "world" — picture with text on top, borderless, that
// rises a sheet when tapped.
export function WorldTile({ world, delay }: { world: World; delay: number }) {
  const { open } = useSheets();
  const bob = useSharedValue(0);
  useEffect(() => {
    bob.value = withDelay(
      delay,
      withRepeat(withTiming(1, { duration: 7000, easing: Easing.inOut(Easing.ease) }), -1, true),
    );
  }, []);
  const bobStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: interpolate(bob.value, [0, 1], [0, -7]) }],
  }));

  const grade = worldGrades[world.grade];
  const height = world.size === 'full' ? 158 : world.tall ? 150 : 128;

  return (
    <Animated.View style={[world.size === 'full' ? styles.full : styles.half, bobStyle]}>
      <Pressable onPress={() => open(world.opens)} style={({ pressed }) => [styles.card, { height }, pressed && styles.pressed]}>
        <LinearGradient colors={grade} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={StyleSheet.absoluteFill} />
        <Image source={{ uri: world.image }} style={StyleSheet.absoluteFill} contentFit="cover" transition={300} />
        <LinearGradient colors={photoScrim} locations={[0, 0.35, 1]} style={StyleSheet.absoluteFill} />
        {world.spark ? <View style={[styles.spark, { backgroundColor: world.spark, shadowColor: world.spark }]} /> : null}
        <View style={styles.content}>
          <Text style={styles.glyph}>{world.glyph}</Text>
          <View>
            <Text style={styles.name}>{world.name}</Text>
            {world.sub ? <Text style={styles.sub}>{world.sub}</Text> : null}
          </View>
        </View>
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  full: { width: '100%', marginBottom: 11 },
  half: { width: '48.5%', marginBottom: 11 },
  card: {
    borderRadius: radius.card,
    overflow: 'hidden',
    backgroundColor: '#23203a',
    shadowColor: '#000',
    shadowOpacity: 0.4,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 10 },
  },
  pressed: { transform: [{ scale: 0.965 }] },
  content: { flex: 1, padding: 15, justifyContent: 'space-between' },
  glyph: { fontSize: 24, textShadowColor: 'rgba(0,0,0,0.5)', textShadowOffset: { width: 0, height: 2 }, textShadowRadius: 6 },
  name: { fontFamily: fonts.uiSemi, fontSize: 16, color: '#fff', textShadowColor: 'rgba(0,0,0,0.55)', textShadowOffset: { width: 0, height: 1 }, textShadowRadius: 10 },
  sub: { fontFamily: fonts.voiceR, fontSize: 13, color: 'rgba(255,255,255,0.86)', marginTop: 2, textShadowColor: 'rgba(0,0,0,0.6)', textShadowOffset: { width: 0, height: 1 }, textShadowRadius: 8 },
  spark: { position: 'absolute', top: 14, right: 16, width: 8, height: 8, borderRadius: 4, shadowOpacity: 0.9, shadowRadius: 6, shadowOffset: { width: 0, height: 0 } },
});
