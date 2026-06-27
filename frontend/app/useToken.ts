"use client";

import { useCallback, useSyncExternalStore } from "react";

const STORAGE_KEY = "pragya_token";

// A tiny external store over `localStorage` so React can subscribe to the token
// via `useSyncExternalStore` — this reads the value without calling setState in
// an effect and stays correct across tabs and reloads.
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) {
    listener();
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // Reflect changes made in other tabs/windows.
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

function getSnapshot(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    // localStorage may be unavailable (e.g. privacy mode); treat as signed out.
    return null;
  }
}

// On the server there is no token; this also drives the `ready` flag below.
function getServerSnapshot(): string | null {
  return null;
}

/** State of the single-user token, read from and synced to `localStorage`. */
export interface TokenState {
  /** The current token, or `null` if signed out. */
  token: string | null;
  /** `true` once the client has hydrated and read `localStorage`. */
  ready: boolean;
  /** Persist a token and update state. */
  setToken: (value: string) => void;
  /** Clear the stored token (sign out). */
  clearToken: () => void;
}

/**
 * Manage the access token in `localStorage`. Subscribes to the value so it
 * survives reloads and stays in sync across browser tabs.
 */
export function useToken(): TokenState {
  const token = useSyncExternalStore(
    subscribe,
    getSnapshot,
    getServerSnapshot,
  );

  // `getServerSnapshot` returns the same value during SSR and the first client
  // render; once mounted, the effect-free store gives us the real value. We use
  // a hydration flag to avoid flashing the sign-in screen before that happens.
  const ready = useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );

  const setToken = useCallback((value: string) => {
    const trimmed = value.trim();
    try {
      window.localStorage.setItem(STORAGE_KEY, trimmed);
    } catch {
      // Ignore persistence failures.
    }
    emit();
  }, []);

  const clearToken = useCallback(() => {
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Ignore.
    }
    emit();
  }, []);

  return { token, ready, setToken, clearToken };
}
