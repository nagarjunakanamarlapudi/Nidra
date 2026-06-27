// Content script: observes the page and emits structured activity events.
// Privacy-first: honors a pause flag + domain denylist, never reads sensitive
// fields, and redacts PII before anything leaves the page.
import { api } from "./browser-api.js";
import {
  analyzePage,
  classify,
  describeInput,
  isSensitiveInput,
  redactString,
} from "./recognizers.js";
import { makeEvent } from "./schema.js";

const DEFAULT_DENYLIST = [
  "chase.com", "bankofamerica.com", "wellsfargo.com", "paypal.com",
  "1password.com", "lastpass.com", "bitwarden.com", "accounts.google.com",
];

let cfg = { paused: false, denylist: DEFAULT_DENYLIST, captureForms: true, captureSelections: true };
let started = false;
let pageStart = Date.now();
let maxScrollPct = 0;
let currentPageId = null;

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
  try {
    const r = api.runtime.sendMessage({ type: "nidra-event", event });
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
  maxScrollPct = 0;
}

// --- behavior listeners ---
addEventListener("scroll", () => { maxScrollPct = Math.max(maxScrollPct, scrollPct()); }, { passive: true });
addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") emitPrimary("flush"); });
addEventListener("pagehide", () => emitPrimary("flush"));

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
  setTimeout(() => emitPrimary("spa"), 800);
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
  setTimeout(() => emitPrimary("load"), 600); // let SPA content settle
  watchSpa();
}
init();
