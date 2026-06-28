// The validated mock content, typed. Everything the app renders comes from here
// for v1. Swap to real endpoints later behind the repository seam.
//
// Design principle (the product's whole point): every world LEADS with an
// anticipatory, cross-surface, ACTIONABLE move — the thing you couldn't trivially
// do yourself. "What I gathered" is demoted to supporting evidence underneath.
// Today is Saturday, June 27. Thu review = Jul 2 · Priya's defense = Fri Jul 3 ·
// study = Sun Jul 5 · mom's birthday = Jul 6 (9 days out). Kept internally consistent.

import { colors } from '../theme/tokens';
import type { ChatMessage, World, WorldDetail } from './models';

// Reliable real photos (deterministic per seed). expo-image falls back to the
// world's color grade if the network is blocked, so a tile is never blank.
const img = (seed: string, w: number, h: number) =>
  `https://picsum.photos/seed/${seed}/${w}/${h}`;

// Time-of-day word, computed live against the user's clock so the greeting never
// says "Morning" in the afternoon. Shared with the chat sheet's opener.
export function greetingWord(d = new Date()): string {
  const h = d.getHours();
  if (h < 12) return 'Morning';
  if (h < 18) return 'Afternoon';
  return 'Evening';
}

export const greeting = {
  // getter so it re-evaluates on each render rather than freezing at module load
  get hello() {
    return `${greetingWord()}, Ishaan.`;
  },
  note: 'Three of these are waiting on a decision from you. I’ve done the legwork on each.',
};

// ---- Home tiles ----
export const worlds: World[] = [
  {
    key: 'tokyo', glyph: '🗾', name: 'Tokyo Trip', sub: 'one thing doesn’t add up',
    image: img('kyototemple', 620, 440), grade: 'tokyo', size: 'full', spark: colors.dawn, opens: 'tokyo',
  },
  {
    key: 'reading', glyph: '📚', name: 'Reading', sub: 'deep in consensus',
    image: img('oldbooks', 360, 360), grade: 'reading', size: 'half', tall: true, opens: 'reading',
  },
  {
    key: 'priya', glyph: '💬', name: 'Priya', sub: 'waiting on you', spark: colors.mail,
    image: img('cafelight', 360, 300), grade: 'priya', size: 'half', opens: 'priya',
  },
  {
    key: 'review', glyph: '🏛️', name: 'Thursday Review', sub: 'not ready yet',
    image: img('whiteboard9', 360, 300), grade: 'review', size: 'half', opens: 'review',
  },
  {
    key: 'family', glyph: '👨‍👩‍👧', name: 'Family', sub: 'mom’s birthday soon',
    image: img('familyhome2', 360, 340), grade: 'family', size: 'half', tall: true, opens: 'family',
  },
  {
    key: 'study', glyph: '✍️', name: 'Study Group', sub: 'Sunday — no topic yet',
    image: img('library7', 360, 300), grade: 'study', size: 'half', opens: 'study',
  },
  {
    key: 'dream', glyph: '🌙', name: 'Last night', sub: 'what I learned',
    image: img('nightstars', 360, 300), grade: 'dream', size: 'half', opens: 'dream',
  },
];

