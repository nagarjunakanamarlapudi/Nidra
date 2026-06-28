// Pure mapping: backend dreams → the app's home shapes (World tiles + WorldDetail
// sheets). No React, no fetch, no browser/RN globals — so it's trivially testable
// and mirrors the extension's "pure recognizers/opinions" convention.
//
// A dream IS an anticipation (hypothesis = the move, kind = its framing,
// provenance = where it was stitched from), so it drops straight into the
// anticipation-first WorldDetail. Topic/glyph/grade/image are synthesized
// deterministically from provenance so the grid looks intentional, not random.

import { colors } from '../theme/tokens';
import type { GradeKey } from '../theme/tokens';
import type { Dream } from '../api/client';
import type { Anticipation, SourceKind, World, WorldDetail } from './models';

// Same deterministic photo helper the mock uses (expo-image falls back to the
// world's color grade if the network is blocked, so a tile is never blank).
const img = (seed: string, w: number, h: number) =>
  `https://picsum.photos/seed/${seed}/${w}/${h}`;

// kind → the dawn kicker that leads the card.
const KICKER: Record<Dream['kind'], string> = {
  need: "WHAT YOU'LL NEED",
  suggestion: "WHAT I'D DO",
  foresight: 'HEADS UP',
};

// kind → a short tile teaser + a primary action label (decorative — the real,
// wired action is the "Ask me anything…" row that opens the live chat).
const SUB: Record<Dream['kind'], string> = {
  need: 'waiting on you',
  suggestion: 'I have an idea',
  foresight: 'a heads-up',
};
const PRIMARY: Record<Dream['kind'], string> = {
  need: 'Help me get ready',
  suggestion: 'Show me',
  foresight: 'Keep an eye on it',
};

interface Topic {
  name: string;
  glyph: string;
  grade: GradeKey;
  seed: string;
  isTravel?: boolean;
}

