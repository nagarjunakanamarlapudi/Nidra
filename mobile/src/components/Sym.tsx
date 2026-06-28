import React from 'react';
import { Platform, type StyleProp, type ViewStyle } from 'react-native';
import { SymbolView, type SymbolViewProps } from 'expo-symbols';
import { Ionicons } from '@expo/vector-icons';

type IoniconName = React.ComponentProps<typeof Ionicons>['name'];

// Apple's official iconography (SF Symbols) on iOS; Ionicons as the Android/web
// fallback. We never hand-draw glyphs — functional icons come from SF Symbols.
export function Sym({
  sf,
  fallback,
  size = 22,
  color,
  weight = 'medium',
  style,
}: {
  sf: string; // SF Symbol name, e.g. "chevron.right"
  fallback: IoniconName; // Ionicons name used off-iOS
  size?: number;
  color?: string;
  weight?: SymbolViewProps['weight'];
  style?: StyleProp<ViewStyle>;
}) {
  if (Platform.OS === 'ios') {
    return (
      <SymbolView
        name={sf as SymbolViewProps['name']}
        size={size}
        tintColor={color}
        weight={weight}
        resizeMode="scaleAspectFit"
        style={[{ width: size, height: size }, style]}
      />
    );
  }
  return <Ionicons name={fallback} size={size} color={color} style={style} />;
}
