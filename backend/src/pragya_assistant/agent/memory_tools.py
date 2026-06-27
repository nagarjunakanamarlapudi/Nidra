"""Memory tools — thin, model-facing wrappers over :class:`MemoryService`."""

from __future__ import annotations

import datetime as dt
from typing import Any

from pragya_assistant.agent.tools import Tool
from pragya_assistant.memory.models import Person
from pragya_assistant.memory.service import MemoryService


def build_memory_tools(memory: MemoryService) -> list[Tool]:
    async def remember_note(args: dict[str, Any]) -> str:
        note = await memory.remember_note(str(args["text"]))
        return f"Saved note #{note.id}."

    async def remember_person(args: dict[str, Any]) -> str:
        person = await memory.remember_person(
            name=str(args["name"]),
            relationship=args.get("relationship"),
            birthday=_parse_date(args.get("birthday")),
            notes=args.get("notes"),
        )
        return f"Saved {_describe_person(person)}."

    async def recall_notes(args: dict[str, Any]) -> str:
        results = await memory.semantic_search(str(args["query"]), k=int(args.get("k", 5)))
        if not results:
            return "No matching notes found."
        return "\n".join(f"- {note.text}" for note, _distance in results)

    async def find_people(args: dict[str, Any]) -> str:
        people = await memory.find_people(str(args["query"]))
        if not people:
            return "No matching people found."
        return "\n".join(f"- {_describe_person(p)}" for p in people)

    async def upcoming_birthdays(args: dict[str, Any]) -> str:
        within = int(args.get("within_days", 30))
        people = await memory.upcoming_birthdays(within_days=within)
        if not people:
            return f"No birthdays in the next {within} days."
        return "\n".join(f"- {_describe_person(p)}" for p in people)

    async def set_preference(args: dict[str, Any]) -> str:
        pref = await memory.set_preference(str(args["key"]), str(args["value"]))
        return f"Set preference {pref.key} = {pref.value}."

    async def get_preferences(args: dict[str, Any]) -> str:
        prefs = await memory.get_preferences()
        if not prefs:
            return "No preferences saved yet."
        return "\n".join(f"- {key}: {value}" for key, value in sorted(prefs.items()))

    return [
        Tool(
            name="remember_note",
            description="Save a free-form note to long-term memory.",
            input_schema=_object({"text": _string("The note text to remember")}, ["text"]),
            handler=remember_note,
        ),
        Tool(
            name="remember_person",
            description="Save a person and what you know about them (relationship, birthday).",
            input_schema=_object(
                {
                    "name": _string("The person's name"),
                    "relationship": _string("Relationship to the user, e.g. sister"),
                    "birthday": _string("Birthday as YYYY-MM-DD"),
                    "notes": _string("Any extra notes about the person"),
                },
                ["name"],
            ),
            handler=remember_person,
        ),
        Tool(
            name="recall_notes",
            description="Semantically search the user's saved notes.",
            input_schema=_object(
                {"query": _string("What to search for"), "k": _integer("Max results")},
                ["query"],
            ),
            handler=recall_notes,
        ),
        Tool(
            name="find_people",
            description="Find saved people by full or partial name.",
            input_schema=_object({"query": _string("A name or part of a name")}, ["query"]),
            handler=find_people,
        ),
        Tool(
            name="upcoming_birthdays",
            description="List people whose birthdays fall within the next N days.",
            input_schema=_object({"within_days": _integer("Window size in days (default 30)")}, []),
            handler=upcoming_birthdays,
        ),
        Tool(
            name="set_preference",
            description="Save a user preference as a key/value pair.",
            input_schema=_object(
                {"key": _string("Preference key"), "value": _string("Preference value")},
                ["key", "value"],
            ),
            handler=set_preference,
        ),
        Tool(
            name="get_preferences",
            description="List all saved user preferences.",
            input_schema=_object({}, []),
            handler=get_preferences,
        ),
    ]


def _parse_date(value: Any) -> dt.date | None:
    if not value:
        return None
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def _describe_person(person: Person) -> str:
    relationship = f" ({person.relationship})" if person.relationship else ""
    birthday = f", birthday {person.birthday.isoformat()}" if person.birthday else ""
    return f"{person.name}{relationship}{birthday}"


def _object(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _string(description: str) -> dict[str, str]:
    return {"type": "string", "description": description}


def _integer(description: str) -> dict[str, str]:
    return {"type": "integer", "description": description}
