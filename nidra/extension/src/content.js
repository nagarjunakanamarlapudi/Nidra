// Content script: observes the page and emits structured activity events.
// Privacy-first: honors a pause flag + domain denylist, never reads sensitive
// fields, and redacts PII before anything leaves the page.
import { api } from "./browser-api.js";
import { analyzePage } from "./analyze.js";
import {
  classify,
  describeImpression,
  describeInput,
  describeInteraction,
  detectStep,
  isSensitiveInput,
  redactString,
} from "./recognizers.js";
import { gate } from "./gate.js";
import { makeEvent } from "./schema.js";

// Mirrors background.js DEFAULT_CFG.denylist — financial / crypto / password-
// manager / auth domains we never capture (the card+SSN redaction won't mask
// account numbers or balances, so we skip these pages entirely).
const DEFAULT_DENYLIST = [
  "chase.com", "bankofamerica.com", "wellsfargo.com", "citibank.com",
  "capitalone.com", "americanexpress.com", "discover.com", "usbank.com",
  "schwab.com", "fidelity.com", "vanguard.com",
  "paypal.com", "venmo.com", "coinbase.com",
  "1password.com", "lastpass.com", "bitwarden.com", "dashlane.com",
  "accounts.google.com", "login.microsoftonline.com",
];

let cfg = { paused: false, denylist: DEFAULT_DENYLIST, captureForms: true, captureSelections: true, captureContent: true };
let started = false;
let maxScrollPct = 0;
let currentPageId = null;

// Active (foreground) time accounting: the timer PAUSES when the tab is hidden,
// so dwell/latency reflect time the user was actually on the page — not a tab
// left open in the background.
let activeAccumMs = 0;
let activeSince = Date.now();
let pageVisible = true;

function activeMs() {
  return Math.round(activeAccumMs + (pageVisible ? Date.now() - activeSince : 0));
}
function pauseActive() {
  if (pageVisible) {
    activeAccumMs += Date.now() - activeSince;
    pageVisible = false;
  }
}
function resumeActive() {
  if (!pageVisible) {
    activeSince = Date.now();
    pageVisible = true;
  }
}

// Decision capture state (reset per page load).
const IMPRESSION_CAP = 40;
const DWELL_MS = 400; // a control must stay in view this long to count as an impression
let seenKeys = new Set();
let recentInteractions = new Map(); // elementKey -> {action, t} — dedupe click+change double-fire
let impressionCount = 0;
let impressionObserver = null;
let dwellTimers = new Map(); // element -> pending dwell timeout (cleared if it scrolls away)

// Journey: where this page-load came from (stitched across navigations via sessionStorage).
let fromUrl = null;
let fromPageId = null;
let cachedPrimary = null; // { id, ev } — analyzePage result cached per page-load (avoid re-parse on flush)

