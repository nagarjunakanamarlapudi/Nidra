// Shared activity-event schema + helpers. Pure: no browser globals, safe to
// import in the content script, the background worker, the collector, and tests.

export const SCHEMA_VERSION = 1;

export const EVENT_TYPES = Object.freeze([
  "pageview", // visited a page (fallback)
  "reading", // read an article / long-form content
  "search", // ran a search query
  "email", // activity in a webmail client (gmail)
  "calendar", // activity in a calendar client (gcal)
  "form_input", // typed into a (non-sensitive) form field
  "selection", // selected / highlighted text
  "impression", // a decision-point (choice elements / offers / CTAs) was shown
  "interaction", // a semantic click / toggle / select — the decision, never the raw value
  "action", // a funnel milestone (reached_checkout / submitted / completed / abandoned)
]);

export const SOURCES = Object.freeze({
  GMAIL: "gmail",
  GCAL: "gcal",
  MEDIUM: "medium",
  SUBSTACK: "substack",
  ARXIV: "arxiv",
  SEARCH: "search",
  WEB: "web",
});

/**
 * Build a normalized activity event. Every captured signal is one of these.
 * `ts` is injectable so tests are deterministic.
 */
export function makeEvent(type, fields = {}) {
  return {
    v: SCHEMA_VERSION,
    type,
    ts: fields.ts ?? Date.now(),
    url: fields.url ?? null,
    domain: fields.domain ?? null,
    title: fields.title ?? null,
    source: fields.source ?? SOURCES.WEB,
    data: fields.data ?? {},
    metrics: fields.metrics ?? {}, // { dwellMs, scrollPct, readPct, latencyMs }
    redacted: Boolean(fields.redacted),
  };
}
