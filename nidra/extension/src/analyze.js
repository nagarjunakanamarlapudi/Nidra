// Page analysis: turn a Document into the ONE "primary" event (reading / pageview
// / search / email / calendar). Kept apart from recognizers.js so the heavy
// @mozilla/readability dependency is bundled ONLY into the content script — never
// the service worker (which imports recognizers.js but not this module).
import Defuddle from "defuddle";
import { findMainContent } from "dom-to-semantic-markdown";
import { Readability, isProbablyReaderable } from "@mozilla/readability";

import {
  classify,
  domainOf,
  extractCalendar,
  extractEmail,
  extractSearch,
  redactString,
  wordCount,
} from "./recognizers.js";
import { makeEvent, SOURCES } from "./schema.js";

const CONTENT_CAP = 4000; // max chars of (redacted) page text captured per page
const MIN_ARTICLE_WORDS = 50;
const DEFUDDLE_OPTIONS = Object.freeze({
  useAsync: false, // content capture must stay local to the current page DOM
  markdown: false,
  removeImages: true,
});

/** Run Mozilla Readability on a CLONE (parse() mutates the DOM). Returns the
 *  parsed article ({ title, byline, siteName, textContent, ... }) or null. */
function parseReadable(doc) {
  try {
    return new Readability(doc.cloneNode(true), { charThreshold: 500 }).parse();
  } catch {
    return null;
  }
}

function supportsDefuddleSelectors(doc) {
  try {
    const probe = doc.createElement("div");
    probe.innerHTML = "<section><p>x</p></section>";
    probe.querySelector("section:not(:has(img))");
    return true;
  } catch {
    return false;
  }
}

function parseDefuddle(doc) {
  if (!supportsDefuddleSelectors(doc)) return null;
  try {
    return new Defuddle(doc.cloneNode(true), {
      ...DEFUDDLE_OPTIONS,
      url: doc.location?.href,
    }).parse();
  } catch {
    return null;
  }
}

function textFromHtml(doc, html) {
  if (!html) return "";
  const template = doc.createElement("template");
  template.innerHTML = html;
  return normalizeText(template.content?.textContent || template.textContent || "");
}

function textFromElement(el) {
  if (!el) return "";
  if (typeof el.innerText === "string") return normalizeText(el.innerText);
  const clone = el.cloneNode(true);
  for (const node of clone.querySelectorAll?.("script,style,noscript,template") || []) node.remove();
  return normalizeText(clone.textContent || "");
}

function normalizeText(text) {
  return (text || "").replace(/\s+/g, " ").trim();
}

function firstUsefulText(...values) {
  for (const value of values) {
    const text = normalizeText(value);
    if (wordCount(text) >= MIN_ARTICLE_WORDS) return text;
  }
  return normalizeText(values.find(Boolean) || "");
}

function capAndRedact(text) {
  return redactString(text.slice(0, CONTENT_CAP + 64)).value.slice(0, CONTENT_CAP) || null;
}

function mainContentRoot(doc) {
  try {
    return findMainContent(doc) || doc.querySelector("main,[role='main']") || doc.body;
  } catch {
    return doc.querySelector("main,[role='main']") || doc.body;
  }
}

/** Plain text of the main content region, minus chrome/forms — fallback for
 *  non-article pages (Readability declines those). */
function visibleText(doc) {
  return textFromElement(mainContentRoot(doc));
}

export function extractPageContent(doc) {
  const text = visibleText(doc);
  return {
    wordCount: wordCount(text),
    content: capAndRedact(text),
  };
}

/** Capture the page's readable text + article metadata. `content` is redacted
 *  (cards/SSNs masked) and capped; redaction runs over a small margin past the
 *  cap so a card/SSN straddling the boundary can't leak a partial run. */
export function extractArticle(doc) {
  // Defuddle is a browser-extension-oriented main-content extractor. Readability
  // remains the conservative article classifier and fallback metadata source.
  const art = isProbablyReaderable(doc) ? parseReadable(doc) : null;
  if (!art) return { isArticle: false, ...extractPageContent(doc) };

  const defuddled = parseDefuddle(doc);
  const text = firstUsefulText(textFromHtml(doc, defuddled?.content), art?.textContent || "");
  const words = wordCount(text);
  const content = capAndRedact(text);

  if (words < MIN_ARTICLE_WORDS) return { isArticle: false, ...extractPageContent(doc) };

  return {
    isArticle: true,
    title: normalizeText(defuddled?.title || art?.title || doc.title) || null,
    author: normalizeText(defuddled?.author || art?.byline) || null,
    siteName: normalizeText(defuddled?.site || art?.siteName) || null,
    wordCount: words,
    content,
  };
}

/**
 * Analyze the current page into ONE primary event describing what it is.
 * The content script enriches it with behavior metrics (dwell, scroll) and
 * emits separate search/form/selection events live.
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

  return makeEvent("pageview", { ...base, data: { wordCount: art.wordCount, content: art.content } });
}
