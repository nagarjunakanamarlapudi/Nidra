"use client";

import { useState, type FormEvent } from "react";

interface TokenGateProps {
  /** Called with the entered token when the form is submitted. */
  onSubmit: (token: string) => void;
}

/** Single-user sign-in: a single field to enter the access token. */
export function TokenGate({ onSubmit }: TokenGateProps) {
  const [value, setValue] = useState("");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = value.trim();
    if (trimmed) {
      onSubmit(trimmed);
    }
  }

  return (
    <main className="flex min-h-dvh items-center justify-center px-6 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="font-serif text-5xl tracking-tight text-foreground">
            Pragya
          </h1>
          <p className="mt-3 text-sm text-muted">
            Your personal assistant. Enter your access token to continue.
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="rounded-2xl border border-border bg-surface p-6 shadow-sm"
        >
          <label
            htmlFor="token"
            className="mb-2 block text-xs font-medium uppercase tracking-wider text-muted"
          >
            Access token
          </label>
          <input
            id="token"
            type="password"
            autoComplete="current-password"
            autoFocus
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder="••••••••••••"
            className="w-full rounded-lg border border-border bg-background px-3.5 py-2.5 text-sm text-foreground outline-none transition placeholder:text-muted/60 focus:border-accent focus:ring-2 focus:ring-accent/20"
          />
          <button
            type="submit"
            disabled={!value.trim()}
            className="mt-4 w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Continue
          </button>
        </form>

        <p className="mt-5 text-center text-xs text-muted">
          The token is stored only in this browser.
        </p>
      </div>
    </main>
  );
}
