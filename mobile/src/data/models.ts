// UI-level types. NOTE: the backend has no "worlds/today/dream-feed" aggregation
// yet (confirmed in exploration), so these are the app's own shapes. The API will
// change, so we keep these intentionally UI-shaped and swap behind the repository
// seam (src/data/repository.ts) later.

import type { GradeKey } from '../theme/tokens';

// A sheet id: a world key ('tokyo'), a drill-down ('tokyo.ryokan'), or 'talk'.
export type SheetId = string;

export interface World {
  key: string;
  glyph: string;
  name: string;
  sub?: string;
  image: string;
  grade: GradeKey;
  size: 'full' | 'half';
  tall?: boolean;
  spark?: string; // a colored "live" dot
  opens: SheetId; // which detail this tile rises (usually === key)
}

// Which surface a signal came from — drives the provenance chips. The whole moat
// is the cross-surface join, so we always show where an inference was stitched from.
export type SourceKind =
  | 'calendar'
  | 'messages'
  | 'email'
  | 'web'
  | 'reading'
  | 'docs'
  | 'maps'
  | 'photos'
  | 'finance'
  | 'patterns';

// The hero of every world: a cross-surface, anticipatory, ACTIONABLE move — the
// thing you couldn't trivially do yourself and an incumbent couldn't trivially match.
export interface Anticipation {
  kicker: string; // e.g. "WHAT I'D DO"
  title: string; // the anticipated need, in companion voice
  why: string; // the cross-surface reasoning
  sources: SourceKind[]; // the surfaces this was stitched from
  primary: string; // primary action label
  secondary?: string; // optional secondary action
}

export interface GatheredItem {
  glyph: string;
  image: string;
  name: string;
  say: string;
  because?: string; // the personal "why this is here" (e.g. "you searched ramen 3×")
  opens?: SheetId; // optional drill-down (e.g. the ryokan detail)
}

export interface Insight {
  kicker: string;
  title: string;
  why: string;
}

export interface Belief {
  text?: string; // a plain belief
  oldText?: string; // for a revised belief: the struck-through prior
  newText?: string; // ...and what it became
  sure: string; // companion-voice confidence ("I'm fairly sure now …")
}

export interface DetailRow {
  label: string;
  value: string;
}

// ---- Templates: each world renders a domain-native BODY, not one generic layout.
// 'standard' = the anticipation + gathered card stack; 'trip' = the itinerary
// template (route ribbon + day-cards). More to come: 'pulse' (relationships),
// 'tracker' (projects), 'digest' (learning). The "because" rationale + state pills
// + provenance stay shared across templates.
export type WorldTemplate = 'standard' | 'trip';

// The per-item status pill. A small, consistent system that replaces ad-hoc tags:
// verified (checked against a live source) · pick (Nidra's choice) · book (needs
// you) · saved (noted). This is how a suggestion shows it was actually vetted.
export type TripState = 'verified' | 'pick' | 'book' | 'saved';

export interface TripThing {
  name: string;
  state?: TripState; // the status pill
  tag?: string; // optional label override for the pill (e.g. "2 options")
  because?: string; // the personal "why this is here"
  opens?: SheetId; // optional drill-down (e.g. the ryokan detail)
}

export interface TripStop {
  when: string; // "DAY 1–2", "DEPART"
  place: string; // "Tokyo", "Fly home"
  image?: string; // thumbnail photo
  glyph?: string; // emoji shown behind the photo / for icon-only stops
  things?: TripThing[];
  leg?: string; // travel-time label shown in the connector to the NEXT stop
}

// The C1 "Nidra speaks" decision — the anticipatory call, in her voice, no alert
// box. It still LEADS the sheet (the moat), it just doesn't look like an error.
export interface TripDecision {
  text: string; // the call, in Nidra's voice (Fraunces)
  primary: string; // primary action (dawn)
  secondary?: string; // a quiet alternative
  sources: SourceKind[]; // where it was stitched from
}

export interface TripRoute {
  cities: string[]; // ["Tokyo", "Kyoto"]
  leg?: string; // the hop between them ("shinkansen · 2h15")
  skip?: { place: string; note: string }; // a place deliberately left off the line
}

export interface Trip {
  countdown?: string; // "in 38 days" — shown as a hero badge
  decision?: TripDecision;
  route?: TripRoute;
  stopsLabel?: string; // section header for the day list (defaults to "The itinerary")
  stops: TripStop[];
}

export interface SheetButton {
  label: string;
  primary?: boolean;
}

// Everything a world sheet can render. Sections are optional; WorldSheet renders
// whichever are present, anticipation-first (help before mirror).
export interface WorldDetail {
  key: SheetId;
  label: string; // header label (with emoji)
  heightPct?: number;
  hero: { image: string; kicker: string; title: string; height?: number; titleSize?: number };
  note: string;
  template?: WorldTemplate; // defaults to 'standard'
  trip?: Trip; // when template === 'trip'
  anticipation?: Anticipation;
  persona?: string; // the "dream" world
  beliefsLabel?: string;
  beliefs?: Belief[];
  insight?: Insight;
  gatheredLabel?: string;
  gathered?: GatheredItem[];
  rows?: DetailRow[]; // a detail/drill-down (the ryokan)
  buttons?: SheetButton[];
  cta?: { label: string; variant?: 'moon' | 'dawn'; closes?: boolean };
  ask?: string; // "Ask me anything about X…"
  footer?: string;
}

export type ChatRole = 'nidra' | 'me' | 'did';
export interface ChatMessage {
  role: ChatRole;
  text: string;
}
