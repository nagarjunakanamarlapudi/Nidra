// Background service worker: receives events, persists them (ring buffer in
// chrome.storage.local), mirrors them to the local collector, backfills from
// browser history, and serves derived opinions to the popup.
import { api } from "./browser-api.js";
import { deriveOpinions } from "./opinions.js";
import { classify, extractSearch, domainOf, redactString } from "./recognizers.js";
import { makeEvent } from "./schema.js";
import { DEFAULTS } from "./config.js";

const STORE_KEY = "nidra_events";
const CFG_KEY = "nidra_config";
const MAX_EVENTS = 2000;

const DEFAULT_CFG = {
  paused: false,
  collectorUrl: "http://localhost:8799", // local Node mirror; off if server not running
  // Pragya backend (the real "our server"): events ingest to the BrowserActivity
  // connector and Dream calls the backend dreamer. Defaults live in config.js so
  // the extension works with no manual setup. appToken = the app's API_AUTH_TOKEN
  // (one token for both ingest and dream).
  backendUrl: DEFAULTS.backendUrl,
  appToken: DEFAULTS.appToken,
  denylist: [
    // Financial, crypto, password-manager and auth domains. The narrowed
    // redaction (card + SSN only) intentionally does NOT mask account/routing
    // numbers or balances, so we don't capture these pages at all.
    "chase.com", "bankofamerica.com", "wellsfargo.com", "citibank.com",
    "capitalone.com", "americanexpress.com", "discover.com", "usbank.com",
    "schwab.com", "fidelity.com", "vanguard.com",
    "paypal.com", "venmo.com", "coinbase.com",
    "1password.com", "lastpass.com", "bitwarden.com", "dashlane.com",
    "accounts.google.com", "login.microsoftonline.com",
  ],
  captureForms: true,
  captureSelections: true,
  captureContent: true,
  backfillDays: 3,
};

let writeChain = Promise.resolve(); // serialize read-modify-write on storage

async function getCfg() {
  const o = await api.storage.local.get(CFG_KEY);
  return { ...DEFAULT_CFG, ...(o[CFG_KEY] || {}) };
}
async function setCfg(patch) {
  const next = { ...(await getCfg()), ...patch };
  await api.storage.local.set({ [CFG_KEY]: next });
  return next;
}
async function getEvents() {
  const o = await api.storage.local.get(STORE_KEY);
  return o[STORE_KEY] || [];
}

function upsert(arr, ev) {
  const i = ev.id != null ? arr.findIndex((e) => e.id === ev.id) : -1;
  if (i >= 0) arr[i] = ev;
  else arr.push(ev);
  return arr;
}

// Stable dedupe id for a backfilled history page, bounded to the backend's
// client_id column (varchar 128). Scrubbed URLs are usually short; if one is
// long, keep a readable prefix + a stable hash so it stays unique AND ≤128.
function histId(url) {
  const base = "hist:" + url;
  if (base.length <= 128) return base;
  let h = 0;
  for (let i = 0; i < url.length; i++) h = (Math.imul(31, h) + url.charCodeAt(i)) | 0;
  return base.slice(0, 118) + ":" + (h >>> 0).toString(36); // ≤ 118 + 1 + 7 = 126
}

function postToCollector(cfg, ev) {
  // Prefer the Pragya backend connector when configured; else the local mirror.
  if (cfg.backendUrl) {
    fetch(cfg.backendUrl.replace(/\/$/, "") + "/connectors/browser_activity/ingest", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...(cfg.appToken ? { authorization: "Bearer " + cfg.appToken } : {}),
      },
      body: JSON.stringify({ events: [ev] }),
    }).catch(() => {});
    return;
  }
  if (!cfg.collectorUrl) return;
  fetch(cfg.collectorUrl + "/events", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(ev),
  }).catch(() => {}); // collector may be offline — fine
}

async function updateBadge(n) {
  try {
    await api.action.setBadgeText({ text: n ? String(Math.min(n, 9999)) : "" });
    await api.action.setBadgeBackgroundColor({ color: "#4f46e5" });
  } catch {}
}

