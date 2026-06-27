from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.agent.toolset import build_agent_tools
from pragya_assistant.calendars.service import CalendarService
from pragya_assistant.email_inbox.service import EmailService
from pragya_assistant.memory.service import MemoryService
from pragya_assistant.tasks.store import TaskStore
from tests.fakes import FakeEmbeddingProvider


class _FakeFinance:
    async def account_balances(self) -> list:
        return []

    async def spending_by_category(self, start: object, end: object) -> dict:
        return {}

    async def search_transactions(
        self, text: object, start: object, end: object, limit: int = 25
    ) -> list:
        return []

    async def holdings(self) -> list:
        return []

    async def liabilities(self) -> list:
        return []

    async def net_worth(self) -> int:
        return 0


def _memory(session_factory: async_sessionmaker[AsyncSession]) -> MemoryService:
    return MemoryService(
        session_factory=session_factory,
        embedder=FakeEmbeddingProvider(),
        embedding_model="x",
        embedding_dim=1536,
    )


class _FakeInbox:
    def list_recent(self, n: int) -> list:
        return []

    def search(self, query: str, n: int) -> list:
        return []

    def unread(self, n: int) -> list:
        return []

    def get(self, message_id: str) -> None:
        return None

    def create_draft(self, raw: bytes) -> None:
        return None


async def test_includes_all_tool_families(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tools = build_agent_tools(
        _memory(session_factory),
        TaskStore(session_factory),
        CalendarService("http://feed"),
        EmailService(_FakeInbox(), address="me@x.com"),
    )
    names = {t.name for t in tools}
    assert {
        "remember_note",
        "add_task",
        "due_tasks",
        "agenda",
        "upcoming_events",
        "list_emails",
        "draft_reply",
    } <= names


async def test_includes_finance_tools(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tools = build_agent_tools(_memory(session_factory), finance_service=_FakeFinance())
    names = {t.name for t in tools}
    assert {"account_balances", "net_worth", "upcoming_bills"} <= names


async def test_omits_calendar_tools_when_service_none(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    names = {
        t.name
        for t in build_agent_tools(_memory(session_factory), TaskStore(session_factory), None)
    }
    assert "add_task" in names
    assert "agenda" not in names
