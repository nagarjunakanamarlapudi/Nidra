// Content script: observes the page and emits structured activity events.
// Privacy-first: honors a pause flag + domain denylist, never reads sensitive
// fields, and redacts PII before anything leaves the page.
import { api } from "./browser-api.js";
import {
  analyzePage,
  classify,
  describeImpression,
  describeInput,
  describeInteraction,
  isSensitiveInput,
  redactString,
} from "./recognizers.js";
import { gate } from "./gate.js";
import { makeEvent } from "./schema.js";

const DEFAULT_DENYLIST = [
  "chase.com", "bankofamerica.com", "wellsfargo.com", "paypal.com",
  "1password.com", "lastpass.com", "bitwarden.com", "accounts.google.com",
];

let cfg = { paused: false, denylist: DEFAULT_DENYLIST, captureForms: true, captureSelections: true };
let started = false;
let pageStart = Date.now();
let pageStartPerf = 0; // performance.now() baseline for decision latency
let maxScrollPct = 0;
let currentPageId = null;

// Decision capture state (reset per page load).
const IMPRESSION_CAP = 40;
let seenKeys = new Set();
let recentInteractions = new Map(); // elementKey -> {action, t} — dedupe click+change double-fire
let impressionCount = 0;
let impressionObserver = null;
let funnelReached = false;
let submitted = false;
const FUNNEL_RE = /checkout|cart|payment|booking|\breview\b|\border\b|subscribe/i;

const host = () => location.hostname.replace(/^www\./, "");
const denylisted = () => cfg.denylist.some((d) => host() === d || host().endsWith("." + d));
const uuid = () => (crypto?.randomUUID ? crypto.randomUUID() : "id-" + Date.now() + "-" + Math.round(performance.now()));

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
  const ev = analyzePage(document, location, { ts: Date.now() });
  ev.id = currentPageId; // stable per page-load so load + flush upsert (no double count)
  ev.metrics = {
    dwellMs: Date.now() - pageStart,
    scrollPct: Math.round(maxScrollPct * 100) / 100,
    ...(ev.type === "reading" ? { readPct: Math.round(maxScrollPct * 100) / 100 } : {}),
    reason,
  };
  send(ev);
}

function newPage() {
  currentPageId = uuid();
  pageStart = Date.now();
  pageStartPerf = performance.now();
  maxScrollPct = 0;
  seenKeys = new Set();
  recentInteractions = new Map();
  impressionCount = 0;
  funnelReached = false;
  submitted = false;
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
  ev.metrics = { latencyMs: Math.max(0, Math.round(performance.now() - pageStartPerf)) };
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
          if (!e.isIntersecting) continue;
          onImpression(e.target);
          impressionObserver.unobserve(e.target);
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

function emitAction(milestone, extra = {}) {
  if (cfg.paused || denylisted()) return;
  const ev = makeEvent("action", {
    ts: Date.now(), url: location.href, domain: host(), title: document.title,
    source: classify(location).source, data: { milestone, funnel: "checkout", ...extra },
  });
  ev.id = uuid();
  ev.context_id = currentPageId;
  send(ev);
}

function maybeFunnel() {
  if (!funnelReached && FUNNEL_RE.test(location.pathname + " " + location.href)) {
    funnelReached = true;
    emitAction("reached_checkout");
  }
}

// --- behavior listeners ---
addEventListener("scroll", () => { maxScrollPct = Math.max(maxScrollPct, scrollPct()); }, { passive: true });
addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") emitPrimary("flush"); });
addEventListener("pagehide", () => {
  emitPrimary("flush");
  if (funnelReached && !submitted) emitAction("abandoned"); // left a flow without finishing
});

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
    submitted = true;
    emitAction("submitted"); // reached the end of a flow
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
  setTimeout(() => { emitPrimary("spa"); maybeFunnel(); armImpressions(); }, 800);
}
function watchSpa() {
  addEventListener("hashchange", onRoute);
  addEventListener("popstate", onRoute);
  const ps = history.pushState;
  history.pushState = function () { ps.apply(this, arguments); onRoute(); };
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
  setTimeout(() => { emitPrimary("load"); maybeFunnel(); armImpressions(); }, 600); // let content settle
  watchSpa();
}
init();
