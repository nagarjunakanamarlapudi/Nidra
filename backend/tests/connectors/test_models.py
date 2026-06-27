"""ORM models backing the connectors platform."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pragya_assistant.memory.models import (
    CalendarEvent,
    ConnectorInstance,
    ConnectorOAuthFlow,
)


async def test_connector_instance_roundtrip(session: AsyncSession) -> None:
    inst = ConnectorInstance(
        connector_key="demo",
        enabled=True,
        status="connected",
        config="ciphertext",
        granted_scopes=["a", "b"],
    )
    session.add(inst)
    await session.commit()
    await session.refresh(inst)
    assert inst.id is not None
    assert inst.created_at is not None
    assert inst.updated_at is not None
    assert inst.granted_scopes == ["a", "b"]
    assert inst.last_sync_at is None


async def test_connector_key_is_unique(session: AsyncSession) -> None:
    session.add(ConnectorInstance(connector_key="dup"))
    await session.commit()
    session.add(ConnectorInstance(connector_key="dup"))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_oauth_flow_roundtrip(session: AsyncSession) -> None:
    session.add(ConnectorOAuthFlow(state="xyz", connector_key="demo", code_verifier="verifier"))
    await session.commit()
    got = await session.get(ConnectorOAuthFlow, "xyz")
    assert got is not None
    assert got.code_verifier == "verifier"


async def test_calendar_event_unique_per_connector_uid(session: AsyncSession) -> None:
    session.add(
        CalendarEvent(
            connector_key="google_calendar",
            uid="e1",
            summary="Standup",
            start=dt.datetime(2026, 1, 1, 9, 0),
            all_day=False,
        )
    )
    await session.commit()
    session.add(
        CalendarEvent(
            connector_key="google_calendar",
            uid="e1",
            summary="dup",
            start=dt.datetime(2026, 1, 1, 9, 0),
            all_day=False,
        )
    )
    with pytest.raises(IntegrityError):
        await session.commit()
