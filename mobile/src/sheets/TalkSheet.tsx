import React, { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { Sym } from '../components/Sym';
import { colors, fonts } from '../theme/tokens';
import { sendChat } from '../api/client';
import { greetingWord } from '../data/mock';
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

// The chat surface — wired to the live backend (POST /chat). Messages are local
// state; the conversation id threads the turns so the backend keeps context.
export function TalkSheet() {
  // lazy init so the opener reflects the time the sheet is actually opened
  const [messages, setMessages] = useState<ChatMessage[]>(() => [
    { role: 'nidra', text: `${greetingWord()}. What’s on your mind?` },
  ]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [convId, setConvId] = useState<number | null>(null);

  const onSend = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput('');
    setMessages((m) => [...m, { role: 'me', text }]);
    setSending(true);
    try {
      const { reply, conversationId } = await sendChat(text, convId);
      setConvId(conversationId);
      setMessages((m) => [...m, { role: 'nidra', text: reply }]);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Something went wrong.';
      setMessages((m) => [...m, { role: 'nidra', text: `⚠️ ${msg}` }]);
    } finally {
      setSending(false);
    }
  };

  return (
    <>
      {messages.map((m, i) => (
        <Bubble key={i} m={m} />
      ))}
      {sending ? (
        <View style={[styles.bub, styles.nidra, styles.typing]}>
          <ActivityIndicator color={colors.inkMid} size="small" />
        </View>
      ) : null}
      <View style={styles.composer}>
        <TextInput
          style={styles.field}
          value={input}
          onChangeText={setInput}
          placeholder="Tell me anything…"
          placeholderTextColor={colors.inkLo}
          onSubmitEditing={onSend}
          returnKeyType="send"
          editable={!sending}
          multiline
        />
        <Pressable
          style={({ pressed }) => [styles.send, (pressed || sending) && styles.sendPressed]}
          onPress={onSend}
          disabled={sending}
        >
          <Sym sf="arrow.up" fallback="arrow-up" size={18} color="#160f2e" />
        </Pressable>
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
  typing: { paddingVertical: 14, minWidth: 56, alignItems: 'center' },
  did: { alignSelf: 'flex-start', fontFamily: fonts.uiSemi, fontSize: 12.5, color: colors.web, backgroundColor: 'rgba(127,224,214,0.1)', borderWidth: 1, borderColor: 'rgba(127,224,214,0.25)', paddingVertical: 7, paddingHorizontal: 12, borderRadius: 12, marginBottom: 12, overflow: 'hidden' },
  composer: { flexDirection: 'row', alignItems: 'flex-end', gap: 10, marginTop: 8 },
  field: { flex: 1, fontFamily: fonts.ui, fontSize: 15, lineHeight: 20, maxHeight: 120, color: colors.inkHi, paddingVertical: 13, paddingHorizontal: 18, borderRadius: 24, borderWidth: 1, borderColor: 'rgba(255,255,255,0.14)', backgroundColor: 'rgba(255,255,255,0.05)' },
  send: { width: 46, height: 46, borderRadius: 23, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.moon },
  sendPressed: { transform: [{ scale: 0.92 }], opacity: 0.85 },
});
