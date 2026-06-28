import React, { useEffect } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import Animated, {
  Easing,
  interpolate,
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
} from 'react-native-reanimated';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import { BlurView } from 'expo-blur';
import { Sym } from './Sym';
import { colors, fonts, radius } from '../theme/tokens';

const DRAWER = Easing.bezier(0.32, 0.72, 0, 1);

// A glass sheet that rises from the bottom and is drag-to-dismissable. When a
// second sheet stacks on top, this one scales back (the iOS card-stack depth).
export function RiseSheet({
  label,
  behind = false,
  onClose,
  heightPct = 0.92,
  children,
}: {
  label: string;
  behind?: boolean;
  onClose: () => void;
  heightPct?: number;
  children: React.ReactNode;
}) {
  const { height } = useWindowDimensions();
  const sheetH = Math.round(height * heightPct);
  const ty = useSharedValue(height);
  const start = useSharedValue(0);
  const depth = useSharedValue(behind ? 1 : 0);

  useEffect(() => {
    ty.value = withTiming(0, { duration: 460, easing: DRAWER });
  }, []);
  useEffect(() => {
    depth.value = withTiming(behind ? 1 : 0, { duration: 320, easing: Easing.out(Easing.cubic) });
  }, [behind]);

  const dismiss = () => {
    ty.value = withTiming(height, { duration: 300, easing: DRAWER }, (finished) => {
      if (finished) runOnJS(onClose)();
    });
  };

  const pan = Gesture.Pan()
    .onStart(() => {
      start.value = ty.value;
    })
    .onUpdate((e) => {
      let n = start.value + e.translationY;
      if (n < 0) n = n * 0.25; // resist dragging up past the top
      ty.value = n;
    })
    .onEnd((e) => {
      if (e.translationY > 120 || e.velocityY > 800) {
        ty.value = withTiming(height, { duration: 300, easing: DRAWER }, (finished) => {
          if (finished) runOnJS(onClose)();
        });
      } else {
        ty.value = withSpring(0, { damping: 20, stiffness: 200 });
      }
    });

  const sheetStyle = useAnimatedStyle(() => ({
    transform: [
      { translateY: ty.value + interpolate(depth.value, [0, 1], [0, -12]) },
      { scale: interpolate(depth.value, [0, 1], [1, 0.94]) },
    ],
  }));
  const dimStyle = useAnimatedStyle(() => ({ opacity: interpolate(depth.value, [0, 1], [0, 0.5]) }));

  return (
    <Animated.View style={[styles.sheet, { height: sheetH }, sheetStyle]}>
      <BlurView intensity={50} tint="dark" blurMethod="dimezisBlurView" style={StyleSheet.absoluteFill} />
      <View style={styles.tint} />
      <GestureDetector gesture={pan}>
        <View style={styles.handle}>
          <View style={styles.grab} />
          <View style={styles.headRow}>
            <Text style={styles.headLbl}>{label}</Text>
            <Pressable hitSlop={10} onPress={dismiss} style={styles.x}>
              <Sym sf="xmark" fallback="close" size={15} color={colors.inkHi} />
            </Pressable>
          </View>
        </View>
      </GestureDetector>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.body}>
        {children}
      </ScrollView>
      <Animated.View pointerEvents="none" style={[StyleSheet.absoluteFill, styles.dim, dimStyle]} />
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    borderTopLeftRadius: radius.sheet,
    borderTopRightRadius: radius.sheet,
    overflow: 'hidden',
  },
  tint: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(17,15,28,0.55)' },
  handle: { paddingTop: 10, paddingHorizontal: 22, paddingBottom: 6 },
  grab: { width: 38, height: 5, borderRadius: 99, backgroundColor: 'rgba(255,255,255,0.28)', alignSelf: 'center', marginBottom: 10 },
  headRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  headLbl: { fontFamily: fonts.uiSemi, fontSize: 13.5, color: colors.inkMid },
  x: {
    width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center',
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.18)', backgroundColor: 'rgba(255,255,255,0.06)',
  },
  body: { padding: 22, paddingBottom: 48 },
  dim: { backgroundColor: '#04030a' },
});
