"""The runtime half of a connector: the behaviour behind a
:class:`~pragya_assistant.connectors.spec.ConnectorSpec`.

Every connector implements :class:`Connector` (``test_connection``). Each
capability is its own structural protocol (``SupportsIngest``, ``SupportsTools``,
…) so the manager can dispatch with ``isinstance`` and a connector implements
only what its spec declares — no ``NotImplementedError`` stubs.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from pragya_assistant.agent.engine import AgentEngine
    from pragya_assistant.agent.tools import Tool
    from pragya_assistant.config import Settings
    from pragya_assistant.connectors.spec import ConnectorSpec
    from pragya_assistant.finance.service import FinanceService
    from pragya_assistant.memory.conversations import ConversationStore


@dataclass(frozen=True)
class Health:
    """Result of a connectivity probe."""

    ok: bool
    detail: str | None = None


@dataclass(frozen=True)
class SyncResult:
    """Outcome of an ingestion run."""

    items: int
    detail: str | None = None


@dataclass(frozen=True)
class McpMount:
    """How to mount an MCP server whose tools become the agent's tools."""

    transport: Literal["stdio", "http", "sse"]
    command: list[str] | None = None  # for stdio
    url: str | None = None  # for http / sse
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class AccountAuth:
    """One linked account's auth, for multi-account (OAuth) connectors.

    ``access_token`` refreshes transparently per call (per account). ``label`` is
    the user-facing account name (e.g. the email) used to tag aggregated results.
    """

    account_id: int
    label: str
    access_token: Callable[[], Awaitable[str]]
    granted_scopes: tuple[str, ...] = ()


@dataclass
class ConnectorContext:
    """Per-call state handed to a connector: its decrypted config, granted OAuth
    scopes, and — for OAuth connectors — a callable returning a fresh access token
    (refreshing transparently).

    For **multi-account** connectors, ``accounts`` holds one entry per linked
    account; tools fan out over it and label results. Single-account connectors
    leave it empty and use ``config`` / ``access_token``.
    """

    key: str
    config: dict[str, Any]
    granted_scopes: tuple[str, ...] = ()
    access_token: Callable[[], Awaitable[str]] | None = None
    accounts: tuple[AccountAuth, ...] = ()


@runtime_checkable
class Connector(Protocol):
    """The one method every connector implements."""

    async def test_connection(self, ctx: ConnectorContext) -> Health: ...


@runtime_checkable
class SupportsAccountIdentity(Protocol):
    """OAuth connectors implement this so the manager can label/dedupe accounts:
    given a fresh access token, return ``(external_account_id, display_label)``."""

    async def account_identity(self, access_token: str) -> tuple[str, str]: ...


@runtime_checkable
class SupportsIngest(Protocol):
    async def sync(self, ctx: ConnectorContext) -> SyncResult: ...


@runtime_checkable
class SupportsTools(Protocol):
    def build_tools(self, ctx: ConnectorContext) -> list[Tool]: ...


@runtime_checkable
class SupportsMcp(Protocol):
    def mcp_mount(self, ctx: ConnectorContext) -> McpMount | None: ...


@runtime_checkable
class SupportsChannel(Protocol):
    def channel_worker(self, ctx: ConnectorContext) -> Any: ...


@dataclass
class ConnectorDeps:
    """Shared dependencies injected when constructing a live connector."""

    session_factory: async_sessionmaker[AsyncSession]
    settings: Settings
    # Channel runtime (for SupportsChannel connectors): a getter for the *live*
    # agent engine (resolved per message so connector toggles take effect without
    # restarting the worker) and the conversation store. Optional — non-channel
    # connectors don't need them.
    get_agent: Callable[[], AgentEngine] | None = None
    conversations: ConversationStore | None = None
    # The finance service (Plaid), for the Plaid connector — None if PLAID creds
    # aren't set.
    finance: FinanceService | None = None


@dataclass(frozen=True)
class RegisteredConnector:
    """A spec paired with a builder that constructs its live connector."""

    spec: ConnectorSpec
    build: Callable[[ConnectorDeps], Connector]
