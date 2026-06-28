import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, {
  Easing,
  interpolate,
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';
import { BlurView } from 'expo-blur';
import { colors } from '../theme/tokens';

interface BlobProps {
  color: string;
  size: number;
  opacity: number;
  dx: number;
  dy: number;
  dur: number;
  delay: number;
  top?: number;
  left?: number;
  right?: number;
  bottom?: number;
}

function Blob({ color, size, opacity, dx, dy, dur, delay, top, left, right, bottom }: BlobProps) {
  const t = useSharedValue(0);
  useEffect(() => {
    t.value = withDelay(
      delay,
      withRepeat(withTiming(1, { duration: dur, easing: Easing.inOut(Easing.ease) }), -1, true),
    );
  }, []);
  const s = useAnimatedStyle(() => ({
    transform: [
      { translateX: interpolate(t.value, [0, 1], [0, dx]) },
      { translateY: interpolate(t.value, [0, 1], [0, dy]) },
      { scale: interpolate(t.value, [0, 1], [1, 1.14]) },
    ],
  }));
  return (
    <Animated.View
      style={[
        { position: 'absolute', width: size, height: size, borderRadius: size / 2, backgroundColor: color, opacity, top, left, right, bottom },
        s,
      ]}
    />
  );
}

// The living substrate: soft colored blobs, blurred into a smooth aurora by the
// BlurView layered on top (RN has no radial-gradient — this is the standard trick).
export function Aurora() {
  return (
    <View style={[StyleSheet.absoluteFill, { backgroundColor: colors.night0, overflow: 'hidden' }]}>
      <Blob color="#7C86FF" size={360} opacity={0.55} left={-70} top={-30} dx={36} dy={40} dur={26000} delay={0} />
      <Blob color="#C9A6FF" size={320} opacity={0.5} right={-80} top={120} dx={-40} dy={30} dur={32000} delay={500} />
      <Blob color="#FF9E73" size={340} opacity={0.4} left={-50} bottom={120} dx={30} dy={-36} dur={30000} delay={1000} />
      <Blob color="#67E0CE" size={280} opacity={0.34} right={-60} bottom={-40} dx={30} dy={-30} dur={36000} delay={300} />
      <BlurView intensity={80} tint="dark" blurMethod="dimezisBlurView" style={StyleSheet.absoluteFill} />
    </View>
  );
}