function addEvent(ev) {
  writeChain = writeChain
    .then(async () => {
      const cfg = await getCfg();
      if (cfg.paused) return;
      // Ship to the backend first — fire-and-forget, so the network POST isn't
      // gated on the (serialized) local-storage round-trip below.
      postToCollector(cfg, ev);
      let arr = upsert(await getEvents(), ev);
      if (arr.length > MAX_EVENTS) arr = arr.slice(-MAX_EVENTS);
      await api.storage.local.set({ [STORE_KEY]: arr });
      await updateBadge(arr.length);
    })
    .catch(() => {});
  return writeChain;
}

api.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    switch (msg?.type) {
      case "nidra-getConfig":
        sendResponse(await getCfg());
        break;
      case "nidra-setConfig":
        sendResponse(await setCfg(msg.patch || {}));
        break;
      case "nidra-event":
        await addEvent(msg.event);
        sendResponse({ ok: true });
        break;
      case "nidra-getState": {
        const events = await getEvents();
        sendResponse({ events, opinions: deriveOpinions(events) });
        break;
      }
      case "nidra-clear":
        writeChain = writeChain
          .then(async () => {
            await api.storage.local.set({ [STORE_KEY]: [] });
            await updateBadge(0);
          })
          .catch(() => {});
        await writeChain;
        sendResponse({ ok: true });
        break;
      default:
        sendResponse({ ok: false });
    }
  })();
  return true; // keep the message channel open for the async response
});

// --- cold-start: backfill from browser history ---
async function backfill() {
  try {
    if (!api.history?.search) return;
    const cfg = await getCfg();
    const since = Date.now() - cfg.backfillDays * 86400000;
    const items = await api.history.search({ text: "", startTime: since, maxResults: 500 });
    const isDeny = (h) => cfg.denylist.some((d) => h.replace(/^www\./, "") === d || h.endsWith("." + d));
    for (const it of items) {
      if (!it.url) continue;
      let u;
      try { u = new URL(it.url); } catch { continue; }
      if (isDeny(u.hostname)) continue;
      const loc = { href: it.url, hostname: u.hostname, pathname: u.pathname, search: u.search, hash: u.hash };
      // Strip query/fragment before STORING: history URLs can carry auth tokens
      // (e.g. a login otpToken), which the live path's gate scrubs too. classify/
      // extractSearch still get the full loc, so the search query is recoverable.
      const cleanUrl = u.origin + u.pathname;
      const title = redactString(it.title || "").value;
      const c = classify(loc);
      let ev;
      if (c.source === "search") {
        const s = extractSearch(loc, null);
        if (!s?.query) continue;
        ev = makeEvent("search", { ts: it.lastVisitTime || Date.now(), url: cleanUrl, domain: domainOf(it.url), title, source: "search", data: s, redacted: true });
      } else {
        const type = c.kind === "reading" ? "reading" : "pageview";
        ev = makeEvent(type, {
          ts: it.lastVisitTime || Date.now(), url: cleanUrl, domain: domainOf(it.url), title, source: c.source,
          data: type === "reading" ? { title, wordCount: 0 } : {},
        });
      }
      ev.id = histId(cleanUrl); // dedupe by scrubbed URL across runs; bounded ≤128 (client_id column)
      ev.backfill = true;
      await addEvent(ev);
    }
  } catch {}
}

// Push everything currently in local storage to the backend (idempotent — the
// backend upserts by client_id). Runs on install/startup so captures made before
// the backend was reachable still land.
async function flushAll() {
  const cfg = await getCfg();
  if (!cfg.backendUrl) return;
  const events = await getEvents();
  if (!events.length) return;
  fetch(cfg.backendUrl.replace(/\/$/, "") + "/connectors/browser_activity/ingest", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(cfg.appToken ? { authorization: "Bearer " + cfg.appToken } : {}),
    },
    body: JSON.stringify({ events }),
  }).catch(() => {});
}

api.runtime.onInstalled.addListener(() => {
  backfill();
  flushAll();
});
api.runtime.onStartup?.addListener?.(() => {
  backfill();
  flushAll();
});
