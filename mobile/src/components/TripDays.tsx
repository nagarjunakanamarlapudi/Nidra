import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Image } from 'expo-image';
import { Sym } from './Sym';
import { Because } from './Because';
import { StatePill } from './StatePill';
import { colors, fonts } from '../theme/tokens';
import type { SheetId, TripStop, TripThing } from '../data/models';

const THUMB = 62;

// The itinerary body: compact photo day-cards joined by short travel-time connectors.
// Photos carry the "trip" feeling; each item shows its state pill + "because" so the
// plan reads as vetted, not generated. The leg between cards keeps the geometry honest.
export function TripDays({ stops, onOpen }: { stops: TripStop[]; onOpen: (id: SheetId) => void }) {
  return (
    <View style={styles.wrap}>
      {stops.map((s, i) => (
        <React.Fragment key={i}>
          <Stop stop={s} onOpen={onOpen} />
          {i < stops.length - 1 ? <Connector leg={s.leg} /> : null}
        </React.Fragment>
      ))}
    </View>
  );
}

function Stop({ stop, onOpen }: { stop: TripStop; onOpen: (id: SheetId) => void }) {
  return (
    <View style={styles.stop}>
      <View style={styles.thumb}>
        {stop.glyph ? <Text style={styles.emoji}>{stop.glyph}</Text> : null}
        {stop.image ? (
          <Image source={{ uri: stop.image }} style={StyleSheet.absoluteFill} contentFit="cover" transition={200} />
        ) : null}
      </View>
      <View style={styles.info}>
        <Text style={styles.when}>{stop.when}</Text>
        <Text style={styles.place}>{stop.place}</Text>
        {stop.things?.map((t, i) => (
          <Thing key={i} thing={t} onOpen={onOpen} />
        ))}
      </View>
    </View>
  );
}

function Thing({ thing, onOpen }: { thing: TripThing; onOpen: (id: SheetId) => void }) {
  const body = (
    <View style={styles.thing}>
      <View style={styles.tgrow}>
        <Text style={styles.tname}>{thing.name}</Text>
        {thing.because ? <Because>{thing.because}</Because> : null}
      </View>
      {thing.state || thing.tag ? <StatePill kind={thing.state ?? 'saved'} label={thing.tag} /> : null}
      {thing.opens ? <Sym sf="chevron.right" fallback="chevron-forward" size={13} color={colors.inkLo} style={styles.chev} /> : null}
    </View>
  );
  if (thing.opens) {
    return (
      <Pressable onPress={() => onOpen(thing.opens!)} style={({ pressed }) => [pressed && styles.pressed]}>
        {body}
      </Pressable>
    );
  }
  return body;
}

function Connector({ leg }: { leg?: string }) {
  return (
    <View style={styles.connector}>
      <View style={styles.dash} />
      {leg ? <Text style={styles.legText}>{leg}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginTop: 4 },
  stop: { flexDirection: 'row', gap: 13, alignItems: 'flex-start' },
  thumb: {
    width: THUMB,
    height: THUMB,
    borderRadius: 15,
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.12)',
  },
  emoji: { fontSize: 22 },
  info: { flex: 1, minWidth: 0 },
  when: { fontFamily: fonts.uiBold, fontSize: 10.5, letterSpacing: 1, color: colors.inkLo },
  place: { fontFamily: fonts.voiceSemi, fontSize: 18, color: colors.inkHi, marginTop: 1 },
  thing: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, marginTop: 11 },
  tgrow: { flex: 1, minWidth: 0 },
  tname: { fontFamily: fonts.uiSemi, fontSize: 14.5, color: colors.inkHi },
  chev: { marginTop: 1 },
  pressed: { opacity: 0.6 },
  connector: { flexDirection: 'row', alignItems: 'center', gap: 9, marginLeft: THUMB / 2, paddingVertical: 5 },
  dash: { width: 0, height: 20, borderLeftWidth: 2, borderStyle: 'dashed', borderColor: 'rgba(255,255,255,0.28)' },
  legText: { fontFamily: fonts.uiSemi, fontSize: 11.5, color: colors.inkLo },
});
