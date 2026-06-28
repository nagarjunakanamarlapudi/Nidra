import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Aurora } from '../components/Aurora';
import { WorldTile } from '../components/WorldTile';
import { ChatFab } from '../components/ChatFab';
import { useSheets } from '../components/SheetContext';
import { useHomeData } from '../components/HomeData';
import { colors, fonts, radius } from '../theme/tokens';

// Placeholder layout shown for the brief moment the live feed is loading — same
// rhythm as the real grid (one full tile, then halves) so nothing jumps.
const SKELETON = ['full', 'half', 'half', 'half', 'half'] as const;

// The glass playground: your worlds floating over a living aurora.
export default function Home() {
  const insets = useSafeAreaInsets();
  const { open } = useSheets();
  const { status, data } = useHomeData();
  const { greeting, worlds } = data;
  return (
    <View style={styles.root}>
      <Aurora />
      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{ paddingTop: insets.top + 18, paddingHorizontal: 18, paddingBottom: 150 }}
      >
        <View style={styles.presence}>
          <Text style={styles.hello}>{greeting.hello}</Text>
          <Text style={styles.note}>{greeting.note}</Text>
        </View>
        <Text style={styles.canvasLabel}>ON YOUR MIND LATELY</Text>
        <View style={styles.canvas}>
          {status === 'loading'
            ? SKELETON.map((s, i) => (
                <View key={i} style={[s === 'full' ? styles.skelFull : styles.skelHalf, styles.skel]} />
              ))
            : worlds.map((w, i) => <WorldTile key={w.key} world={w} delay={i * 220} />)}
        </View>
      </ScrollView>
      <ChatFab onPress={() => open('talk')} bottom={insets.bottom + 22} />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.night0 },
  presence: { paddingHorizontal: 6 },
  hello: { fontFamily: fonts.voice, fontSize: 32, lineHeight: 34, color: colors.inkHi },
  note: { fontFamily: fonts.voice, fontSize: 16, lineHeight: 24, color: colors.inkMid, marginTop: 9 },
  canvasLabel: { fontFamily: fonts.uiSemi, fontSize: 11.5, letterSpacing: 1.6, color: colors.inkLo, marginTop: 26, marginBottom: 14, marginHorizontal: 6 },
  canvas: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between' },
  skel: { backgroundColor: 'rgba(255,255,255,0.05)', borderRadius: radius.card, marginBottom: 11 },
  skelFull: { width: '100%', height: 158 },
  skelHalf: { width: '48.5%', height: 128 },
});