const host = () => location.hostname.replace(/^www\./, "");
const denylisted = () => cfg.denylist.some((d) => host() === d || host().endsWith("." + d));
const uuid = () => (crypto?.randomUUID ? crypto.randomUUID() : "id-" + Date.now() + "-" + Math.round(performance.now()));
const stripQuery = (u) => { try { const x = new URL(u); return x.origin + x.pathname; } catch { return u || null; } };
// sessionStorage is shared with the page, so journey values read back are UNTRUSTED
// (a page could poison them). Accept only an http(s) URL (query-stripped, capped,
// redacted) and a uuid-shaped id.
const sanitizeUrl = (u) => (u && /^https?:\/\//i.test(u) ? redactString(stripQuery(u).slice(0, 300)).value : null);
const sanitizeId = (id) => (/^[\w-]{1,64}$/.test(id || "") ? id : null);

function scrollPct() {
  const h = document.documentElement;
  const denom = h.scrollHeight - h.clientHeight;
  if (denom <= 0) return 1;
  return Math.min(1, Math.max(0, (h.scrollTop || window.scrollY || 0) / denom));
}

function send(event) {
  // The privacy gate is the single chokepoint EVERY producer passes through.
  const gated = gate(event);
  if (!gated) return; // dropped: sensitive / unknown control / all-PII label
  try {
    const r = api.runtime.sendMessage({ type: "nidra-event", event: gated });
    if (r && typeof r.catch === "function") r.catch(() => {});
  } catch {
    /* extension context invalidated (e.g. reload) — ignore */
  }
}

function emitPrimary(reason) {
  if (cfg.paused || denylisted()) return;
  // analyzePage runs Readability (expensive), so compute once per page-load and
  // reuse on flush (visibilitychange/pagehide), updating only the live metrics.
  let ev = cachedPrimary && cachedPrimary.id === currentPageId ? cachedPrimary.ev : null;
  if (!ev) {
    ev = analyzePage(document, location, { ts: Date.now() });
    ev.id = currentPageId; // stable per page-load so load + flush upsert (no double count)
    ev.data = { ...(ev.data || {}), journey: { fromUrl, fromPageId } };
    if (cfg.captureContent === false && ev.data) delete ev.data.content;
    cachedPrimary = { id: currentPageId, ev };
  }
  ev.metrics = {
    dwellMs: activeMs(), // foreground time only — paused while the tab is hidden
    scrollPct: Math.round(maxScrollPct * 100) / 100,
    ...(ev.type === "reading" ? { readPct: Math.round(maxScrollPct * 100) / 100 } : {}),
    reason,
  };
  send(ev);
}

function newPage() {
  // Journey: "from" = whatever this tab recorded on its previous page-load
  // (survives same-origin navigations via sessionStorage); referrer covers the
  // cross-origin first hop.
  try {
    fromPageId = sanitizeId(sessionStorage.getItem("nidra:lastPageId"));
    fromUrl = sanitizeUrl(sessionStorage.getItem("nidra:lastUrl")) || sanitizeUrl(document.referrer);
  } catch {
    fromPageId = null;
    fromUrl = sanitizeUrl(document.referrer);
  }
  currentPageId = uuid();
  cachedPrimary = null;
  activeAccumMs = 0;
  activeSince = Date.now();
  pageVisible = document.visibilityState !== "hidden";
  maxScrollPct = 0;
  seenKeys = new Set();
  recentInteractions = new Map();
  impressionCount = 0;
  dwellTimers.forEach((t) => clearTimeout(t));
  dwellTimers.clear();
  try {
    sessionStorage.setItem("nidra:lastPageId", currentPageId);
    sessionStorage.setItem("nidra:lastUrl", stripQuery(location.href) || location.href);
  } catch { /* sessionStorage unavailable */ }
}

// --- decisions: interaction / impression / action ---
// Each carries context_id = the page-load id so the backend can correlate
// "shown -> picked -> reached/abandoned" within one decision.

const DECISION_CONTROLS = "a,button,select,input,[role=switch],[role=radio],[role=checkbox],[role=button],[role=tab],[role=menuitem],[role=option]";

function onInteraction(target) {
  if (cfg.paused || denylisted()) return;
  const el = target?.closest?.(DECISION_CONTROLS) || target;
  const desc = describeInteraction(el);
  if (!desc) return;
  // Dedupe the click+change pair (and rapid repeats) for the same control+state.
  const now = performance.now();
  const prev = recentInteractions.get(desc.elementKey);
  if (prev && prev.action === desc.action && now - prev.t < 700) return;
  recentInteractions.set(desc.elementKey, { action: desc.action, t: now });
  const ev = makeEvent("interaction", {
    ts: Date.now(), url: location.href, domain: host(), title: document.title,
    source: classify(location).source, data: desc,
  });
  ev.id = uuid();
  ev.context_id = currentPageId;
  ev.metrics = { latencyMs: activeMs() }; // foreground time to the interaction
  send(ev);
}

function onImpression(el) {
  if (cfg.paused || denylisted() || impressionCount >= IMPRESSION_CAP) return;
  const desc = describeImpression(el);
  if (!desc) return;
  if (seenKeys.has(desc.elementKey)) return; // first-seen only; stable across re-render
  seenKeys.add(desc.elementKey);
  impressionCount += 1;
  const ev = makeEvent("impression", {
    ts: Date.now(), url: location.href, domain: host(), title: document.title,
    source: classify(location).source, data: desc,
  });
  ev.id = currentPageId + ":" + desc.elementKey; // dedupe key (upsert, not double-count)
  ev.context_id = currentPageId;
  send(ev);
}

function armImpressions() {
  if (cfg.paused || denylisted() || typeof IntersectionObserver === "undefined") return;
  if (!impressionObserver) {
    impressionObserver = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            if (dwellTimers.has(e.target)) continue; // dwell already counting down
            const target = e.target;
            const timer = setTimeout(() => {
              dwellTimers.delete(target);
              onImpression(target);
              impressionObserver.unobserve(target);
            }, DWELL_MS);
            dwellTimers.set(target, timer);
          } else {
            const timer = dwellTimers.get(e.target); // scrolled away before the dwell elapsed
            if (timer) { clearTimeout(timer); dwellTimers.delete(e.target); }
          }
        }
      },
      { threshold: 0.5 }
    );
  }
  let armed = 0;
  for (const el of document.querySelectorAll(DECISION_CONTROLS)) {
    if (armed >= IMPRESSION_CAP) break;
    try { impressionObserver.observe(el); armed += 1; } catch { /* detached */ }
  }
}

