"""Uvicorn entrypoint: ``uvicorn pragya_assistant.main:app``."""

from __future__ import annotations

from pragya_assistant.api.app import create_app
from pragya_assistant.config import get_settings

app = create_app(get_settings())
