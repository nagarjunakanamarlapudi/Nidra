"""Deterministic, regex-only output redactor (Sec-2 of the injection defense).

``GuardedEngine`` runs every LLM output through :func:`scrub_secrets` so that
secret-shaped text can never leave the system -- even if a prompt injection
coaxes the model into emitting an API key, private key, or card number.

Design notes:

* **Ordering matters.** Specific, high-confidence shapes (PEM block, AWS/OpenAI
  keys, ``key = value`` assignments) run first; the broad numeric patterns run
  last so they can't piecemeal-clobber a structured secret. The PEM block is
  first of all so its multi-line base64 body is collapsed to a single token
  rather than nibbled by the numeric rules.
* **Idempotent.** ``[REDACTED]`` contains no secret shape, so a second pass is a
  no-op: ``scrub_secrets(scrub_secrets(x)) == scrub_secrets(x)``.
* **Prose-safe.** Years, small counts, and ordinary words survive; the numeric
  rules only fire on card-length groups (13-19 digits) or long bare runs
  (>=9 digits). Where catching a secret and sparing prose conflict, we favor
  redaction -- this is a security control on model output, not on user prose.

Pure function, no dependencies beyond :mod:`re`."""

from __future__ import annotations

import re

_REDACTED = "[REDACTED]"

# (pattern, replacement) applied in order. Replacements are plain ``[REDACTED]``
# except the two credential rules, whose replacements keep the leading capture
# group(s) (key/separator, or "Bearer ") and drop the value -- so
# "password = x" -> "password = [REDACTED]" and "Bearer x" -> "Bearer [REDACTED]".
_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    # PEM private-key block -> collapse the whole BEGIN..END block to one token.
    (
        re.compile(
            r"-----BEGIN[A-Z ]*PRIVATE KEY-----.*?-----END[A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        _REDACTED,
    ),
    # AWS access key id (AKIA) and temporary STS credential (ASIA): prefix + 16 upper-alnum.
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}"), _REDACTED),
    # OpenAI-style secret key: sk- + >=20 alnum/hyphen. The hyphen in the class is
    # required to catch modern default formats (sk-proj-, sk-svcacct-, sk-admin-), which
    # otherwise stop at the first hyphen and escape. \b avoids matching sk- inside words
    # like task-/risk-/disk-.
    (re.compile(r"\bsk-[A-Za-z0-9-]{20,}"), _REDACTED),
    # Authorization: Bearer <token> -- the canonical HTTP header is space-separated (no
    # [:=]), so it needs a dedicated rule. Keep "Bearer ", redact the base64url/JWT token
    # (dots separate JWT segments). Case-sensitive "Bearer" per RFC 6750, so prose like
    # "bearer bonds"/"bearer instruments" is left alone.
    (re.compile(r"(\bBearer\s+)[A-Za-z0-9._-]{10,}"), r"\1" + _REDACTED),
    # Generic credential assignment: tolerate optional quotes around the key and value
    # (so JSON like {"password": "x"} is caught), keep the key + separator, and redact
    # only the value group. The value stops at the closing quote/space so the secret
    # can't bleed past it. The (?!\[REDACTED\]) guard keeps the rule idempotent -- without
    # it a second pass would re-match the [REDACTED] token (plus any trailing }/, ) as a
    # fresh value and eat the surrounding punctuation.
    (
        re.compile(
            r"(?i)[\"']?(password|secret|api[_-]?key|token|bearer)[\"']?"
            r"(\s*[:=]\s*)[\"']?(?!\[REDACTED\])([^\"'\s]{6,})[\"']?"
        ),
        r"\1\2" + _REDACTED,
    ),
    # Card-like run: 13-19 digits, optionally grouped by single spaces/dashes.
    (re.compile(r"\b\d(?:[ -]?\d){12,18}\b"), _REDACTED),
    # Long bare account/number run.
    (re.compile(r"\b\d{9,}\b"), _REDACTED),
)


def scrub_secrets(text: str) -> str:
    """Return ``text`` with secret-shaped substrings replaced by ``[REDACTED]``.

    Deterministic and idempotent; leaves ordinary prose (years, small counts,
    plain words) intact. See the module docstring for the rule set and ordering."""
    for pattern, replacement in _RULES:
        text = pattern.sub(replacement, text)
    return text
