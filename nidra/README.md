# Nidra — Activity Capture 🌙

> Ambient, privacy-first activity capture that learns your behavior and **forms opinions about you**. One Manifest V3 WebExtension — runs in **Chrome** today and converts to a **Safari Web Extension for iOS** from the same source.

This is the capture + opinion-forming layer for the *Nidra* concept ("the assistant that sleeps to learn you"). It watches what you read, search, and do across the web, turns each signal into a structured event, and derives a model of you — interests, reading taste, active projects, and natural-language beliefs with confidence + provenance.

## What it captures

| Signal | How | Example |
|---|---|---|
| **Article reading** | content script extracts title/author/tags + word count + scroll/dwell | "read *Understanding Raft Consensus* by Jane Doe, 90% scrolled" |
| **Searches** | query parsed from search-engine URLs (Google/Bing/DDG/Brave/Ecosia) | "searched *raft consensus algorithm*" |
| **Email (Gmail)** | reads action (read/compose), subject, participant count | "read mail: *Re: Q3 planning…*" |
| **Calendar (GCal)** | view + event creation (title/time) | "created event: *Design review with team*" |
| **Browsing history** | `chrome.history` backfill on install (last 3 days) | cold-start signal (Chrome only) |
| **Form inputs** | non-sensitive fields + search boxes, with secrets masked | search/filter terms |
| **Selections** | highlighted text ≥ 12 chars, with secrets masked | what you copy/quote |

## Privacy (first-class, not bolted on)
- **Local-first** — events live in `chrome.storage.local`; dev builds can mirror to the local Pragya backend or local collector. Nothing goes to a third party by default.
- **Never captures secrets** — password / cc / cvv / ssn / otp fields are skipped entirely; payment cards and SSNs are masked out of captured strings. Contact details like names, emails, and phone numbers are intentionally kept as user-model signal.
- **Domain denylist** — banking / crypto / password-manager / auth domains are ignored by default.
- **Pause anytime** — one toggle in the popup; every inferred belief carries provenance.

## Architecture

**capture → ingest (connector-shaped) → dream** — the same shape as a Pragya connector: the browser ingests activity to a server, then the dreamer runs on top of it.

```
  capture (extension)                ingest (server)                  dream (on-device LLM)
  ───────────────────                ───────────────                  ─────────────────────
content.js ─(events)─► background.js ─► chrome.storage.local ─► popup
 (recognizers)          (ring buffer)  └─► POST /events ────► collector ─► deriveOpinions  (instant, heuristic)
                                           (or /connectors/         └────► POST /dream ─► dreamer ─► Gemma 4 (Ollama)
                                            browser-activity/ingest)                         connect signals → intent
```

Two layers of understanding sit on the captured events:
- **`opinions.js`** — heuristic, instant, deterministic: interests, reading taste, cross-signal projects, beliefs with provenance.
- **`dreamer.mjs`** — the **"Sleep" pass**: an LLM (on-device **Gemma 4** via Ollama) that **connects signals across activity** into higher-level intent + persona + next-needs. e.g. *flights + car rental + ryokan reading = "planning a Japan trip"* — the leap heuristics can't make. Provider-pluggable; default is fully on-device.

The recognizers and opinions engine are pure functions with **no browser globals**, so the exact code that runs in the extension also runs in unit tests, the collector, and the dreamer's digest.

## Quick start — Chrome (backend by default)
The extension is **baked from the project's root `.env`** at build time (`APP_PORT` → backend URL, `API_AUTH_TOKEN` → token), so it points at your Pragya backend with **no manual config**.
1. Backend up (repo root): `make up && make migrate`. Ollama running with Gemma 4: `ollama serve`.
2. `chrome://extensions` → **Developer mode** → **Load unpacked** → `nidra/extension`.
3. Browse / search / read. Events ingest to Postgres (`browser_activity_events`) via the BrowserActivity connector.
4. Click the **🌙 Nidra** icon → **Dreams → 🌙 Dream** (backend dreamer, on-device Gemma) · **Opinions** · **Signals**.

> **Changed `.env`?** Re-run `npm run build` to re-bake, then reload the extension. `extension/dist/` is committed so it loads with no build step.
>
> **Zero-backend mode:** set `backendUrl` to `""` (popup/storage) and run `npm run collector` to use the local Node mirror instead (`NIDRA_DREAM_MODEL` overrides the dream model).

## Tests
```bash
npm install
npm test            # build + 16 unit tests (recognizers, opinions) + 1 Chrome E2E
npm run test:unit   # jsdom unit tests only
npm run test:e2e    # Playwright loads the real extension into Chromium and asserts capture + redaction + opinions
```
The E2E serves the fixtures at their **real hostnames** (medium.com, mail.google.com, …) via Playwright route interception, so the recognizers classify them exactly as in production.

## iOS Safari
```bash
npm run ios         # generates ios/Nidra/Nidra.xcodeproj from the same extension (and fixes the bundle-id prefix)
open ios/Nidra/Nidra.xcodeproj
```
In Xcode pick an iPhone simulator and **Run**. Then in the simulator: **Settings → Apps → Safari → Extensions → Nidra → enable**, and in Safari "Allow on Every Website".

- Validated: `xcodebuild … -sdk iphonesimulator` → **BUILD SUCCEEDED** (iPhone 17 simulator).
- Note: `chrome.history` backfill is Chrome-only — iOS Safari has no history API (the code guards for this). Live page/search/reading capture works on iOS.

## Layout
```
extension/        the WebExtension (load this folder unpacked)
  manifest.json   MV3
  src/            recognizers.js · opinions.js · content.js · background.js · popup.js · schema.js · browser-api.js
  dist/           esbuild bundles (committed)
  popup.html/css  popup UI · icons/ (generated)
collector/        local ingest server — server.mjs (events + /opinions + /dream) · dreamer.mjs (Gemma 4)
fixtures/         deterministic Gmail / GCal / Medium / arXiv / Search pages for the E2E
tests/            unit/ (jsdom + dreamer mock) · e2e/ (Playwright capture + live Gemma dream)
build.mjs         icon generator + esbuild bundling
```
