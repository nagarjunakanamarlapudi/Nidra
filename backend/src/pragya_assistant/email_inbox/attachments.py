"""Extract text from email attachments (PDF / Office / etc.) via MarkItDown.

Runs in-memory (a BytesIO stream) — the attachment bytes are never written to
disk, keeping the read-only / nothing-stored-locally property. One library
covers PDF, Word, Excel, PowerPoint, HTML, CSV, and images.
"""

from __future__ import annotations

import io
import pathlib

from markitdown import MarkItDown, StreamInfo

_md = MarkItDown()
_MAX_CHARS = 8000  # cap per attachment so a chat/digest reply stays tidy


def extract_attachment(filename: str, content_type: str, payload: bytes) -> str:
    extension = pathlib.Path(filename or "").suffix.lower() or None
    info = StreamInfo(mimetype=content_type or None, extension=extension, filename=filename or None)
    try:
        result = _md.convert_stream(io.BytesIO(payload), stream_info=info)
        text = (result.text_content or "").strip()
    except Exception as exc:  # extraction is best-effort; never crash the email read
        return f"(could not read attachment {filename!r}: {exc})"
    if not text:
        return f"({filename!r}: no extractable text — likely a scanned/image file needing OCR)"
    if len(text) > _MAX_CHARS:
        return text[:_MAX_CHARS] + "\n…[truncated]"
    return text
