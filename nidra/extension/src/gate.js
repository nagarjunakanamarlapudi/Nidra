// The privacy gate — the single chokepoint every captured event passes through
// before it leaves the page. Semantic-only, allowlist + DROP-by-default for the
// new decision event types; envelope (url/title) scrubbed too. Existing event
// types pass through unchanged (they are already redacted upstream).
import { redactString } from "./recognizers.js";

const DECISION_TYPES = new Set(["interaction", "impression", "action"]);

// Only these control kinds may be captured at all. Anything else → DROP.
const SAFE_CONTROLS = new Set([
  "toggle", "checkbox", "radio", "dropdown", "button",
  "link", "stepper", "slider", "tab", "card", "menuitem",
]);

// A sensitive section/label means "never capture this decision".
const SENSITIVE_CTX =
  /\b(card\s*number|cardnumber|credit\s*card|cvv|cvc|security\s*code|password|passcode|ssn|social\s*security|account\s*number|routing|iban|\bpin\b)\b/i;

// An instrument identifier in a label (masked digits or a card brand) — drop even
// inside an allowed "payment methods" section, while a plain method enum
// ("Apple Pay", "Card") is permitted.
const INSTRUMENT = /(?:•|\*|x){2,}\s*\d{2,}|\b(?:visa|mastercard|amex|american express|discover|maestro)\b/i;

function scrubUrl(url) {
  if (!url) return url ?? null;
  try {
    const u = new URL(url);
    return u.origin + u.pathname; // drop query + fragment (tokens, ids)
  } catch {
    return String(url).split(/[?#]/)[0];
  }
}

/** Gate one event. Returns the (possibly sanitized) event to send, or null to DROP. */
export function gate(event) {
  if (!event) return null;

  // Non-decision events (pageview/reading/search/email/calendar/form_input/
  // selection): values are redacted upstream, but this is the single chokepoint,
  // so scrub the envelope (url query/fragment can hold tokens) and re-redact any
  // captured free-text `content` as a backstop.
  if (!DECISION_TYPES.has(event.type)) {
    const d = event.data || {};
    const title = redactString(event.title || "");
    const content = typeof d.content === "string" ? redactString(d.content) : null;
    const data = content ? { ...d, content: content.value } : d;
    return {
      ...event,
      url: scrubUrl(event.url),
      title: title.value,
      data,
      redacted: Boolean(event.redacted || title.redacted || content?.redacted),
    };
  }

  const d = event.data || {};
  const value = d.value == null ? "" : String(d.value);

  // 1. Allowlist the control kind (impression/interaction carry one; action does not).
  if (event.type !== "action" && !SAFE_CONTROLS.has(d.control)) return null;

  // 2. Sensitive section/label/value → DROP the whole event.
  if (SENSITIVE_CTX.test(`${d.group || ""} ${d.label || ""} ${value}`)) return null;

  // 3. Instrument identifier in the label/value → DROP (covers "Visa ••4242", "•••• 1111").
  if (INSTRUMENT.test(`${d.label || ""} ${value}`)) return null;
  if (value && redactString(value).redacted) return null;

  // 4. Treat label/group as untrusted free text — redact. If a label collapses to
  //    a bare mask like "[card]" or "[ssn]", drop it rather than emit the mask.
  const label = redactString(d.label || "");
  const group = redactString(d.group || "");
  if (label.value && /^\s*\[[^\]]+\]\s*$/.test(label.value)) return null;
  const title = redactString(event.title || "");

  // 5. Scrub the envelope — a sensitive page leaks regardless of value scrubbing.
  return {
    ...event,
    url: scrubUrl(event.url),
    title: title.value,
    data: { ...d, label: label.value, group: group.value },
    redacted: Boolean(event.redacted || title.redacted || label.redacted || group.redacted),
  };
}
