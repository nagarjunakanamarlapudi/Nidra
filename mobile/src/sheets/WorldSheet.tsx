import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Hero } from '../components/Hero';
import { GatheredRow } from '../components/GatheredRow';
import { Belief } from '../components/Belief';
import { Anticipation } from '../components/Anticipation';
import { TripDecision } from '../components/TripDecision';
import { RouteRibbon } from '../components/RouteRibbon';
import { TripDays } from '../components/TripDays';
import { AskRow, Button, Cta, Insight, MLabel, Note, Persona } from '../components/SheetBits';
import { useSheets } from '../components/SheetContext';
import { colors, fonts } from '../theme/tokens';
import type { WorldDetail } from '../data/models';

// One renderer for every world. Sections are data-driven and render in a fixed,
// deliberate order: the anticipatory MOVE leads; "what I gathered" is demoted to
// supporting evidence underneath. Help first, mirror last.
export function WorldSheet({ detail }: { detail: WorldDetail }) {
  const { open, closeAll } = useSheets();
  const d = detail;
  const isTrip = d.template === 'trip' && !!d.trip;
  return (
    <>
      <Hero
        image={d.hero.image}
        kicker={d.hero.kicker}
        title={d.hero.title}
        height={d.hero.height}
        titleSize={d.hero.titleSize}
        badge={isTrip ? d.trip!.countdown : undefined}
      />
      <Note>{d.note}</Note>

      {isTrip ? (
        <>
          {d.trip!.decision ? <TripDecision data={d.trip!.decision} /> : null}
          {d.trip!.route ? <RouteRibbon data={d.trip!.route} /> : null}
          <MLabel>{d.trip!.stopsLabel ?? 'The itinerary'}</MLabel>
          <TripDays stops={d.trip!.stops} onOpen={open} />
        </>
      ) : d.anticipation ? (
        <Anticipation data={d.anticipation} />
      ) : null}

      {d.persona ? <Persona>{d.persona}</Persona> : null}

      {d.beliefs?.length ? (
        <>
          <MLabel>{d.beliefsLabel ?? 'What I came to understand'}</MLabel>
          {d.beliefs.map((b, i) => (
            <Belief key={i} belief={b} />
          ))}
        </>
      ) : null}

      {d.insight ? <Insight insight={d.insight} /> : null}

      {d.gathered?.length ? (
        <>
          <MLabel>{d.gatheredLabel ?? "What I've gathered for you"}</MLabel>
          {d.gathered.map((g, i) => (
            <GatheredRow key={i} item={g} onPress={() => open(g.opens ?? 'talk')} />
          ))}
        </>
      ) : null}

      {d.rows?.length ? (
        <View style={styles.rows}>
          {d.rows.map((r, i) => (
            <View key={i} style={styles.row}>
              <Text style={styles.label}>{r.label}</Text>
              <Text style={styles.value}>{r.value}</Text>
            </View>
          ))}
        </View>
      ) : null}

      {d.buttons?.length ? (
        <View style={styles.btns}>
          {d.buttons.map((b, i) => (
            <Button key={i} label={b.label} primary={b.primary} />
          ))}
        </View>
      ) : null}

      {d.footer ? <Note dim>{d.footer}</Note> : null}

      {d.cta ? (
        <Cta label={d.cta.label} variant={d.cta.variant} onPress={d.cta.closes ? closeAll : undefined} />
      ) : null}

      {d.ask ? <AskRow label={d.ask} onPress={() => open('talk')} /> : null}
    </>
  );
}

const styles = StyleSheet.create({
  rows: { marginTop: 16, gap: 10 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 13,
    paddingHorizontal: 15,
    borderRadius: 15,
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
  },
  label: { fontFamily: fonts.ui, fontSize: 13.5, color: colors.inkLo },
  value: { fontFamily: fonts.uiSemi, fontSize: 14, color: colors.inkHi },
  btns: { flexDirection: 'row', gap: 10, marginTop: 16 },
});
