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
    "selection",
    // selected / highlighted text
    "impression",
    // a decision-point (choice elements / offers / CTAs) was shown
    "interaction",
    // a semantic click / toggle / select — the decision, never the raw value
    "action"
    // a funnel milestone (reached_checkout / submitted / completed / abandoned)
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
      // { dwellMs, scrollPct, readPct, latencyMs }
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
  var PHONE_RE = /\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b/g;
  var DATE_RE = /\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b/g;
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
    if (PHONE_RE.test(value)) {
      kinds.push("phone");
      value = value.replace(PHONE_RE, "[phone]");
    }
    if (DATE_RE.test(value)) {
      kinds.push("date");
      value = value.replace(DATE_RE, "[date]");
    }
    if (LONG_NUM_RE.test(value)) {
      kinds.push("number");
      value = value.replace(LONG_NUM_RE, "[number]");
    }
    EMAIL_RE.lastIndex = CARD_RE.lastIndex = SSN_RE.lastIndex = 0;
    PHONE_RE.lastIndex = DATE_RE.lastIndex = LONG_NUM_RE.lastIndex = 0;
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
  var CONTROL_BY_ROLE = {
    switch: "toggle",
    checkbox: "checkbox",
    radio: "radio",
    combobox: "dropdown",
    listbox: "dropdown",
    button: "button",
    link: "link",
    tab: "tab",
    menuitem: "menuitem",
    slider: "slider",
    spinbutton: "stepper",
    option: "radio"
  };
  function controlKind(el) {
    if (!el || !el.getAttribute) return null;
    const role = (el.getAttribute("role") || "").toLowerCase();
    if (CONTROL_BY_ROLE[role]) return CONTROL_BY_ROLE[role];
    const tag = (el.tagName || "").toLowerCase();
    const type = (el.getAttribute("type") || el.type || "").toLowerCase();
    if (tag === "select") return "dropdown";
    if (tag === "a") return "link";
    if (tag === "button") return "button";
    if (tag === "input") {
      if (type === "checkbox") return "checkbox";
      if (type === "radio") return "radio";
      if (type === "range") return "slider";
      if (type === "submit" || type === "button") return "button";
    }
    return null;
  }
  function accessibleName(el) {
    if (!el) return "";
    const aria = el.getAttribute?.("aria-label");
    if (aria) return aria.trim();
    const lbl = el.closest?.("label");
    if (lbl) return (lbl.textContent || "").replace(/\s+/g, " ").trim();
    const id = el.id;
    if (id && el.ownerDocument) {
      const forLbl = el.ownerDocument.querySelector(`label[for="${id}"]`);
      if (forLbl) return (forLbl.textContent || "").replace(/\s+/g, " ").trim();
    }
    return (el.textContent || el.value || "").replace(/\s+/g, " ").trim();
  }
  function sectionLabel(el) {
    if (!el || !el.closest) return null;
    const fs = el.closest("fieldset");
    const legend = fs?.querySelector("legend");
    if (legend) return (legend.textContent || "").replace(/\s+/g, " ").trim();
    const group = el.closest('[role="group"], [role="radiogroup"], section, [aria-labelledby]');
    if (group) {
      const labelledby = group.getAttribute?.("aria-labelledby");
      const ref = labelledby && el.ownerDocument?.getElementById(labelledby);
      if (ref) return (ref.textContent || "").replace(/\s+/g, " ").trim();
      const aria = group.getAttribute?.("aria-label");
      if (aria) return aria.trim();
      const heading = group.querySelector?.("h1,h2,h3,h4,legend");
      if (heading) return (heading.textContent || "").replace(/\s+/g, " ").trim();
    }
    return null;
  }
  function checkedState(el) {
    const role = (el.getAttribute?.("role") || "").toLowerCase();
    if (typeof el.checked === "boolean") return el.checked;
    const aria = el.getAttribute?.("aria-checked") ?? el.getAttribute?.("aria-pressed") ?? el.getAttribute?.("aria-selected");
    if (aria != null) return aria === "true";
    return null;
  }
  function elementKey(el) {
    const control = controlKind(el) || "el";
    const group = sectionLabel(el) || "";
    const label = accessibleName(el).slice(0, 80);
    let h = 0;
    const sig = `${control}|${group}|${label}`;
    for (let i = 0; i < sig.length; i++) h = Math.imul(31, h) + sig.charCodeAt(i) | 0;
    return `${control}:${(h >>> 0).toString(36)}`;
  }
  function describeInteraction(el) {
    const control = controlKind(el);
    if (!control) return null;
    const label = redactString(accessibleName(el).slice(0, 120)).value;
    const group = sectionLabel(el);
    const checked = checkedState(el);
    let action = "select";
    let value = null;
    let valueClass = "text_safe";
    if (control === "toggle" || control === "checkbox") {
      action = checked ? "toggle_on" : "toggle_off";
      value = checked ? "on" : "off";
      valueClass = "boolean";
    } else if (control === "radio") {
      action = "choose";
      value = label;
      valueClass = "enum";
    } else if (control === "dropdown") {
      action = "select";
      const sel = el.selectedOptions?.[0]?.textContent || el.value || null;
      value = sel ? redactString(String(sel)).value : null;
      valueClass = "enum";
    } else if (control === "stepper" || control === "slider") {
      action = "step";
      value = el.value ?? null;
      valueClass = "numeric";
    } else {
      action = control === "link" ? "open" : "click";
    }
    return { action, control, label, group, value, valueClass, elementKey: elementKey(el) };
  }
  function describeImpression(el) {
    const control = controlKind(el);
    if (!control) return null;
    return {
      control,
      label: redactString(accessibleName(el).slice(0, 120)).value,
      group: sectionLabel(el),
      elementKey: elementKey(el)
    };
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

  // extension/src/gate.js
  var DECISION_TYPES = /* @__PURE__ */ new Set(["interaction", "impression", "action"]);
  var SAFE_CONTROLS = /* @__PURE__ */ new Set([
    "toggle",
    "checkbox",
    "radio",
    "dropdown",
    "button",
    "link",
    "stepper",
    "slider",
    "tab",
    "card",
    "menuitem"
  ]);
  var SENSITIVE_CTX = /\b(card\s*number|cardnumber|credit\s*card|cvv|cvc|security\s*code|password|passcode|ssn|social\s*security|account\s*number|routing|iban|\bpin\b)\b/i;
  var INSTRUMENT = /(?:•|\*|x){2,}\s*\d{2,}|\b(?:visa|mastercard|amex|american express|discover|maestro)\b/i;
  function scrubUrl(url) {
    if (!url) return url ?? null;
    try {
      const u = new URL(url);
      return u.origin + u.pathname;
    } catch {
      return String(url).split(/[?#]/)[0];
    }
  }
  function gate(event) {
    if (!event) return null;
    if (!DECISION_TYPES.has(event.type)) return event;
    const d = event.data || {};
    if (event.type !== "action" && !SAFE_CONTROLS.has(d.control)) return null;
    if (SENSITIVE_CTX.test(`${d.group || ""} ${d.label || ""}`)) return null;
    if (INSTRUMENT.test(d.label || "")) return null;
    const label = redactString(d.label || "").value;
    const group = redactString(d.group || "").value;
    if (label && /^\s*\[[^\]]+\]\s*$/.test(label)) return null;
    return {
      ...event,
      url: scrubUrl(event.url),
      title: redactString(event.title || "").value,
      data: { ...d, label, group }
    };
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
  var pageStartPerf = 0;
  var maxScrollPct = 0;
  var currentPageId = null;
  var IMPRESSION_CAP = 40;
  var seenKeys = /* @__PURE__ */ new Set();
  var recentInteractions = /* @__PURE__ */ new Map();
  var impressionCount = 0;
  var impressionObserver = null;
  var funnelReached = false;
  var submitted = false;
  var FUNNEL_RE = /checkout|cart|payment|booking|\breview\b|\border\b|subscribe/i;
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
    const gated = gate(event);
    if (!gated) return;
    try {
      const r = api.runtime.sendMessage({ type: "nidra-event", event: gated });
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
    pageStartPerf = performance.now();
    maxScrollPct = 0;
    seenKeys = /* @__PURE__ */ new Set();
    recentInteractions = /* @__PURE__ */ new Map();
    impressionCount = 0;
    funnelReached = false;
    submitted = false;
  }
  var DECISION_CONTROLS = "a,button,select,input,[role=switch],[role=radio],[role=checkbox],[role=button],[role=tab],[role=menuitem],[role=option]";
  function onInteraction(target) {
    if (cfg.paused || denylisted()) return;
    const el = target?.closest?.(DECISION_CONTROLS) || target;
    const desc = describeInteraction(el);
    if (!desc) return;
    const now = performance.now();
    const prev = recentInteractions.get(desc.elementKey);
    if (prev && prev.action === desc.action && now - prev.t < 700) return;
    recentInteractions.set(desc.elementKey, { action: desc.action, t: now });
    const ev = makeEvent("interaction", {
      ts: Date.now(),
      url: location.href,
      domain: host(),
      title: document.title,
      source: classify(location).source,
      data: desc
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
    if (seenKeys.has(desc.elementKey)) return;
    seenKeys.add(desc.elementKey);
    impressionCount += 1;
    const ev = makeEvent("impression", {
      ts: Date.now(),
      url: location.href,
      domain: host(),
      title: document.title,
      source: classify(location).source,
      data: desc
    });
    ev.id = currentPageId + ":" + desc.elementKey;
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
      try {
        impressionObserver.observe(el);
        armed += 1;
      } catch {
      }
    }
  }
  function emitAction(milestone, extra = {}) {
    if (cfg.paused || denylisted()) return;
    const ev = makeEvent("action", {
      ts: Date.now(),
      url: location.href,
      domain: host(),
      title: document.title,
      source: classify(location).source,
      data: { milestone, funnel: "checkout", ...extra }
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
  addEventListener("scroll", () => {
    maxScrollPct = Math.max(maxScrollPct, scrollPct());
  }, { passive: true });
  addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") emitPrimary("flush");
  });
  addEventListener("pagehide", () => {
    emitPrimary("flush");
    if (funnelReached && !submitted) emitAction("abandoned");
  });
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
      submitted = true;
      emitAction("submitted");
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
    setTimeout(() => {
      emitPrimary("spa");
      maybeFunnel();
      armImpressions();
    }, 800);
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
    setTimeout(() => {
      emitPrimary("load");
      maybeFunnel();
      armImpressions();
    }, 600);
    watchSpa();
  }
  init();
})();
