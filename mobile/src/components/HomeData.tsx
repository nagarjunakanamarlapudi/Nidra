// The repository seam (the one models.ts always pointed at): the single source
// the home grid + sheets read from. Loads the live feed from the backend once at
// startup and maps it to the app's shapes, falling back to curated mock when the
// API is empty or unreachable so the app is never blank.

import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { fetchDreams } from '../api/client';
import { fromDreams } from '../data/fromDreams';
import { greeting as mockGreeting, worlds as mockWorlds, details as mockDetails } from '../data/mock';
import type { World, WorldDetail } from '../data/models';

export interface HomeData {
  greeting: { hello: string; note: string };
  worlds: World[];
  details: Record<string, WorldDetail>;
}

const MOCK_HOME: HomeData = { greeting: mockGreeting, worlds: mockWorlds, details: mockDetails };

type Status = 'loading' | 'ready';

interface HomeCtx {
  status: Status;
  data: HomeData; // always populated (mock until/unless live data arrives)
  live: boolean; // true once real backend data is showing
  reload: () => void;
}

const Ctx = createContext<HomeCtx | null>(null);

export function useHomeData(): HomeCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error('useHomeData must be used inside <HomeDataProvider>');
  return v;
}

// Build live HomeData from dreams; keep the curated Tokyo trip showpiece as the
// marquee. On empty/error, return curated mock (live:false) — never throw.
async function loadHome(): Promise<{ data: HomeData; live: boolean }> {
  try {
    const dreams = await fetchDreams();
    if (!dreams.length) return { data: MOCK_HOME, live: false };

    const { worlds, details, marqueeKey } = fromDreams(dreams);

    // The flat dreams API can't express an itinerary, so the travel tile opens
    // the curated trip sheet (route ribbon + day-cards) — the locked showpiece.
    if (marqueeKey && mockDetails.tokyo) {
      const tile = worlds.find((w) => w.key === marqueeKey);
      if (tile) tile.opens = 'tokyo';
      details.tokyo = mockDetails.tokyo;
      if (mockDetails['tokyo.ryokan']) details['tokyo.ryokan'] = mockDetails['tokyo.ryokan'];
    }

    const n = worlds.length;
    const greeting = {
      hello: mockGreeting.hello, // evaluates the time-of-day getter once
      note: `${n} ${n === 1 ? 'thing is' : 'things are'} on your mind — I’ve done the legwork on each.`,
    };
    return { data: { greeting, worlds, details }, live: true };
  } catch {
    return { data: MOCK_HOME, live: false };
  }
}

export function HomeDataProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<Status>('loading');
  const [data, setData] = useState<HomeData>(MOCK_HOME);
  const [live, setLive] = useState(false);

  const load = useCallback(() => {
    setStatus('loading');
    void loadHome().then((res) => {
      setData(res.data);
      setLive(res.live);
      setStatus('ready');
    });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return <Ctx.Provider value={{ status, data, live, reload: load }}>{children}</Ctx.Provider>;
}
