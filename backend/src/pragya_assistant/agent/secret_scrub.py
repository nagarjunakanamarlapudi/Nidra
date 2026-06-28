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
# except the credential-assignment rule, which keeps the key/separator (groups
# 1 and 2) and redacts only the value -- so "password = x" -> "password = [REDACTED]".
_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    # PEM private-key block -> collapse the whole BEGIN..END block to one token.
    (
        re.compile(
            r"-----BEGIN[A-Z ]*PRIVATE KEY-----.*?-----END[A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        _REDACTED,
    ),
    # AWS access key id: AKIA + 16 upper-alnum.
    (re.compile(r"\bAKIA[0-9A-Z]{16}"), _REDACTED),
    # OpenAI-style secret key: sk- + >=20 alnum (\b avoids matching task-/risk- etc.).
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}"), _REDACTED),
    # Generic credential assignment: keep the key + separator, redact the value.
    (
        re.compile(r"(?i)\b(password|secret|api[_-]?key|token|bearer)(\s*[:=]\s*)\S+"),
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
