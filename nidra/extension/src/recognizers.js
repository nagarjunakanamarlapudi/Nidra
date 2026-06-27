// Recognizers: turn a page (Document + location) into structured activity.
// Pure functions — they take an explicit `doc` and `loc` so they run identically
// in the content script (real DOM) and in tests (jsdom). No browser globals.

import { makeEvent, SOURCES } from "./schema.js";

// ----------------------------- helpers -----------------------------

export function domainOf(href) {
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
      /* ignore malformed ld+json */
    }
  }
  return out;
}

export function wordCount(text) {
  if (!text) return 0;
  const t = text.replace(/\s+/g, " ").trim();
  return t ? t.split(" ").length : 0;
}

function visibleText(doc) {
  const root =
    doc.querySelector("article") ||
    doc.querySelector("main") ||
    doc.querySelector('[role="main"]') ||
    doc.body;
  if (!root) return "";
  const clone = root.cloneNode(true);
  for (const el of clone.querySelectorAll("script,style,noscript,nav,header,footer,aside,form"))
    el.remove();
  return clone.textContent || "";
}

// ----------------------------- redaction -----------------------------

const EMAIL_RE = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi;
const CARD_RE = /\b(?:\d[ -]?){13,19}\b/g; // credit-card-ish runs
const SSN_RE = /\b\d{3}-\d{2}-\d{4}\b/g;
const LONG_NUM_RE = /\b\d{9,}\b/g; // account/phone-ish

/** Mask PII inside a free-text string. Returns {value, redacted, kinds}. */
export function redactString(input) {
  if (typeof input !== "string" || !input) return { value: input ?? null, redacted: false, kinds: [] };
  const kinds = [];
  let value = input;
  if (EMAIL_RE.test(value)) { kinds.push("email"); value = value.replace(EMAIL_RE, "[email]"); }
  if (CARD_RE.test(value)) { kinds.push("card"); value = value.replace(CARD_RE, "[card]"); }
  if (SSN_RE.test(value)) { kinds.push("ssn"); value = value.replace(SSN_RE, "[ssn]"); }
  if (LONG_NUM_RE.test(value)) { kinds.push("number"); value = value.replace(LONG_NUM_RE, "[number]"); }
  // reset lastIndex on the global regexes we .test()ed above
  EMAIL_RE.lastIndex = CARD_RE.lastIndex = SSN_RE.lastIndex = LONG_NUM_RE.lastIndex = 0;
  return { value, redacted: kinds.length > 0, kinds };
}

const SENSITIVE_NAME_RE =
  /(pass|pwd|card|cc-|cvv|cvc|ssn|secret|otp|\bpin\b|security|account.?number|routing|token|auth)/i;

/** Should we refuse to capture this input's value at all? */
export function isSensitiveInput(el) {
  if (!el) return false;
  const type = (el.getAttribute("type") || el.type || "").toLowerCase();
  if (["password", "hidden"].includes(type)) return true;
  const ac = (el.getAttribute("autocomplete") || "").toLowerCase();
  if (/cc-|current-password|new-password|one-time-code/.test(ac)) return true;
  const hay = [el.name, el.id, el.getAttribute?.("aria-label"), el.getAttribute?.("placeholder")]
    .filter(Boolean)
    .join(" ");
  return SENSITIVE_NAME_RE.test(hay);
}

/** Describe a form field for capture, redacting/skipping sensitive ones. */
export function describeInput(el, { maxLen = 200 } = {}) {
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

// ----------------------------- classify -----------------------------

const SEARCH_HOSTS = {
  "google.": "google",
  "bing.com": "bing",
  "duckduckgo.com": "duckduckgo",
  "search.brave.com": "brave",
  "ecosia.org": "ecosia",
};

export function classify(loc) {
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

// ----------------------------- search -----------------------------

export function extractSearch(loc, doc) {
  const c = classify(loc);
  if (c.source !== SOURCES.SEARCH) return null;
  let query = null;
  try {
    query = new URL(loc.href).searchParams.get("q");
  } catch {
    /* fall through */
  }
  if (!query && doc) {
    const box = doc.querySelector('input[name="q"], input[type="search"]');
    query = box?.value || null;
  }
  if (!query) return null;
  const { value } = redactString(query.trim());
  return { engine: c.engine, query: value };
}

// ----------------------------- article / reading -----------------------------

export function extractArticle(doc) {
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

  const title =
    metaContent(doc, 'meta[property="og:title"]') ||
    (ldArticle && (ldArticle.headline || ldArticle.name)) ||
    doc.querySelector("h1")?.textContent?.trim() ||
    (doc.title || "").trim() ||
    null;

  let author =
    metaContent(doc, 'meta[name="author"]') ||
    doc.querySelector('[rel="author"], a[data-testid="authorName"], .author')?.textContent?.trim() ||
    null;
  if (!author && ldArticle && ldArticle.author) {
    const a = ldArticle.author;
    author = Array.isArray(a) ? a.map((x) => x.name || x).join(", ") : a.name || a;
  }

  const tags = new Set();
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
    estReadMin: Math.max(1, Math.round(words / 200)),
  };
}

// ----------------------------- email (gmail) -----------------------------

export function extractEmail(doc, loc) {
  const c = classify(loc);
  if (c.source !== SOURCES.GMAIL) return null;
  const hash = (loc.hash || "").toLowerCase();
  let action = "list";
  if (/[?#&]compose|compose=/.test(hash) || doc.querySelector('[role="dialog"] [aria-label*="Message Body" i]'))
    action = "compose";
  else if (doc.querySelector("[data-thread-id], .nidra-thread, h2.hP")) action = "read";

  // Subject is useful signal; addresses are not — redact addresses, keep subject.
  const subjectEl = doc.querySelector("h2.hP, .nidra-subject, [data-test='subject']");
  const subject = subjectEl ? redactString(subjectEl.textContent.trim()).value : null;

  const folderEl = doc.querySelector(".nidra-folder, [aria-label='Folder']");
  const folder = folderEl?.textContent?.trim() || hash.replace(/[#?].*/, "").replace("#", "") || null;

  const participants = doc.querySelectorAll(".nidra-participant, .gD").length || null;
  return { action, subject, folder, participants };
}

// ----------------------------- calendar (gcal) -----------------------------

export function extractCalendar(doc, loc) {
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
  const eventTitle = eventTitleEl
    ? redactString((eventTitleEl.value || eventTitleEl.textContent || "").trim()).value
    : null;
  const eventTimeEl = doc.querySelector(".nidra-event-time, [data-test='event-time']");
  const eventTime = eventTimeEl?.textContent?.trim() || null;

  return { view, action: creating ? "create" : "view", eventTitle, eventTime };
}

// ----------------------------- top-level -----------------------------

/**
 * Analyze the current page into ONE primary event describing what it is.
 * The content script enriches the returned event with behavior metrics
 * (dwell, scroll) and emits separate search/form/selection events live.
 */
export function analyzePage(doc, loc, { ts } = {}) {
  const { source } = classify(loc);
  const base = {
    ts,
    url: loc.href,
    domain: domainOf(loc.href),
    title: (doc.title || "").trim() || null,
    source,
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
