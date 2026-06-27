"""Persistence for connector instances (encrypted config) and OAuth flows.

The instance store is the credential vault: ``config`` is a JSON blob encrypted
at rest with the shared Fernet key. Plaintext config only ever exists in memory.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterable
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.crypto import decrypt_secret, encrypt_secret
from pragya_assistant.memory.models import (
    ConnectorAccount,
    ConnectorAppCredential,
    ConnectorInstance,
    ConnectorOAuthFlow,
)


class ConnectorInstanceStore:
    """CRUD over ``ConnectorInstance`` with transparent config encryption."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], app_secret_key: str
    ) -> None:
        self._sf = session_factory
        self._key = app_secret_key

    def encrypt_config(self, config: dict[str, Any]) -> str:
        return encrypt_secret(json.dumps(config), self._key)

    def decrypt_config(self, inst: ConnectorInstance) -> dict[str, Any]:
        if not inst.config:
            return {}
        decoded: dict[str, Any] = json.loads(decrypt_secret(inst.config, self._key))
        return decoded

    def accounts(self) -> ConnectorAccountStore:
        """The sibling account store, sharing this store's session + Fernet key."""
        return ConnectorAccountStore(self._sf, self._key)

    async def get(self, key: str) -> ConnectorInstance | None:
        async with self._sf() as s:
            return (
                await s.execute(
                    select(ConnectorInstance).where(ConnectorInstance.connector_key == key)
                )
            ).scalar_one_or_none()

    async def list_all(self) -> list[ConnectorInstance]:
        async with self._sf() as s:
            return list((await s.execute(select(ConnectorInstance))).scalars().all())

    async def list_enabled(self) -> list[ConnectorInstance]:
        async with self._sf() as s:
            stmt = select(ConnectorInstance).where(ConnectorInstance.enabled.is_(True))
            return list((await s.execute(stmt)).scalars().all())

    async def upsert_config(
        self,
        key: str,
        config: dict[str, Any],
        *,
        enabled: bool,
        status: str,
        granted_scopes: Iterable[str] | None = None,
    ) -> ConnectorInstance:
        async with self._sf() as s:
            inst = (
                await s.execute(
                    select(ConnectorInstance).where(ConnectorInstance.connector_key == key)
                )
            ).scalar_one_or_none()
            if inst is None:
                inst = ConnectorInstance(connector_key=key)
                s.add(inst)
            inst.config = self.encrypt_config(config)
            inst.enabled = enabled
            inst.status = status
            if granted_scopes is not None:
                inst.granted_scopes = list(granted_scopes)
            await s.commit()
            await s.refresh(inst)
            return inst

    async def patch_config(self, key: str, partial: dict[str, Any]) -> ConnectorInstance | None:
        async with self._sf() as s:
            inst = (
                await s.execute(
                    select(ConnectorInstance).where(ConnectorInstance.connector_key == key)
                )
            ).scalar_one_or_none()
            if inst is None:
                return None
            current = {} if not inst.config else json.loads(decrypt_secret(inst.config, self._key))
            current.update(partial)
            inst.config = self.encrypt_config(current)
            await s.commit()
            await s.refresh(inst)
            return inst

    async def set_status(self, key: str, status: str, *, last_error: str | None = None) -> None:
        async with self._sf() as s:
            inst = (
                await s.execute(
                    select(ConnectorInstance).where(ConnectorInstance.connector_key == key)
                )
            ).scalar_one_or_none()
            if inst is not None:
                inst.status = status
                inst.last_error = last_error
                await s.commit()

    async def set_last_sync(self, key: str, when: dt.datetime) -> None:
        async with self._sf() as s:
            inst = (
                await s.execute(
                    select(ConnectorInstance).where(ConnectorInstance.connector_key == key)
                )
            ).scalar_one_or_none()
            if inst is not None:
                inst.last_sync_at = when
                await s.commit()

    async def delete(self, key: str) -> None:
        async with self._sf() as s:
            await s.execute(delete(ConnectorInstance).where(ConnectorInstance.connector_key == key))
            await s.commit()


