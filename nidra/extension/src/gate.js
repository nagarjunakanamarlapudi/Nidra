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
  if (!DECISION_TYPES.has(event.type)) return event; // existing types: already-redacted passthrough

  const d = event.data || {};

  // 1. Allowlist the control kind (impression/interaction carry one; action does not).
  if (event.type !== "action" && !SAFE_CONTROLS.has(d.control)) return null;

  // 2. Sensitive section/label → DROP the whole event.
  if (SENSITIVE_CTX.test(`${d.group || ""} ${d.label || ""}`)) return null;

  // 3. Instrument identifier in the label → DROP (covers "Visa ••4242", "•••• 1111").
  if (INSTRUMENT.test(d.label || "")) return null;

  // 4. Treat label/group as untrusted free text — redact. If a label collapses to
  //    pure PII, drop it rather than emit a bare "[email]"/"[phone]".
  const label = redactString(d.label || "").value;
  const group = redactString(d.group || "").value;
  if (label && /^\s*\[[^\]]+\]\s*$/.test(label)) return null;

  // 5. Scrub the envelope — a sensitive page leaks regardless of value scrubbing.
  return {
    ...event,
    url: scrubUrl(event.url),
    title: redactString(event.title || "").value,
    data: { ...d, label, group },
  };
}
