"""Single-user bearer-token authentication."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from pragya_assistant.api.deps import get_settings_dep
from pragya_assistant.config import Settings


async def require_token(
    settings: Annotated[Settings, Depends(get_settings_dep)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Require ``Authorization: Bearer <API_AUTH_TOKEN>`` (constant-time compare)."""
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ")
    if not secrets.compare_digest(token, settings.api_auth_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