class OAuthFlowStore:
    """Short-lived store for in-flight OAuth authorizations (state + verifier)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def create(self, state: str, connector_key: str, code_verifier: str) -> None:
        async with self._sf() as s:
            s.add(
                ConnectorOAuthFlow(
                    state=state, connector_key=connector_key, code_verifier=code_verifier
                )
            )
            await s.commit()

    async def pop(self, state: str) -> ConnectorOAuthFlow | None:
        """Return the flow for ``state`` and delete it (single-use)."""
        async with self._sf() as s:
            flow = await s.get(ConnectorOAuthFlow, state)
            if flow is None:
                return None
            detached = ConnectorOAuthFlow(
                state=flow.state,
                connector_key=flow.connector_key,
                code_verifier=flow.code_verifier,
                created_at=flow.created_at,
            )
            await s.delete(flow)
            await s.commit()
            return detached

    async def connector_for_state(self, state: str) -> str | None:
        """Peek the connector key for a state without consuming the flow."""
        async with self._sf() as s:
            flow = await s.get(ConnectorOAuthFlow, state)
            return flow.connector_key if flow is not None else None

    async def purge_older_than(self, seconds: int) -> None:
        cutoff = dt.datetime.now(dt.UTC).replace(tzinfo=None) - dt.timedelta(seconds=seconds)
        async with self._sf() as s:
            await s.execute(
                delete(ConnectorOAuthFlow).where(ConnectorOAuthFlow.created_at < cutoff)
            )
            await s.commit()


class AppCredentialStore:
    """Server-level OAuth *app* credentials per provider, encrypted at rest."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], app_secret_key: str
    ) -> None:
        self._sf = session_factory
        self._key = app_secret_key

    async def get(self, provider: str) -> dict[str, str] | None:
        async with self._sf() as s:
            row = await s.get(ConnectorAppCredential, provider)
            if row is None:
                return None
            creds: dict[str, str] = json.loads(decrypt_secret(row.config, self._key))
            return creds

    async def set(self, provider: str, creds: dict[str, str]) -> None:
        encrypted = encrypt_secret(json.dumps(creds), self._key)
        async with self._sf() as s:
            row = await s.get(ConnectorAppCredential, provider)
            if row is None:
                s.add(ConnectorAppCredential(provider=provider, config=encrypted))
            else:
                row.config = encrypted
            await s.commit()

    async def delete(self, provider: str) -> None:
        async with self._sf() as s:
            row = await s.get(ConnectorAppCredential, provider)
            if row is not None:
                await s.delete(row)
                await s.commit()


class ConnectorAccountStore:
    """CRUD over ``ConnectorAccount`` — the N linked accounts of a connector.

    Identity-keyed: re-connecting the same external account (same
    ``external_account_id``) updates the row instead of creating a duplicate.
    """

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], app_secret_key: str
    ) -> None:
        self._sf = session_factory
        self._key = app_secret_key

    def encrypt_config(self, config: dict[str, Any]) -> str:
        return encrypt_secret(json.dumps(config), self._key)

    def decrypt_config(self, account: ConnectorAccount) -> dict[str, Any]:
        if not account.config:
            return {}
        decoded: dict[str, Any] = json.loads(decrypt_secret(account.config, self._key))
        return decoded

    async def get(self, account_id: int) -> ConnectorAccount | None:
        async with self._sf() as s:
            return await s.get(ConnectorAccount, account_id)

    async def list_for_connector(self, connector_key: str) -> list[ConnectorAccount]:
        async with self._sf() as s:
            stmt = select(ConnectorAccount).where(ConnectorAccount.connector_key == connector_key)
            return list((await s.execute(stmt)).scalars().all())

    async def list_all(self) -> list[ConnectorAccount]:
        async with self._sf() as s:
            return list((await s.execute(select(ConnectorAccount))).scalars().all())

    async def upsert_by_identity(
        self,
        connector_key: str,
        external_account_id: str,
        *,
        label: str,
        config: dict[str, Any],
        granted_scopes: Iterable[str] | None = None,
        status: str = "connected",
    ) -> ConnectorAccount:
        """Create the account, or update it if (connector_key, identity) exists."""
        async with self._sf() as s:
            account = (
                await s.execute(
                    select(ConnectorAccount).where(
                        ConnectorAccount.connector_key == connector_key,
                        ConnectorAccount.external_account_id == external_account_id,
                    )
                )
            ).scalar_one_or_none()
            if account is None:
                account = ConnectorAccount(
                    connector_key=connector_key, external_account_id=external_account_id
                )
                s.add(account)
            account.label = label
            account.config = self.encrypt_config(config)
            account.status = status
            if granted_scopes is not None:
                account.granted_scopes = list(granted_scopes)
            await s.commit()
            await s.refresh(account)
            return account

    async def update_config(self, account_id: int, config: dict[str, Any]) -> None:
        async with self._sf() as s:
            account = await s.get(ConnectorAccount, account_id)
            if account is not None:
                account.config = self.encrypt_config(config)
                await s.commit()

    async def set_status(
        self, account_id: int, status: str, *, last_error: str | None = None
    ) -> None:
        async with self._sf() as s:
            account = await s.get(ConnectorAccount, account_id)
            if account is not None:
                account.status = status
                account.last_error = last_error
                await s.commit()

    async def set_last_sync(self, account_id: int, when: dt.datetime) -> None:
        async with self._sf() as s:
            account = await s.get(ConnectorAccount, account_id)
            if account is not None:
                account.last_sync_at = when
                await s.commit()

    async def delete(self, account_id: int) -> None:
        async with self._sf() as s:
            account = await s.get(ConnectorAccount, account_id)
            if account is not None:
                await s.delete(account)
                await s.commit()
