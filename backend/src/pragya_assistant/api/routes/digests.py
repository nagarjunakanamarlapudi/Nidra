"""Digest endpoints — list recent digests and trigger one on demand."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from pragya_assistant.agent.prompts import build_weekly_finance_prompt
from pragya_assistant.api.auth import require_token
from pragya_assistant.api.deps import get_digests
from pragya_assistant.api.schemas import DigestOut
from pragya_assistant.digests.service import DigestService
from pragya_assistant.memory.models import Digest

router = APIRouter(tags=["digests"], dependencies=[Depends(require_token)])


def _out(d: Digest) -> DigestOut:
    return DigestOut(id=d.id, content=d.content, delivered=d.delivered, created_at=d.created_at)


@router.get("/digests", response_model=list[DigestOut])
async def list_digests(
    digests: Annotated[DigestService, Depends(get_digests)],
) -> list[DigestOut]:
    return [_out(d) for d in await digests.recent()]


@router.post("/digests/run", response_model=DigestOut)
async def run_digest(
    digests: Annotated[DigestService, Depends(get_digests)],
) -> DigestOut:
    return _out(await digests.run())


@router.post("/digests/run-weekly", response_model=DigestOut)
async def run_weekly_digest(
    digests: Annotated[DigestService, Depends(get_digests)],
) -> DigestOut:
    return _out(await digests.run(build_weekly_finance_prompt))
