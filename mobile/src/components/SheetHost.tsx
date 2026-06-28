import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';
import { RiseSheet } from './RiseSheet';
import { useSheets } from './SheetContext';
import { useHomeData } from './HomeData';
import { WorldSheet } from '../sheets/WorldSheet';
import { TalkSheet } from '../sheets/TalkSheet';

// Renders the active sheet stack over Home. Each sheet rises + is drag-dismissable;
// the one beneath scales back for depth. World sheets are data-driven off the live
// `details` (from the repository seam); Talk is the chat surface.
export function SheetHost() {
  const { stack, close } = useSheets();
  const { data } = useHomeData();
  const details = data.details;
  if (stack.length === 0) return null;

  const labelFor = (id: string): string => (id === 'talk' ? 'Nidra' : details[id]?.label ?? '');
  const heightFor = (id: string): number => details[id]?.heightPct ?? 0.92;
  const content = (id: string) => {
    if (id === 'talk') return <TalkSheet />;
    const d = details[id];
    return d ? <WorldSheet detail={d} /> : null;
  };

  return (
    <View style={StyleSheet.absoluteFill}>
      <Pressable style={StyleSheet.absoluteFill} onPress={close}>
        <Animated.View entering={FadeIn.duration(280)} style={styles.scrim} />
      </Pressable>
      {stack.map((id, i) => (
        <RiseSheet
          key={`${id}-${i}`}
          label={labelFor(id)}
          behind={i < stack.length - 1}
          onClose={close}
          heightPct={heightFor(id)}
        >
          {content(id)}
        </RiseSheet>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  scrim: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(4,3,9,0.45)' },
});
