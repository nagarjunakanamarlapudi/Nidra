(() => {
  // extension/src/browser-api.js
  var api = typeof globalThis.browser !== "undefined" && globalThis.browser?.runtime ? globalThis.browser : globalThis.chrome;

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
  function metaContent(doc, selector, attr = "content") {
    const el = doc.querySelector(selector);
    return el ? (el.getAttribute(attr) || "").trim() || null : null;
  }
  function parseJsonLd(doc) {
    const out = [];
    for (const s of doc.querySelectorAll('script[type="application/ld+json"]')) {
      try {
        const parsed = JSON.parse(s.textContent);
        if (Array.isArray(parsed)) out.push(...parsed);
        else if (parsed && Array.isArray(parsed["@graph"])) out.push(...parsed["@graph"]);
        else if (parsed) out.push(parsed);
      } catch {
      }
    }
    return out;
  }
  function wordCount(text) {
    if (!text) return 0;
    const t = text.replace(/\s+/g, " ").trim();
    return t ? t.split(" ").length : 0;
  }
  function visibleText(doc) {
    const root = doc.querySelector("article") || doc.querySelector("main") || doc.querySelector('[role="main"]') || doc.body;
    if (!root) return "";
    const clone = root.cloneNode(true);
    for (const el of clone.querySelectorAll("script,style,noscript,nav,header,footer,aside,form"))
      el.remove();
    return clone.textContent || "";
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
  var SENSITIVE_NAME_RE = /(pass|pwd|card|cc-|cvv|cvc|ssn|secret|otp|\bpin\b|security|account.?number|routing|token|auth)/i;
  function isSensitiveInput(el) {
    if (!el) return false;
    const type = (el.getAttribute("type") || el.type || "").toLowerCase();
    if (["password", "hidden"].includes(type)) return true;
    const ac = (el.getAttribute("autocomplete") || "").toLowerCase();
    if (/cc-|current-password|new-password|one-time-code/.test(ac)) return true;
    const hay = [el.name, el.id, el.getAttribute?.("aria-label"), el.getAttribute?.("placeholder")].filter(Boolean).join(" ");
    return SENSITIVE_NAME_RE.test(hay);
  }
  function describeInput(el, { maxLen = 200 } = {}) {
    const type = (el.getAttribute("type") || el.type || "text").toLowerCase();
    const name = el.name || el.id || el.getAttribute?.("aria-label") || type;
    const isSearch = type === "search" || el.name === "q" || el.getAttribute?.("role") === "searchbox";
    if (isSensitiveInput(el)) {
      return { name, kind: "sensitive", valueLength: (el.value || "").length, value: null, redacted: true };
    }
    const raw = (el.value || "").slice(0, maxLen);
    const { value, redacted } = redactString(raw);
    return { name, kind: isSearch ? "search" : type, valueLength: (el.value || "").length, value, redacted };
  }
  var SEARCH_HOSTS = {
    "google.": "google",
    "bing.com": "bing",
    "duckduckgo.com": "duckduckgo",
    "search.brave.com": "brave",
    "ecosia.org": "ecosia"
  };
  function classify(loc) {
    const host2 = (loc.hostname || domainOf(loc.href) || "").toLowerCase();
    const path = loc.pathname || "";
    if (host2 === "mail.google.com") return { source: SOURCES.GMAIL, kind: "email" };
    if (host2 === "calendar.google.com") return { source: SOURCES.GCAL, kind: "calendar" };
    for (const [frag, engine] of Object.entries(SEARCH_HOSTS)) {
      if (host2.includes(frag) && (path.includes("/search") || loc.search?.includes("q=") || engine !== "google"))
        return { source: SOURCES.SEARCH, kind: "search", engine };
    }
    if (host2.endsWith("medium.com") || host2 === "medium.com") return { source: SOURCES.MEDIUM, kind: "reading" };
    if (host2.endsWith("substack.com")) return { source: SOURCES.SUBSTACK, kind: "reading" };
    if (host2 === "arxiv.org" || host2.endsWith(".arxiv.org")) return { source: SOURCES.ARXIV, kind: "reading" };
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
  function extractArticle(doc) {
    const ld = parseJsonLd(doc);
    const ldArticle = ld.find((x) => {
      const t = x && x["@type"];
      const types = Array.isArray(t) ? t : [t];
      return types.some((tt) => /Article|BlogPosting|NewsArticle|Report/i.test(String(tt || "")));
    });
    const ogType = metaContent(doc, 'meta[property="og:type"]');
    const text = visibleText(doc);
    const words = wordCount(text);
    const hasArticleEl = !!doc.querySelector("article");
    const isArticle = Boolean(ldArticle) || /article/i.test(ogType || "") || hasArticleEl || words > 400;
    if (!isArticle) return { isArticle: false, wordCount: words };
    const title = metaContent(doc, 'meta[property="og:title"]') || ldArticle && (ldArticle.headline || ldArticle.name) || doc.querySelector("h1")?.textContent?.trim() || (doc.title || "").trim() || null;
    let author = metaContent(doc, 'meta[name="author"]') || doc.querySelector('[rel="author"], a[data-testid="authorName"], .author')?.textContent?.trim() || null;
    if (!author && ldArticle && ldArticle.author) {
      const a = ldArticle.author;
      author = Array.isArray(a) ? a.map((x) => x.name || x).join(", ") : a.name || a;
    }
    const tags = /* @__PURE__ */ new Set();
    const kw = metaContent(doc, 'meta[name="keywords"]');
    if (kw) kw.split(",").forEach((t) => t.trim() && tags.add(t.trim().toLowerCase()));
    for (const m of doc.querySelectorAll('meta[property="article:tag"]')) {
      const v = (m.getAttribute("content") || "").trim();
      if (v) tags.add(v.toLowerCase());
    }
    if (ldArticle && ldArticle.keywords) {
      const ks = Array.isArray(ldArticle.keywords) ? ldArticle.keywords : String(ldArticle.keywords).split(",");
      ks.forEach((t) => String(t).trim() && tags.add(String(t).trim().toLowerCase()));
    }
    return {
      isArticle: true,
      title: title || null,
      author: author || null,
      siteName: metaContent(doc, 'meta[property="og:site_name"]'),
      tags: [...tags].slice(0, 12),
      wordCount: words,
      estReadMin: Math.max(1, Math.round(words / 200))
    };
  }
  function extractEmail(doc, loc) {
    const c = classify(loc);
    if (c.source !== SOURCES.GMAIL) return null;
    const hash = (loc.hash || "").toLowerCase();
    let action = "list";
    if (/[?#&]compose|compose=/.test(hash) || doc.querySelector('[role="dialog"] [aria-label*="Message Body" i]'))
      action = "compose";
    else if (doc.querySelector("[data-thread-id], .nidra-thread, h2.hP")) action = "read";
    const subjectEl = doc.querySelector("h2.hP, .nidra-subject, [data-test='subject']");
    const subject = subjectEl ? redactString(subjectEl.textContent.trim()).value : null;
    const folderEl = doc.querySelector(".nidra-folder, [aria-label='Folder']");
    const folder = folderEl?.textContent?.trim() || hash.replace(/[#?].*/, "").replace("#", "") || null;
    const participants = doc.querySelectorAll(".nidra-participant, .gD").length || null;
    return { action, subject, folder, participants };
  }
  function extractCalendar(doc, loc) {
    const c = classify(loc);
    if (c.source !== SOURCES.GCAL) return null;
    const path = (loc.pathname || "").toLowerCase();
    let view = "unknown";
    for (const v of ["day", "week", "month", "agenda", "year"]) if (path.includes("/r/" + v) || path.endsWith("/" + v)) view = v;
    const creating = !!doc.querySelector(
      ".nidra-event-edit, [aria-label*='Add title' i], input[aria-label*='title' i]"
    );
    const eventTitleEl = doc.querySelector(
      ".nidra-event-title, input[aria-label*='title' i], [data-test='event-title']"
    );
    const eventTitle = eventTitleEl ? redactString((eventTitleEl.value || eventTitleEl.textContent || "").trim()).value : null;
    const eventTimeEl = doc.querySelector(".nidra-event-time, [data-test='event-time']");
    const eventTime = eventTimeEl?.textContent?.trim() || null;
    return { view, action: creating ? "create" : "view", eventTitle, eventTime };
  }
  function analyzePage(doc, loc, { ts } = {}) {
    const { source } = classify(loc);
    const base = {
      ts,
      url: loc.href,
      domain: domainOf(loc.href),
      title: (doc.title || "").trim() || null,
      source
    };
    if (source === SOURCES.SEARCH) {
      const s = extractSearch(loc, doc);
      if (s) return makeEvent("search", { ...base, data: s, redacted: true });
    }
    if (source === SOURCES.GMAIL) {
      const e = extractEmail(doc, loc);
      if (e) return makeEvent("email", { ...base, data: e, redacted: true });
    }
    if (source === SOURCES.GCAL) {
      const cal = extractCalendar(doc, loc);
      if (cal) return makeEvent("calendar", { ...base, data: cal, redacted: true });
    }
    const art = extractArticle(doc);
    if (art.isArticle) return makeEvent("reading", { ...base, data: art });
    return makeEvent("pageview", { ...base, data: { wordCount: art.wordCount } });
  }

  // extension/src/content.js
  var DEFAULT_DENYLIST = [
    "chase.com",
    "bankofamerica.com",
    "wellsfargo.com",
    "paypal.com",
    "1password.com",
    "lastpass.com",
    "bitwarden.com",
    "accounts.google.com"
  ];
  var cfg = { paused: false, denylist: DEFAULT_DENYLIST, captureForms: true, captureSelections: true };
  var started = false;
  var pageStart = Date.now();
  var maxScrollPct = 0;
  var currentPageId = null;
  var host = () => location.hostname.replace(/^www\./, "");
  var denylisted = () => cfg.denylist.some((d) => host() === d || host().endsWith("." + d));
  var uuid = () => crypto?.randomUUID ? crypto.randomUUID() : "id-" + Date.now() + "-" + Math.round(performance.now());
  function scrollPct() {
    const h = document.documentElement;
    const denom = h.scrollHeight - h.clientHeight;
    if (denom <= 0) return 1;
    return Math.min(1, Math.max(0, (h.scrollTop || window.scrollY || 0) / denom));
  }
  function send(event) {
    try {
      const r = api.runtime.sendMessage({ type: "nidra-event", event });
      if (r && typeof r.catch === "function") r.catch(() => {
      });
    } catch {
    }
  }
  function emitPrimary(reason) {
    if (cfg.paused || denylisted()) return;
    const ev = analyzePage(document, location, { ts: Date.now() });
    ev.id = currentPageId;
    ev.metrics = {
      dwellMs: Date.now() - pageStart,
      scrollPct: Math.round(maxScrollPct * 100) / 100,
      ...ev.type === "reading" ? { readPct: Math.round(maxScrollPct * 100) / 100 } : {},
      reason
    };
    send(ev);
  }
  function newPage() {
    currentPageId = uuid();
    pageStart = Date.now();
    maxScrollPct = 0;
  }
  addEventListener("scroll", () => {
    maxScrollPct = Math.max(maxScrollPct, scrollPct());
  }, { passive: true });
  addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") emitPrimary("flush");
  });
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
            ts: Date.now(),
            url: location.href,
            domain: host(),
            title: document.title,
            source: classify(location).source,
            data: d,
            redacted: d.redacted
          });
          ev.id = uuid();
          send(ev);
        }
      }
    },
    true
  );
  var selTimer;
  addEventListener("mouseup", () => {
    if (!cfg.captureSelections || cfg.paused || denylisted()) return;
    clearTimeout(selTimer);
    selTimer = setTimeout(() => {
      const sel = String(getSelection?.() || "").trim();
      if (sel.length < 12) return;
      const { value, redacted } = redactString(sel.slice(0, 300));
      const ev = makeEvent("selection", {
        ts: Date.now(),
        url: location.href,
        domain: host(),
        title: document.title,
        source: classify(location).source,
        data: { text: value, length: sel.length },
        redacted
      });
      ev.id = uuid();
      send(ev);
    }, 400);
  });
  var lastUrl = location.href;
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
    history.pushState = function() {
      ps.apply(this, arguments);
      onRoute();
    };
    let moTimer;
    try {
      new MutationObserver(() => {
        clearTimeout(moTimer);
        moTimer = setTimeout(onRoute, 1500);
      }).observe(document.body, { childList: true, subtree: true });
    } catch {
    }
  }
  async function init() {
    if (started) return;
    started = true;
    try {
      const c = await api.runtime.sendMessage({ type: "nidra-getConfig" });
      if (c) cfg = { ...cfg, ...c };
    } catch {
    }
    if (denylisted()) return;
    newPage();
    setTimeout(() => emitPrimary("load"), 600);
    watchSpa();
  }
  init();
})();
