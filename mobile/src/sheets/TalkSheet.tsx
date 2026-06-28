import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Sym } from '../components/Sym';
import { colors, fonts } from '../theme/tokens';
import { talk } from '../data/mock';
import type { ChatMessage } from '../data/models';

function Bubble({ m }: { m: ChatMessage }) {
  if (m.role === 'did') return <Text style={styles.did}>{m.text}</Text>;
  const me = m.role === 'me';
  return (
    <View style={[styles.bub, me ? styles.me : styles.nidra]}>
      <Text style={me ? styles.meText : styles.nidraText}>{m.text}</Text>
    </View>
  );
}

export function TalkSheet() {
  return (
    <>
      {talk.map((m, i) => (
        <Bubble key={i} m={m} />
      ))}
      <View style={styles.composer}>
        <Text style={styles.field}>Tell me anything…</Text>
        <View style={styles.mic}>
          <Sym sf="mic.fill" fallback="mic" size={18} color="#160f2e" />
        </View>
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  bub: { maxWidth: '84%', paddingVertical: 13, paddingHorizontal: 16, marginBottom: 12 },
  nidra: { alignSelf: 'flex-start', backgroundColor: 'rgba(255,255,255,0.08)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)', borderRadius: 20, borderBottomLeftRadius: 6 },
  me: { alignSelf: 'flex-end', backgroundColor: colors.dawn, borderRadius: 20, borderBottomRightRadius: 6 },
  nidraText: { fontFamily: fonts.voice, fontSize: 15, lineHeight: 22, color: colors.inkHi },
  meText: { fontFamily: fonts.uiMed, fontSize: 15, lineHeight: 22, color: '#2a1206' },
  did: { alignSelf: 'flex-start', fontFamily: fonts.uiSemi, fontSize: 12.5, color: colors.web, backgroundColor: 'rgba(127,224,214,0.1)', borderWidth: 1, borderColor: 'rgba(127,224,214,0.25)', paddingVertical: 7, paddingHorizontal: 12, borderRadius: 12, marginBottom: 12, overflow: 'hidden' },
  composer: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 8 },
  field: { flex: 1, fontFamily: fonts.ui, fontSize: 15, color: colors.inkLo, paddingVertical: 13, paddingHorizontal: 18, borderRadius: 24, borderWidth: 1, borderColor: 'rgba(255,255,255,0.14)', backgroundColor: 'rgba(255,255,255,0.05)', overflow: 'hidden' },
  mic: { width: 46, height: 46, borderRadius: 23, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.moon },
});