function emitAction(milestone, step = {}) {
  if (cfg.paused || denylisted()) return;
  const ev = makeEvent("action", {
    ts: Date.now(), url: location.href, domain: host(), title: document.title,
    source: classify(location).source,
    data: {
      milestone,
      flow: step.flow || null,
      stepLabel: step.label || null,
      stepIndex: step.index ?? null,
      of: step.of ?? null,
    },
  });
  ev.id = uuid();
  ev.context_id = currentPageId;
  send(ev);
}

// Generalized funnel: detect a step in ANY multi-step flow (checkout, signup,
// wizard, …) and record flow entry ("reached") vs. progression ("advanced").
// Flow continuity is tracked across page-loads via sessionStorage; the backend
// can infer abandonment (a flow that was "reached" but never "submitted").
function maybeStep() {
  const step = detectStep(document, location);
  if (!step) {
    try { sessionStorage.removeItem("nidra:flow"); } catch { /* ignore */ }
    return;
  }
  let prevFlow = null;
  try { prevFlow = sessionStorage.getItem("nidra:flow"); } catch { /* ignore */ }
  try { sessionStorage.setItem("nidra:flow", step.flow || "flow"); } catch { /* ignore */ }
  emitAction(prevFlow && prevFlow === step.flow ? "advanced" : "reached", step);
}

// --- behavior listeners ---
addEventListener("scroll", () => { maxScrollPct = Math.max(maxScrollPct, scrollPct()); }, { passive: true });
addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") {
    pauseActive(); // stop the dwell/latency clock while the tab is backgrounded
    emitPrimary("flush");
  } else {
    resumeActive();
  }
});
addEventListener("pagehide", () => emitPrimary("flush"));

// Interaction capture: semantic clicks/toggles/selects, routed through the gate.
addEventListener("click", (e) => onInteraction(e.target), true);
addEventListener("change", (e) => onInteraction(e.target), true);

addEventListener(
  "submit",
  (e) => {
    if (!cfg.captureForms || cfg.paused || denylisted()) return;
    const form = e.target;
    if (!form?.querySelectorAll) return;
    for (const el of form.querySelectorAll("input,textarea")) {
      if (isSensitiveInput(el) || !el.value) continue;
      const d = describeInput(el);
      if (d.kind === "search" || d.value) {
        const ev = makeEvent("form_input", {
          ts: Date.now(), url: location.href, domain: host(), title: document.title,
          source: classify(location).source, data: d, redacted: d.redacted,
        });
        ev.id = uuid();
        send(ev);
      }
    }
    const step = detectStep(document, location);
    if (step) emitAction("submitted", step); // reached the end of a flow (only inside a detected flow)
  },
  true
);

let selTimer;
addEventListener("mouseup", () => {
  if (!cfg.captureSelections || cfg.paused || denylisted()) return;
  clearTimeout(selTimer);
  selTimer = setTimeout(() => {
    const sel = String(getSelection?.() || "").trim();
    if (sel.length < 12) return;
    const { value, redacted } = redactString(sel.slice(0, 300));
    const ev = makeEvent("selection", {
      ts: Date.now(), url: location.href, domain: host(), title: document.title,
      source: classify(location).source, data: { text: value, length: sel.length }, redacted,
    });
    ev.id = uuid();
    send(ev);
  }, 400);
});

// --- SPA route changes (gmail/gcal/etc.) ---
let lastUrl = location.href;
function onRoute() {
  if (location.href === lastUrl) return;
  lastUrl = location.href;
  newPage();
  setTimeout(() => { emitPrimary("spa"); maybeStep(); armImpressions(); }, 800);
}
function watchSpa() {
  addEventListener("hashchange", onRoute);
  addEventListener("popstate", onRoute);
  const ps = history.pushState;
  const rs = history.replaceState;
  history.pushState = function () { const ret = ps.apply(this, arguments); onRoute(); return ret; };
  history.replaceState = function () { const ret = rs.apply(this, arguments); onRoute(); return ret; };
  let moTimer;
  try {
    new MutationObserver(() => { clearTimeout(moTimer); moTimer = setTimeout(onRoute, 1500); })
      .observe(document.body, { childList: true, subtree: true });
  } catch {}
}

async function init() {
  if (started) return;
  started = true;
  try {
    const c = await api.runtime.sendMessage({ type: "nidra-getConfig" });
    if (c) cfg = { ...cfg, ...c };
  } catch {}
  if (denylisted()) return;
  newPage();
  setTimeout(() => { emitPrimary("load"); maybeStep(); armImpressions(); }, 600); // let content settle
  watchSpa();
}
init();
