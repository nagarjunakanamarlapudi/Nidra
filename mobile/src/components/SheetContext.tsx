import React, { createContext, useCallback, useContext, useState } from 'react';
import type { SheetId } from '../data/models';

interface SheetCtx {
  stack: SheetId[];
  open: (id: SheetId) => void;
  close: () => void; // pop the top sheet
  closeAll: () => void;
}

const Ctx = createContext<SheetCtx | null>(null);

export function useSheets(): SheetCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error('useSheets must be used inside <SheetStateProvider>');
  return v;
}

export function SheetStateProvider({ children }: { children: React.ReactNode }) {
  const [stack, setStack] = useState<SheetId[]>([]);
  const open = useCallback(
    (id: SheetId) => setStack((s) => (s[s.length - 1] === id ? s : [...s, id])),
    [],
  );
  const close = useCallback(() => setStack((s) => s.slice(0, -1)), []);
  const closeAll = useCallback(() => setStack([]), []);
  return <Ctx.Provider value={{ stack, open, close, closeAll }}>{children}</Ctx.Provider>;
}
