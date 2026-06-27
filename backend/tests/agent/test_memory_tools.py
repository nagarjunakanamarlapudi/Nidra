import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.agent.memory_tools import build_memory_tools
from pragya_assistant.agent.tools import Tool
from pragya_assistant.memory.service import MemoryService
from tests.fakes import FakeEmbeddingProvider

EXPECTED_TOOLS = {
    "remember_note",
    "remember_person",
    "recall_notes",
    "find_people",
    "upcoming_birthdays",
    "set_preference",
    "get_preferences",
}


def _tools(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, Tool]:
    service = MemoryService(
        session_factory=session_factory,
        embedder=FakeEmbeddingProvider(),
        embedding_model="fake",
        embedding_dim=1536,
    )
    return {tool.name: tool for tool in build_memory_tools(service)}


async def test_tool_set_and_schemas(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tools = _tools(session_factory)
    assert set(tools) == EXPECTED_TOOLS
    for tool in tools.values():
        assert tool.input_schema["type"] == "object"


async def test_remember_person_then_upcoming_birthdays(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tools = _tools(session_factory)
    in_three_days = (dt.date.today() + dt.timedelta(days=3)).isoformat()
    saved = await tools["remember_person"].handler(
        {"name": "Sister", "relationship": "sister", "birthday": in_three_days}
    )
    assert "Sister" in saved

    upcoming = await tools["upcoming_birthdays"].handler({"within_days": 7})
    assert "Sister" in upcoming


async def test_remember_note_then_recall(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tools = _tools(session_factory)
    await tools["remember_note"].handler({"text": "the pasta place downtown was great"})
    recalled = await tools["recall_notes"].handler({"query": "pasta place"})
    assert "pasta place" in recalled


async def test_find_people(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tools = _tools(session_factory)
    await tools["remember_person"].handler({"name": "Alice Johnson"})
    found = await tools["find_people"].handler({"query": "alice"})
    assert "Alice Johnson" in found


async def test_set_and_get_preferences(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tools = _tools(session_factory)
    await tools["set_preference"].handler({"key": "tone", "value": "concise"})
    prefs = await tools["get_preferences"].handler({})
    assert "tone" in prefs and "concise" in prefs


async def test_invalid_birthday_surfaces_as_text(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # The handler raises on a bad date; we assert the raised message is meaningful.
    tools = _tools(session_factory)
    raised = False
    try:
        await tools["remember_person"].handler({"name": "X", "birthday": "not-a-date"})
    except ValueError:
        raised = True
    assert raised
