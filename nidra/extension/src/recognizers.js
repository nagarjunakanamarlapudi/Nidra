// Recognizers: turn a page (Document + location) into structured activity.
// Pure functions — they take an explicit `doc` and `loc` so they run identically
// in the content script (real DOM) and in tests (jsdom). No browser globals.

import { SOURCES } from "./schema.js";

// ----------------------------- helpers -----------------------------

export function domainOf(href) {
  try {
    return new URL(href).hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
}

export function wordCount(text) {
  if (!text) return 0;
  const t = text.replace(/\s+/g, " ").trim();
  return t ? t.split(" ").length : 0;
}

// ----------------------------- redaction -----------------------------

const CARD_RE = /\b(?:\d[ -]?){13,19}\b/g; // credit-card-ish digit runs (Luhn-checked below)
const SSN_RE = /\b\d{3}[\s-]?\d{2}[\s-]?\d{4}\b/g; // dashed, spaced, or bare 9-digit

/** Luhn checksum — only treat a digit run as a card if it actually validates,
 *  so we don't mask phone numbers, order ids, dates, etc. */
function luhnValid(s) {
  const digits = s.replace(/\D/g, "");
  if (digits.length < 13 || digits.length > 19) return false;
  let sum = 0;
  let alt = false;
  for (let i = digits.length - 1; i >= 0; i--) {
    let d = digits.charCodeAt(i) - 48;
    if (alt) { d *= 2; if (d > 9) d -= 9; }
    sum += d;
    alt = !alt;
  }
  return sum % 10 === 0;
}

/** Mask ONLY highly sensitive data — payment cards (Luhn-validated) and SSNs.
 *  Names, emails, phone numbers and addresses are intentionally KEPT: they are
 *  useful signal for the assistant. Returns {value, redacted, kinds}. */
export function redactString(input) {
  if (typeof input !== "string" || !input) return { value: input ?? null, redacted: false, kinds: [] };
  const kinds = [];
  let value = input.replace(CARD_RE, (m) => {
    if (!luhnValid(m)) return m;
    if (!kinds.includes("card")) kinds.push("card");
    return "[card]";
  });
  value = value.replace(SSN_RE, () => {
    if (!kinds.includes("ssn")) kinds.push("ssn");
    return "[ssn]";
  });
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

// --------------------- interactions / impressions ---------------------
// Semantic descriptors for on-page DECISIONS — the abstract role of a control,
// not its raw value. Domain-agnostic: works for any site's options/toggles.

const CONTROL_BY_ROLE = {
  switch: "toggle", checkbox: "checkbox", radio: "radio", combobox: "dropdown",
  listbox: "dropdown", button: "button", link: "link", tab: "tab", menuitem: "menuitem",
  slider: "slider", spinbutton: "stepper", option: "radio",
};

/** Map a DOM element to a control kind (toggle/radio/dropdown/button/...) or null. */
export function controlKind(el) {
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

/** Accessible name of a control: aria-label, associated <label>, or text. */
export function accessibleName(el) {
  if (!el) return "";
  const aria = el.getAttribute?.("aria-label");
  if (aria) return aria.trim();
  // wrapping <label> or label[for=id]
  const lbl = el.closest?.("label");
  if (lbl) return (lbl.textContent || "").replace(/\s+/g, " ").trim();
  const id = el.id;
  if (id && el.ownerDocument) {
    const forLbl = el.ownerDocument.querySelector(`label[for="${id}"]`);
    if (forLbl) return (forLbl.textContent || "").replace(/\s+/g, " ").trim();
  }
  return (el.textContent || el.value || "").replace(/\s+/g, " ").trim();
}

/** The semantic section a control belongs to (fieldset legend / aria group / heading). */
export function sectionLabel(el) {
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
  void role;
  return null;
}

/** Bounded, position-independent key for an element: role+group+label signature.
 *  Stable across re-renders / virtualized list recycling. */
export function elementKey(el) {
  const control = controlKind(el) || "el";
  const group = sectionLabel(el) || "";
  const label = accessibleName(el).slice(0, 80);
  let h = 0;
  const sig = `${control}|${group}|${label}`;
  for (let i = 0; i < sig.length; i++) h = (Math.imul(31, h) + sig.charCodeAt(i)) | 0;
  return `${control}:${(h >>> 0).toString(36)}`;
}

/** Describe a semantic interaction with a control, or null if not a control. */
export function describeInteraction(el) {
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

/** Describe a decision-point impression: a choice element / offer / CTA shown. */
export function describeImpression(el) {
  const control = controlKind(el);
  if (!control) return null;
  return {
    control,
    label: redactString(accessibleName(el).slice(0, 120)).value,
    group: sectionLabel(el),
    elementKey: elementKey(el),
  };
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

// ----------------------------- flow steps -----------------------------

const FLOW_RE =
  /checkout|cart|payment|sign[\s-]?up|register|onboard|wizard|booking|apply|application|survey|quiz|subscribe|\border\b/i;

/** Detect whether the page is a step in a multi-step flow (checkout, signup,
 *  wizard, …). Returns { flow, label, index, of } or null. Heuristic + best-effort. */
export function detectStep(doc, loc) {
  // Match the flow keyword against the PATH only — a querystring (?order=…) or a
  // subdomain (cart.example.com) shouldn't trip it.
  const path = (loc && loc.pathname) || "";
  const flowMatch = FLOW_RE.exec(path);

  // Explicit "Step 2 of 4" text, scoped to a step-ish container when present.
  let index = null;
  let of = null;
  const scope = doc.querySelector('[class*="step" i], [data-step], [role="progressbar"], nav[aria-label*="step" i]');
  const probe = ((scope && scope.textContent) || (doc.body && doc.body.textContent) || "").slice(0, 4000);
  const m = probe.match(/step\s*(\d+)\s*(?:of|\/)\s*(\d+)/i);
  if (m) { index = Number(m[1]); of = Number(m[2]); }

  // A progressbar's aria-valuenow/max — only when it looks like a small step
  // count, not an 0–100 percentage.
  const pb = doc.querySelector('[role="progressbar"]');
  if (pb && index == null) {
    const now = Number(pb.getAttribute("aria-valuenow"));
    const max = Number(pb.getAttribute("aria-valuemax"));
    if (now && max && max <= 12) { index = now; of = max; }
  }

  const current = doc.querySelector('[aria-current="step"]');
  if (!flowMatch && index == null && !current) return null;

  // `flow` is the STABLE flow identity (so maybeStep can tell "entered" from
  // "advanced" across steps) — prefer the path keyword; the per-step text lives
  // in `label`.
  const crumb = doc.querySelector('nav[aria-label*="breadcrumb" i]');
  const flowRaw =
    (flowMatch && flowMatch[0]) ||
    (crumb && crumb.textContent) ||
    (doc.querySelector("h1") && doc.querySelector("h1").textContent) ||
    "flow";
  const labelEl = current || doc.querySelector("h1, h2");
  return {
    flow: redactString(String(flowRaw).toLowerCase().replace(/\s+/g, " ").trim().slice(0, 60)).value,
    label: labelEl ? redactString((labelEl.textContent || "").replace(/\s+/g, " ").trim().slice(0, 80)).value : null,
    index,
    of,
  };
}

