"""Egress guard for WebFetch (Sec-4 of the prompt-injection defense).

WebFetch stays available (chat needs web lookups), so rather than removing it we
guard what it can carry *out*. :func:`egress_allowed` is a pure predicate over
the target URL; a ``PreToolUse`` hook in :class:`ClaudeCodeEngine` calls it
before every WebFetch and denies the call when it returns ``False``.

A ``PreToolUse`` hook -- not ``can_use_tool`` -- is the correct mechanism: per
the Claude Agent SDK, ``can_use_tool`` only fires when permission evaluation
reaches "ask", so an allowed/auto-approved WebFetch would never reach it. A
``PreToolUse`` hook fires before *every* tool call.

Two block conditions:

* **Secret-shaped data.** Reuse :func:`scrub_secrets` (don't reinvent secret
  detection); if it would rewrite the URL -- raw or percent-decoded -- the URL
  carries an API key / token / card / PEM / long digit run and must not leave.
* **Bulk encoded blob.** A contiguous run of URL-safe base64url/hex characters
  (``[A-Za-z0-9_-]``) longer than ~64 chars in the path/query/fragment is the
  signature of bulk-data exfiltration, not a lookup. Structural URL delimiters
  (``/ ? & = # . + % :`` ...) are not in the class, so they break runs -- a deep
  path of short segments is never mistaken for a blob. Checked on the raw target
  and its percent-decoded form, so ``?x=%41%41...`` is caught too.

Normal lookups -- ``https://en.wikipedia.org/wiki/Kyoto``, a short search query,
an underscore-separated title, even a ~64-char opaque id -- pass. Pure function,
``re`` + ``urllib`` only."""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

from pragya_assistant.agent.secret_scrub import scrub_secrets

# Block a contiguous URL-safe base64url/hex run longer than this. ~64 tolerates
# real opaque ids (a SHA-256 hex is exactly 64) while a bulk exfil blob -- far
# longer -- is caught.
_MAX_BLOB = 64
_BLOB_RUN = re.compile(r"[A-Za-z0-9_-]+")


def egress_allowed(url: str) -> tuple[bool, str]:
    """Return ``(allowed, reason)`` for fetching ``url``.

    ``(True, "")`` for ordinary lookup URLs; ``(False, reason)`` when the URL
    carries secret-shaped data or a bulk encoded blob (data exfiltration). See
    the module docstring for the rule set."""
    parts = urlsplit(url)
    target = f"{parts.path}?{parts.query}#{parts.fragment}"
    decoded = unquote(target)

    # 1. Secret-shaped data -- in the raw URL (covers host too) or the decoded
    #    path/query (catches percent-encoded keys/tokens).
    if scrub_secrets(url) != url or scrub_secrets(decoded) != decoded:
        return False, "URL carries secret-shaped data"

    # 2. Bulk base64/hex blob in the path/query/fragment, raw or decoded.
    if _has_bulk_blob(target) or _has_bulk_blob(decoded):
        return False, f"URL carries a bulk encoded blob (>{_MAX_BLOB} chars)"

    return True, ""


def _has_bulk_blob(text: str) -> bool:
    return any(len(m.group()) > _MAX_BLOB for m in _BLOB_RUN.finditer(text))
