// Nidra design tokens — the shared source of truth, ported verbatim from the
// validated mock (mocks/index.html :root). These values are what a future web
// build (or RN-Web) consumes too, so "reuse across web + app" lives here.

export const colors = {
  night0: '#07060d',
  night1: '#0c0a15',
  inkHi: '#F5F2EC', // warm paper, never pure white
  inkMid: '#C3BFD2',
  inkLo: '#8480A0',
  dawn: '#FFB279', // morning / warmth / primary action
  dawn2: '#FF8E6E',
  moon: '#AEB6FF', // night / dream / belief
  moon2: '#C9A6FF',
  // provenance (which surface a signal came from)
  cal: '#FFC27A',
  mail: '#FF9AA8',
  read: '#C9A6FF',
  web: '#7FE0D6',
} as const;

export type GradeKey =
  | 'tokyo'
  | 'reading'
  | 'priya'
  | 'review'
  | 'family'
  | 'study'
  | 'dream'
  | 'ryokan';

// Per-world color grade — also the graceful no-photo fallback (a tile is never blank).
export const worldGrades: Record<GradeKey, [string, string]> = {
  tokyo: ['#FF9255', '#6E5BFF'],
  reading: ['#9A7BFF', '#4B3A8E'],
  priya: ['#FF8FA3', '#A4506A'],
  review: ['#FFC27A', '#B5732E'],
  family: ['#FFAE8B', '#C76B86'],
  study: ['#67E0CE', '#2E6E8E'],
  dream: ['#AEB6FF', '#5B4A9E'],
  ryokan: ['#E0B57A', '#5E7E5A'],
};

// Bottom-up legibility scrim used under text-on-photo (tiles + heroes).
export const photoScrim = ['rgba(0,0,0,0.10)', 'transparent', 'rgba(7,5,14,0.82)'] as const;

export const radius = { card: 30, lg: 36, sheet: 34, thumb: 13 } as const;

export const fonts = {
  voice: 'Fraunces_500Medium', // what Nidra "says"
  voiceR: 'Fraunces_400Regular',
  voiceItalic: 'Fraunces_500Medium_Italic',
  voiceSemi: 'Fraunces_600SemiBold',
  ui: 'Inter_400Regular',
  uiMed: 'Inter_500Medium',
  uiSemi: 'Inter_600SemiBold',
  uiBold: 'Inter_700Bold',
} as const;

// Strong easing curves (mirrors the mock's cubic-beziers).
export const bezier = {
  out: [0.23, 1, 0.32, 1] as const,
  drawer: [0.32, 0.72, 0, 1] as const,
};
