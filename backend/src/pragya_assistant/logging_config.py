"""Structured logging setup (structlog → JSON)."""

from __future__ import annotations

import logging

import structlog


def configure_logging(level: str = "INFO") -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", level=numeric_level)
    # httpx logs each request URL at INFO — which includes the bot token for
    # Telegram calls. Quiet it so tokens don't leak into logs (and reduce noise).
    logging.getLogger("httpx").setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.PrintLoggerFactory(),
        # Off so structlog.testing.capture_logs can intercept; negligible perf cost.
        cache_logger_on_first_use=False,
    )