function hashS(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

// Classify from PROVENANCE only (the structured intent:/interest:/preference:
// tags) — not the free-text hypothesis, which name-drops "Tokyo" even in the
// ramen dream and would wrongly collapse distinct tiles.
function topicFor(d: Dream): Topic {
  const hay = d.provenance.join(' ').toLowerCase();
  if (/travel|trip|itinerary|flight|tokyo|japan|kyoto|hakone/.test(hay))
    return { name: 'Tokyo Trip', glyph: '🗾', grade: 'tokyo', seed: 'kyototemple', isTravel: true };
  if (/ramen|omakase|food|dining|restaurant|eat/.test(hay))
    return { name: 'Food & Ramen', glyph: '🍜', grade: 'study', seed: 'ramenbowl' };
  if (/coffee|roaster|espresso|cafe/.test(hay))
    return { name: 'Coffee', glyph: '☕', grade: 'review', seed: 'coffeebar' };
  if (/visa|immigration|h-?1b|sponsor/.test(hay))
    return { name: 'Visa & Work', glyph: '🛂', grade: 'priya', seed: 'passportdesk' };
  if (/job|interview|career|offer|hiring|recruit/.test(hay))
    return { name: 'Job Search', glyph: '💼', grade: 'review', seed: 'desk9' };
  if (/read|book|paper|consensus|raft|paxos|article/.test(hay))
    return { name: 'Reading', glyph: '📚', grade: 'reading', seed: 'oldbooks' };
  const first = (d.provenance[0] ?? '').replace(/^[a-z]+:/i, '').replace(/[-_]/g, ' ').trim();
  const name = first ? first.replace(/\b\w/g, (c) => c.toUpperCase()) : 'On your radar';
  return { name, glyph: '✨', grade: 'dream', seed: `radar${hashS(name)}` };
}

// Provenance tags → the fixed SourceKind surfaces (Sources.tsx renders these as
// chips). Deduped, capped at 3; the richer words go into the `why` line instead.
function sourcesFor(prov: string[]): SourceKind[] {
  const out: SourceKind[] = [];
  for (const p of prov) {
    const t = p.toLowerCase();
    let k: SourceKind = 'patterns';
    if (/travel|trip|flight|hotel|map|place|itinerary/.test(t)) k = 'maps';
    else if (/ramen|food|dining|coffee|restaurant|eat/.test(t)) k = 'web';
    else if (/read|book|paper|article/.test(t)) k = 'reading';
    else if (/visa|immigration|h-?1b|sponsor/.test(t)) k = 'email';
    else if (/job|interview|career|offer|hiring|work/.test(t)) k = 'email';
    else if (/cal|meeting|schedule|event/.test(t)) k = 'calendar';
    else if (/mail|email|message/.test(t)) k = 'email';
    if (!out.includes(k)) out.push(k);
  }
  if (out.length === 0) out.push('patterns');
  return out.slice(0, 3);
}

// Human-readable provenance words for the "why", e.g. ["intent:travel",
// "interest:ramen"] → "travel + ramen".
function provWords(prov: string[]): string {
  const words = prov
    .map((p) => p.replace(/^[a-z]+:/i, '').replace(/[-_]/g, ' ').trim())
    .filter(Boolean);
  return [...new Set(words)].slice(0, 2).join(' + ');
}

function toWorld(d: Dream, t: Topic, key: string, size: 'full' | 'half', i: number): World {
  const tall = size === 'half' && i % 3 === 2;
  const [w, h] = size === 'full' ? [620, 440] : [360, tall ? 360 : 300];
  return {
    key,
    glyph: t.glyph,
    name: t.name,
    sub: SUB[d.kind],
    image: img(t.seed, w, h),
    grade: t.grade,
    size,
    tall,
    spark: d.kind === 'need' ? colors.dawn : undefined,
    opens: key,
  };
}

function toDetail(d: Dream, t: Topic, key: string): WorldDetail {
  const sure =
    d.confidence >= 0.7 ? 'fairly sure' : d.confidence >= 0.5 ? 'starting to think' : 'wondering if';
  const words = provWords(d.provenance);
  const why = words
    ? `Stitched from your ${words} signals — I'm ${sure} this is coming.`
    : `Based on your recent patterns — I'm ${sure} this is coming.`;
  const anticipation: Anticipation = {
    kicker: KICKER[d.kind],
    title: d.hypothesis,
    why,
    sources: sourcesFor(d.provenance),
    primary: PRIMARY[d.kind],
    secondary: 'Not now',
  };
  return {
    key,
    label: `${t.glyph} ${t.name}`,
    hero: { image: img(t.seed, 1000, 700), kicker: KICKER[d.kind], title: t.name },
    note: 'I pulled this together from what you’ve been up to lately.',
    anticipation,
    ask: 'Ask me anything about this…',
  };
}

export interface MappedHome {
  worlds: World[];
  details: Record<string, WorldDetail>;
  // The key of the travel/Tokyo world, if any — the caller points this tile at
  // the curated trip showpiece (route ribbon + day-cards) the API can't supply.
  marqueeKey: string | null;
}

export function fromDreams(dreams: Dream[]): MappedHome {
  const active = dreams
    .filter((d) => d.status !== 'refuted' && d.status !== 'expired')
    .sort((a, b) => b.confidence - a.confidence);

  // One tile per topic — keep the highest-confidence dream per topic (already
  // sorted), so the grid never shows two near-identical "Tokyo Trip" tiles.
  const picked: { dream: Dream; topic: Topic }[] = [];
  const seen = new Set<string>();
  for (const d of active) {
    const topic = topicFor(d);
    if (seen.has(topic.name)) continue;
    seen.add(topic.name);
    picked.push({ dream: d, topic });
    if (picked.length >= 7) break;
  }

  // Float the travel tile to the front so it becomes the full-width marquee.
  const travelIdx = picked.findIndex((p) => p.topic.isTravel);
  if (travelIdx > 0) picked.unshift(picked.splice(travelIdx, 1)[0]);

  const worlds: World[] = [];
  const details: Record<string, WorldDetail> = {};
  let marqueeKey: string | null = null;
  picked.forEach(({ dream, topic }, i) => {
    const key = `dream-${dream.id}`;
    const size: 'full' | 'half' = i === 0 ? 'full' : 'half';
    worlds.push(toWorld(dream, topic, key, size, i));
    details[key] = toDetail(dream, topic, key);
    if (topic.isTravel && !marqueeKey) marqueeKey = key;
  });

  return { worlds, details, marqueeKey };
}
