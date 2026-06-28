import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';
import { RiseSheet } from './RiseSheet';
import { useSheets } from './SheetContext';
import { WorldSheet } from '../sheets/WorldSheet';
import { TalkSheet } from '../sheets/TalkSheet';
import { details } from '../data/mock';

// Renders the active sheet stack over Home. Each sheet rises + is drag-dismissable;
// the one beneath scales back for depth. Everything is data-driven off `details`,
// except Talk (the chat surface), which has its own composer-shaped layout.
function labelFor(id: string): string {
  if (id === 'talk') return 'Nidra';
  return details[id]?.label ?? '';
}

function heightFor(id: string): number {
  return details[id]?.heightPct ?? 0.92;
}

function content(id: string) {
  if (id === 'talk') return <TalkSheet />;
  const d = details[id];
  return d ? <WorldSheet detail={d} /> : null;
}

export function SheetHost() {
  const { stack, close } = useSheets();
  if (stack.length === 0) return null;
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