// ---- World detail sheets (data-driven; WorldSheet renders them) ----
export const details: Record<string, WorldDetail> = {
  tokyo: {
    key: 'tokyo',
    label: '🗾 Tokyo Trip',
    hero: { image: img('kyotostreet', 720, 440), kicker: '🗾 TOKYO TRIP', title: 'Your trip to Japan' },
    note: 'Five days, mid-range, walkable — and mostly sorted.',
    template: 'trip',
    trip: {
      countdown: 'in 38 days',
      // C1 — the call, in Nidra's voice (no alert box). It still leads the sheet.
      decision: {
        text: 'One call before I lock this in — the three ryokans you saved are all in Hakone, 90 minutes each way. On a five-day trip a night in Kyoto fits you better, and costs less. I already found one.',
        primary: 'Swap to Kyoto',
        secondary: 'Keep Hakone',
        sources: ['web', 'maps', 'calendar'],
      },
      route: {
        cities: ['Tokyo', 'Kyoto'],
        leg: 'shinkansen · 2h15',
        skip: { place: 'Hakone', note: 'skipped · +3h round-trip off your line' },
      },
      stopsLabel: 'The five days',
      stops: [
        {
          when: 'DEPART', place: 'Fly to Tokyo', glyph: '✈️',
          things: [{ name: 'ANA · ~$900', state: 'saved', tag: '2 options', because: 'priced for the Tue–Sun window you usually fly' }],
        },
        {
          when: 'DAY 1–2', place: 'Tokyo', image: img('tokyocity9', 240, 240), glyph: '🗼',
          leg: '🚄 2h15 · shinkansen',
          things: [
            { name: '3 ramen spots', state: 'verified', because: 'you searched Tokyo ramen three times last week' },
            { name: 'A place to stay', state: 'book', because: 'you book lodging late — I’ll hold off nudging you' },
          ],
        },
        {
          when: 'DAY 4–5', place: 'Kyoto', image: img('kyototemple', 240, 240), glyph: '⛩️',
          things: [
            { name: 'Tsubaki-an ryokan', state: 'pick', because: 'private onsen, walkable — it travels like you do', opens: 'tokyo.ryokan' },
            { name: 'JR Pass', state: 'saved', because: 'cheaper than singles for the Tokyo–Kyoto hop' },
          ],
        },
        {
          when: 'DAY 5', place: 'Fly home', glyph: '🛫',
          things: [{ name: 'Evening flight · Kansai', because: 'leaves your last day open for temples' }],
        },
      ],
    },
    insight: {
      kicker: '🔗 SOMETHING I NOTICED',
      title: 'You keep drifting toward Kyoto, not just Tokyo.',
      why: 'Your reading and the spots you saved lean temples and quiet over nightlife. I’ll weight Kyoto when I plan your days.',
    },
    ask: 'Ask me anything about Tokyo…',
  },

  'tokyo.ryokan': {
    key: 'tokyo.ryokan',
    label: 'My Kyoto pick',
    heightPct: 0.86,
    hero: { image: img('kyotoryokan', 720, 520), kicker: '🏠 MY KYOTO PICK', title: 'Tsubaki-an, Higashiyama', height: 200, titleSize: 26 },
    note: 'A small ryokan minutes from the temples, with a private onsen. I picked it because it matches how you travel: quiet, compact, a little special, never flashy.',
    rows: [
      { label: 'Around', value: '$180 / night' },
      { label: 'Where', value: 'Higashiyama · walkable' },
      { label: 'Why you', value: 'Onsen · quiet · compact' },
    ],
    buttons: [
      { label: 'Save it', primary: true },
      { label: 'Show me others' },
    ],
  },

  reading: {
    key: 'reading',
    label: '📚 Reading',
    hero: { image: img('oldbooks2', 720, 420), kicker: '📚 READING', title: 'What you keep coming back to' },
    note: 'Four papers on consensus this week. You’re not browsing — you’re building toward something.',
    anticipation: {
      kicker: 'WHAT I’D DO',
      title: 'You’ve re-derived the same Raft-vs-Paxos comparison three times. I turned your highlights into one page.',
      why: 'Same passages, same margin notes, three sittings. I pulled them into a single Raft / Paxos / Viewstamped table — and it drops straight into Thursday’s review doc.',
      sources: ['reading', 'web', 'docs'],
      primary: 'Show me the table',
      secondary: 'Add VR to it',
    },
    insight: {
      kicker: '🔗 SOMETHING I NOTICED',
      title: 'This isn’t idle reading — it’s prep.',
      why: 'The papers, the afternoon you blocked Thursday, and the review doc all point one way. You’re getting ready to argue a position.',
    },
    gatheredLabel: 'What you’ve been in',
    gathered: [
      { glyph: '📄', image: img('paperdesk', 160, 160), name: 'Raft (extended)', say: 'You highlighted leader-election twice.' },
      { glyph: '📄', image: img('paperink', 160, 160), name: 'Paxos Made Simple', say: 'Bounced between this and Raft all week.' },
      { glyph: '🧪', image: img('servers2', 160, 160), name: 'Jepsen: etcd', say: 'Saved Tuesday, 1am. Read it twice.' },
    ],
    ask: 'Ask me about what you’re reading…',
  },

  priya: {
    key: 'priya',
    label: '💬 Priya',
    hero: { image: img('cafewindow', 720, 420), kicker: '💬 PRIYA', title: 'Priya' },
    note: 'You two usually talk most days. It’s gone quiet — and there’s a thread you left open.',
    anticipation: {
      kicker: 'WORTH A REPLY',
      title: 'Priya asked about Saturday three days ago. You haven’t replied — and you almost always answer her within the hour.',
      why: 'Her defense is this Friday; Saturday is her coming up for air. The dinner isn’t really about dinner. I can draft a yes that mentions the defense, in your voice.',
      sources: ['messages', 'calendar', 'patterns'],
      primary: 'Draft a reply',
      secondary: 'Remind me at 6',
    },
    insight: {
      kicker: '🔗 SOMETHING I NOTICED',
      title: 'You’ve gone quiet right when she’s most anxious.',
      why: 'Three unanswered messages and her defense on Friday — your usual rhythm with her is daily. A two-line reply now lands bigger than a long one later.',
    },
    gatheredLabel: 'The open thread',
    gathered: [
      { glyph: '💬', image: img('phonetext', 160, 160), name: '“Still on for Saturday?”', say: 'Sent Tuesday. Read, no reply.' },
      { glyph: '🎓', image: img('university', 160, 160), name: 'Her thesis defense', say: 'Friday 2pm — she’s nervous about the Q&A.' },
    ],
    ask: 'Ask me about Priya…',
  },

  review: {
    key: 'review',
    label: '🏛️ Thursday Review',
    hero: { image: img('whiteboardroom', 720, 420), kicker: '🏛️ THURSDAY REVIEW', title: 'The design review' },
    note: 'Thursday 3pm. It’s the big one — and right now it isn’t ready to send.',
    anticipation: {
      kicker: 'WHAT I’D DO',
      title: 'The doc’s still a draft and 2 of 5 reviewers haven’t opened it. Send tonight and they’ll have read it by Thursday.',
      why: 'You blocked Thursday afternoon but no prep time. I can nudge the two who haven’t opened it and hold 90 minutes tomorrow morning — after your no-meetings rule — to finish.',
      sources: ['calendar', 'docs', 'email'],
      primary: 'Nudge them + block 90 min',
      secondary: 'Just block the time',
    },
    insight: {
      kicker: '🔗 SOMETHING I NOTICED',
      title: 'Your reading is this review’s backbone.',
      why: 'The consensus papers you’ve been in all week are the doc’s background section. I can drop your highlights straight in.',
    },
    gatheredLabel: 'Where it stands',
    gathered: [
      { glyph: '📝', image: img('docpage', 160, 160), name: 'The doc', say: 'Draft. Last edit Tuesday. 3 open comments.' },
      { glyph: '👥', image: img('teamdesk', 160, 160), name: '5 reviewers', say: 'Aakash and Lin haven’t opened it yet.' },
      { glyph: '🗓️', image: img('calendarwall', 160, 160), name: 'Thu 3pm · 90 min', say: 'On your calendar. No prep block before it.' },
    ],
    ask: 'Ask me about the review…',
  },

  family: {
    key: 'family',
    label: '👨‍👩‍👧 Family',
    hero: { image: img('familytable', 720, 420), kicker: '👨‍👩‍👧 FAMILY', title: 'Family' },
    note: 'Mostly quiet, the way you like it — but a date is coming you’ll want to be ahead of.',
    anticipation: {
      kicker: 'WHAT I’D DO',
      title: 'Mom’s birthday is in 9 days. Last year you scrambled the day of.',
      why: 'In March you forwarded her a ceramics class in Bandra — “she’d love this.” Two spots are still open that weekend. Want me to book it, for both of you?',
      sources: ['calendar', 'email', 'patterns'],
      primary: 'Book two spots',
      secondary: 'Show me other ideas',
    },
    insight: {
      kicker: '🔗 SOMETHING I NOTICED',
      title: 'You call home on Sundays — this one’s worth more than a check-in.',
      why: 'Between her birthday and your travel planning, there’s more to say than usual. I’ll surface it Sunday morning so it isn’t rushed.',
    },
    gatheredLabel: 'What I’m holding onto',
    gathered: [
      { glyph: '🏺', image: img('pottery', 160, 160), name: 'The ceramics class', say: 'You forwarded it in March — “she’d love this.”' },
      { glyph: '🎁', image: img('giftwrap', 160, 160), name: 'Last year’s gift', say: 'A scarf, ordered the night before. It was late.' },
      { glyph: '🎂', image: img('birthday3', 160, 160), name: 'Birthday — July 6', say: '9 days out.' },
    ],
    ask: 'Ask me about family…',
  },

  study: {
    key: 'study',
    label: '✍️ Study Group',
    hero: { image: img('studylibrary', 720, 420), kicker: '✍️ STUDY GROUP', title: 'Study group' },
    note: 'Sunday’s session is coming and nobody’s claimed it yet.',
    anticipation: {
      kicker: 'WHAT I’D DO',
      title: 'You’ve led the last three Sundays. Hand this one off — and it lines up perfectly.',
      why: 'Aakash hasn’t presented yet, and he’s on consensus too — the same topic as your Thursday review. If he takes it, you both get prep for free. Want me to suggest it in the group?',
      sources: ['messages', 'calendar', 'reading'],
      primary: 'Suggest Aakash takes it',
      secondary: 'I’ll lead again',
    },
    insight: {
      kicker: '🔗 SOMETHING I NOTICED',
      title: 'This group keeps shadowing your real work.',
      why: 'Three of the last five topics overlapped what you were already reading. It’s quietly become your prep room, not a side thing.',
    },
    gatheredLabel: 'The session',
    gathered: [
      { glyph: '🗓️', image: img('clocklib', 160, 160), name: 'Sunday 5pm', say: 'Set. No topic yet — usually you pick.' },
      { glyph: '💬', image: img('groupchat', 160, 160), name: 'The group thread', say: 'Quiet since Monday. Everyone’s waiting.' },
    ],
    ask: 'Ask me about the group…',
  },

  dream: {
    key: 'dream',
    label: '🌙 Last night',
    hero: { image: img('nightskystars', 720, 400), kicker: '🌙 LAST NIGHT', title: 'While you slept', height: 150, titleSize: 27 },
    note: 'I went back over your day and got a little surer of who you are.',
    persona:
      'A hands-on engineer deep in distributed systems, quietly planning a trip to Japan. You guard your mornings, your time, and a straight answer.',
    beliefs: [
      {
        oldText: 'You want detailed, thorough write-ups.',
        newText: 'You want the short version — 3 bullets, no preamble.',
        sure: 'I changed my mind · from how you read and reply',
      },
      {
        text: 'You trust primary sources — you bounced off a “Top-10 tips” listicle almost instantly.',
        sure: 'I’m noticing this more and more · from your reading',
      },
    ],
    insight: {
      kicker: '🔗 THE THING I PIECED TOGETHER',
      title: 'You’re prepping a real decision, not just reading.',
      why: 'The consensus papers, the afternoon you blocked Thursday, and that “design review” email all point one way. No single one of them said it — together they did.',
    },
    footer: 'These are guesses. Tell me when I’m wrong — that’s how I get you.',
    cta: { label: 'Start the day →', variant: 'dawn', closes: true },
  },
};

// ---- Talk sheet ----
export const talk: ChatMessage[] = [
  { role: 'nidra', text: 'Morning. Want me to set up the design-team sync before you get pulled into things?' },
  { role: 'me', text: 'yeah do it, thursday works' },
  { role: 'did', text: '✓ Booked Thu 3pm — after your no-mornings rule' },
  { role: 'nidra', text: 'Done. I drafted the heads-up too, short and casual like you write. Want it on Telegram as well?' },
  { role: 'me', text: 'perfect' },
  { role: 'did', text: '✓ Sent · same voice everywhere' },
];
