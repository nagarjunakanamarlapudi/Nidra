(() => {
  // extension/src/browser-api.js
  var api = typeof globalThis.browser !== "undefined" && globalThis.browser?.runtime ? globalThis.browser : globalThis.chrome;

  // extension/src/opinions.js
  var STOPWORDS = new Set(
    "the a an and or but for to of in on at by with from as is are was were be been being this that these those how what why when where who which your you i we they it its their our his her how-to your guide best vs how new top using use used make made get got into out over under more most less about across una el la los".split(/\s+/)
  );
  function tokenize(text) {
    if (!text) return [];
    return String(text).toLowerCase().split(/[^a-z0-9+#]+/).filter((w) => w.length >= 3 && !STOPWORDS.has(w) && !/^\d+$/.test(w));
  }
  function topEntries(map, n) {
    return [...map.entries()].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1)).slice(0, n);
  }
  function bump(map, key, by = 1) {
    if (!key) return;
    map.set(key, (map.get(key) || 0) + by);
  }
  var PRIMARY_HINTS = /arxiv|doi\.org|\.pdf|ieee|acm\.org|nature\.com|sciencedirect|paper/i;
  var LISTICLE_RE = /^\s*\d+\s+(things|ways|tips|reasons|tricks|habits|tools)\b/i;
  function deriveOpinions(events = []) {
    const reading = events.filter((e) => e.type === "reading");
    const searches = events.filter((e) => e.type === "search");
    const emails = events.filter((e) => e.type === "email");
    const calendar = events.filter((e) => e.type === "calendar");
    const interest = /* @__PURE__ */ new Map();
    const interestEvidence = /* @__PURE__ */ new Map();
    for (const e of reading) {
      for (const t of e.data?.tags || []) {
        bump(interest, t, 3);
        bump(interestEvidence, t);
      }
      for (const t of tokenize(e.data?.title)) {
        bump(interest, t, 1);
      }
    }
    for (const e of searches) {
      for (const t of tokenize(e.data?.query)) {
        bump(interest, t, 2);
        bump(interestEvidence, t);
      }
    }
    const maxScore = Math.max(1, ...interest.values());
    const interests = topEntries(interest, 8).map(([topic, score]) => ({
      topic,
      score: Math.round(score / maxScore * 100) / 100,
      evidence: interestEvidence.get(topic) || 0
    }));
    const words = reading.map((e) => e.data?.wordCount || 0).filter(Boolean);
    const readPcts = reading.map((e) => e.metrics?.readPct).filter((x) => typeof x === "number");
    const avgWords = words.length ? Math.round(words.reduce((a, b) => a + b, 0) / words.length) : 0;
    const avgReadPct = readPcts.length ? Math.round(readPcts.reduce((a, b) => a + b, 0) / readPcts.length * 100) / 100 : null;
    const longForm = words.filter((w) => w > 1e3).length;
    const primaryCount = reading.filter(
      (e) => PRIMARY_HINTS.test(e.url || "") || PRIMARY_HINTS.test(e.source || "")
    ).length;
    const listicleCount = reading.filter((e) => LISTICLE_RE.test(e.data?.title || "")).length;
    const authorMap = /* @__PURE__ */ new Map();
    const sourceMap = /* @__PURE__ */ new Map();
    for (const e of reading) {
      bump(authorMap, e.data?.author);
      bump(sourceMap, e.source || e.domain);
    }
    const readingTaste = {
      articlesRead: reading.length,
      avgWords,
      avgReadPct,
      longFormRatio: reading.length ? Math.round(longForm / reading.length * 100) / 100 : 0,
      prefersPrimarySources: primaryCount > listicleCount && primaryCount > 0,
      listicleAversion: listicleCount === 0 && reading.length >= 3,
      topAuthors: topEntries(authorMap, 5).map(([author, count]) => ({ author, count })),
      topSources: topEntries(sourceMap, 5).map(([source, count]) => ({ source, count }))
    };
    const inReading = /* @__PURE__ */ new Set();
    for (const e of reading) {
      (e.data?.tags || []).forEach((t) => inReading.add(t));
      tokenize(e.data?.title).forEach((t) => inReading.add(t));
    }
    const inSearch = /* @__PURE__ */ new Set();
    for (const e of searches) tokenize(e.data?.query).forEach((t) => inSearch.add(t));
    const crossTopics = [...inSearch].filter((t) => inReading.has(t));
    const activeProjects = crossTopics.map((t) => ({ label: t, evidence: interestEvidence.get(t) || 0, crossSignal: true })).sort((a, b) => b.evidence - a.evidence || (a.label < b.label ? -1 : 1)).slice(0, 5);
    const byHour = {};
    for (const e of events) {
      const h = new Date(e.ts).getUTCHours();
      byHour[h] = (byHour[h] || 0) + 1;
    }
    const peakHours = Object.entries(byHour).sort((a, b) => b[1] - a[1] || Number(a[0]) - Number(b[0])).slice(0, 3).map(([h]) => Number(h));
    const beliefs = [];
    const conf = (n, ceil) => Math.min(1, Math.round(n / ceil * 100) / 100);
    if (interests[0]) {
      beliefs.push({
        statement: `Actively interested in "${interests[0].topic}"`,
        confidence: conf(interests[0].evidence, 4),
        evidence: interests[0].evidence,
        provenance: ["reading.tags", "search.query"]
      });
    }
    if (activeProjects[0]) {
      beliefs.push({
        statement: `Currently researching "${activeProjects[0].label}" (searched it AND read about it)`,
        confidence: conf(activeProjects[0].evidence + 1, 3),
        evidence: activeProjects[0].evidence,
        provenance: ["search", "reading"]
      });
    }
    if (readingTaste.articlesRead >= 2) {
      const lf = readingTaste.longFormRatio >= 0.5;
      beliefs.push({
        statement: lf ? `Prefers long-form reading (avg ~${avgWords} words/article)` : `Prefers shorter reads (avg ~${avgWords} words/article)`,
        confidence: conf(readingTaste.articlesRead, 4),
        evidence: readingTaste.articlesRead,
        provenance: ["reading.wordCount"]
      });
    }
    if (readingTaste.prefersPrimarySources) {
      beliefs.push({
        statement: "Trusts primary sources over listicles",
        confidence: conf(primaryCount, 3),
        evidence: primaryCount,
        provenance: ["reading.url"]
      });
    }
    if (readingTaste.topAuthors[0]?.author && readingTaste.topAuthors[0].count >= 2) {
      beliefs.push({
        statement: `Follows the author "${readingTaste.topAuthors[0].author}"`,
        confidence: conf(readingTaste.topAuthors[0].count, 3),
        evidence: readingTaste.topAuthors[0].count,
        provenance: ["reading.author"]
      });
    }
    if (calendar.length || emails.length) {
      beliefs.push({
        statement: `Manages work via webmail/calendar (${emails.length} mail + ${calendar.length} calendar signals)`,
        confidence: conf(emails.length + calendar.length, 4),
        evidence: emails.length + calendar.length,
        provenance: ["email", "calendar"]
      });
    }
    return {
      generatedFrom: events.length,
      counts: {
        reading: reading.length,
        search: searches.length,
        email: emails.length,
        calendar: calendar.length,
        total: events.length
      },
      interests,
      readingTaste,
      activeProjects,
      routines: { byHour, peakHours },
      beliefs
    };
  }

  // extension/src/schema.js
  var SCHEMA_VERSION = 1;
  var EVENT_TYPES = Object.freeze([
    "pageview",
    // visited a page (fallback)
    "reading",
    // read an article / long-form content
    "search",
    // ran a search query
    "email",
    // activity in a webmail client (gmail)
    "calendar",
    // activity in a calendar client (gcal)
    "form_input",
    // typed into a (non-sensitive) form field
    "selection"
    // selected / highlighted text
  ]);
  var SOURCES = Object.freeze({
    GMAIL: "gmail",
    GCAL: "gcal",
    MEDIUM: "medium",
    SUBSTACK: "substack",
    ARXIV: "arxiv",
    SEARCH: "search",
    WEB: "web"
  });
  function makeEvent(type, fields = {}) {
    return {
      v: SCHEMA_VERSION,
      type,
      ts: fields.ts ?? Date.now(),
      url: fields.url ?? null,
      domain: fields.domain ?? null,
      title: fields.title ?? null,
      source: fields.source ?? SOURCES.WEB,
      data: fields.data ?? {},
      metrics: fields.metrics ?? {},
      // { dwellMs, scrollPct, readPct }
      redacted: Boolean(fields.redacted)
    };
  }

  // extension/src/recognizers.js
  function domainOf(href) {
    try {
      return new URL(href).hostname.replace(/^www\./, "");
    } catch {
      return null;
    }
  }
  var EMAIL_RE = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi;
  var CARD_RE = /\b(?:\d[ -]?){13,19}\b/g;
  var SSN_RE = /\b\d{3}-\d{2}-\d{4}\b/g;
  var LONG_NUM_RE = /\b\d{9,}\b/g;
  function redactString(input) {
    if (typeof input !== "string" || !input) return { value: input ?? null, redacted: false, kinds: [] };
    const kinds = [];
    let value = input;
    if (EMAIL_RE.test(value)) {
      kinds.push("email");
      value = value.replace(EMAIL_RE, "[email]");
    }
    if (CARD_RE.test(value)) {
      kinds.push("card");
      value = value.replace(CARD_RE, "[card]");
    }
    if (SSN_RE.test(value)) {
      kinds.push("ssn");
      value = value.replace(SSN_RE, "[ssn]");
    }
    if (LONG_NUM_RE.test(value)) {
      kinds.push("number");
      value = value.replace(LONG_NUM_RE, "[number]");
    }
    EMAIL_RE.lastIndex = CARD_RE.lastIndex = SSN_RE.lastIndex = LONG_NUM_RE.lastIndex = 0;
    return { value, redacted: kinds.length > 0, kinds };
  }
  var SEARCH_HOSTS = {
    "google.": "google",
    "bing.com": "bing",
    "duckduckgo.com": "duckduckgo",
    "search.brave.com": "brave",
    "ecosia.org": "ecosia"
  };
  function classify(loc) {
    const host = (loc.hostname || domainOf(loc.href) || "").toLowerCase();
    const path = loc.pathname || "";
    if (host === "mail.google.com") return { source: SOURCES.GMAIL, kind: "email" };
    if (host === "calendar.google.com") return { source: SOURCES.GCAL, kind: "calendar" };
    for (const [frag, engine] of Object.entries(SEARCH_HOSTS)) {
      if (host.includes(frag) && (path.includes("/search") || loc.search?.includes("q=") || engine !== "google"))
        return { source: SOURCES.SEARCH, kind: "search", engine };
    }
    if (host.endsWith("medium.com") || host === "medium.com") return { source: SOURCES.MEDIUM, kind: "reading" };
    if (host.endsWith("substack.com")) return { source: SOURCES.SUBSTACK, kind: "reading" };
    if (host === "arxiv.org" || host.endsWith(".arxiv.org")) return { source: SOURCES.ARXIV, kind: "reading" };
    return { source: SOURCES.WEB, kind: "page" };
  }
  function extractSearch(loc, doc) {
    const c = classify(loc);
    if (c.source !== SOURCES.SEARCH) return null;
    let query = null;
    try {
      query = new URL(loc.href).searchParams.get("q");
    } catch {
    }
    if (!query && doc) {
      const box = doc.querySelector('input[name="q"], input[type="search"]');
      query = box?.value || null;
    }
    if (!query) return null;
    const { value } = redactString(query.trim());
    return { engine: c.engine, query: value };
  }

  // extension/src/config.js
  var DEFAULTS = {
    backendUrl: true ? "http://localhost:8088" : "http://localhost:8088",
    appToken: true ? "dev-token" : "dev-token"
  };

  // extension/src/background.js
  var STORE_KEY = "nidra_events";
  var CFG_KEY = "nidra_config";
  var MAX_EVENTS = 2e3;
  var DEFAULT_CFG = {
    paused: false,
    collectorUrl: "http://localhost:8799",
    // local Node mirror; off if server not running
    // Pragya backend (the real "our server"): events ingest to the BrowserActivity
    // connector and Dream calls the backend dreamer. Defaults live in config.js so
    // the extension works with no manual setup. appToken = the app's API_AUTH_TOKEN
    // (one token for both ingest and dream).
    backendUrl: DEFAULTS.backendUrl,
    appToken: DEFAULTS.appToken,
    denylist: [
      "chase.com",
      "bankofamerica.com",
      "wellsfargo.com",
      "paypal.com",
      "1password.com",
      "lastpass.com",
      "bitwarden.com",
      "accounts.google.com"
    ],
    captureForms: true,
    captureSelections: true,
    backfillDays: 3
  };
  var writeChain = Promise.resolve();
  async function getCfg() {
    const o = await api.storage.local.get(CFG_KEY);
    return { ...DEFAULT_CFG, ...o[CFG_KEY] || {} };
  }
  async function setCfg(patch) {
    const next = { ...await getCfg(), ...patch };
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
  function postToCollector(cfg, ev) {
    if (cfg.backendUrl) {
      fetch(cfg.backendUrl.replace(/\/$/, "") + "/connectors/browser_activity/ingest", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          ...cfg.appToken ? { authorization: "Bearer " + cfg.appToken } : {}
        },
        body: JSON.stringify({ events: [ev] })
      }).catch(() => {
      });
      return;
    }
    if (!cfg.collectorUrl) return;
    fetch(cfg.collectorUrl + "/events", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(ev)
    }).catch(() => {
    });
  }
  async function updateBadge(n) {
    try {
      await api.action.setBadgeText({ text: n ? String(Math.min(n, 9999)) : "" });
      await api.action.setBadgeBackgroundColor({ color: "#4f46e5" });
    } catch {
    }
  }
  function addEvent(ev) {
    writeChain = writeChain.then(async () => {
      const cfg = await getCfg();
      if (cfg.paused) return;
      let arr = upsert(await getEvents(), ev);
      if (arr.length > MAX_EVENTS) arr = arr.slice(-MAX_EVENTS);
      await api.storage.local.set({ [STORE_KEY]: arr });
      await updateBadge(arr.length);
      postToCollector(cfg, ev);
    }).catch(() => {
    });
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
          writeChain = writeChain.then(async () => {
            await api.storage.local.set({ [STORE_KEY]: [] });
            await updateBadge(0);
          }).catch(() => {
          });
          await writeChain;
          sendResponse({ ok: true });
          break;
        default:
          sendResponse({ ok: false });
      }
    })();
    return true;
  });
  async function backfill() {
    try {
      if (!api.history?.search) return;
      const cfg = await getCfg();
      const since = Date.now() - cfg.backfillDays * 864e5;
      const items = await api.history.search({ text: "", startTime: since, maxResults: 500 });
      const isDeny = (h) => cfg.denylist.some((d) => h.replace(/^www\./, "") === d || h.endsWith("." + d));
      for (const it of items) {
        if (!it.url) continue;
        let u;
        try {
          u = new URL(it.url);
        } catch {
          continue;
        }
        if (isDeny(u.hostname)) continue;
        const loc = { href: it.url, hostname: u.hostname, pathname: u.pathname, search: u.search, hash: u.hash };
        const c = classify(loc);
        let ev;
        if (c.source === "search") {
          const s = extractSearch(loc, null);
          if (!s?.query) continue;
          ev = makeEvent("search", { ts: it.lastVisitTime || Date.now(), url: it.url, domain: domainOf(it.url), title: it.title || null, source: "search", data: s, redacted: true });
        } else {
          const type = c.kind === "reading" ? "reading" : "pageview";
          ev = makeEvent(type, {
            ts: it.lastVisitTime || Date.now(),
            url: it.url,
            domain: domainOf(it.url),
            title: it.title || null,
            source: c.source,
            data: type === "reading" ? { title: it.title || null, tags: [], wordCount: 0 } : {}
          });
        }
        ev.id = "hist:" + it.url;
        ev.backfill = true;
        await addEvent(ev);
      }
    } catch {
    }
  }
  async function flushAll() {
    const cfg = await getCfg();
    if (!cfg.backendUrl) return;
    const events = await getEvents();
    if (!events.length) return;
    fetch(cfg.backendUrl.replace(/\/$/, "") + "/connectors/browser_activity/ingest", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...cfg.appToken ? { authorization: "Bearer " + cfg.appToken } : {}
      },
      body: JSON.stringify({ events })
    }).catch(() => {
    });
  }
  api.runtime.onInstalled.addListener(() => {
    backfill();
    flushAll();
  });
  api.runtime.onStartup?.addListener?.(() => {
    backfill();
    flushAll();
  });
})();
