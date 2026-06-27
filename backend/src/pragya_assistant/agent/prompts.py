"""System prompt construction for the agent."""

from __future__ import annotations

BASE_SYSTEM_PROMPT = """You are Pragya, a personal assistant for a single user who fully owns and \
controls you.

You keep a durable memory of the user's world — people, birthdays, free-form notes, and \
preferences — and you have tools to read from and write to that memory.

How to behave:
- Be concise, warm, and direct.
- Recall from memory with your tools before answering from assumptions.
- Honor the user's saved preferences. On any turn that involves money or formatting, call \
get_preferences FIRST and apply every relevant one. In particular, if a preference asks for \
amounts in more than one currency, show EVERY amount in ALL of those currencies — use your web \
search tool to fetch the current exchange rate, and state the rate you used.
- When the user tells you something worth keeping (a person, a birthday, a preference, a note), \
save it with the appropriate tool, then briefly confirm what you saved.
- Never invent stored data. If you don't find something in memory, say so.
- You can store and look things up; you do not take outward actions (sending messages, moving \
money) in this version."""


def build_digest_prompt(today: str) -> str:
    """Prompt that asks the engine to compose the daily digest."""
    return (
        f"Compose my short daily digest for today, {today}. "
        "Greet me warmly in one line, then cover these using your tools, omitting "
        "any section that's empty or unavailable: birthdays in the next 7 days; "
        "tasks that are overdue or due within the next 3 days; the calendar agenda "
        "for today plus the next 2 days (label each day, and call out what's today); "
        "and a quick email triage — scan recent unread mail and surface only the few "
        "that genuinely look like they need my attention (skip newsletters, promos, "
        "and automated alerts); a one-line finance check — notable account balances "
        "and any bills due in the next few days. Keep it brief and friendly — no "
        "preamble about being an assistant."
    )


def build_weekly_finance_prompt(today: str) -> str:
    """Prompt for the weekly finance digest."""
    return (
        f"Compose my weekly finance summary for the week ending {today}. Using your finance "
        "tools, cover: total spending by category this week (top few), current balances across "
        "accounts, net worth, and any bills due in the next 7 days. Be concise and friendly; "
        "omit any section with no data."
    )


def build_system_prompt(
    *, preferences: dict[str, str] | None = None, today: str | None = None
) -> str:
    """Assemble the system prompt, optionally injecting date and known preferences."""
    parts = [BASE_SYSTEM_PROMPT]
    if today:
        parts.append(f"\n\nToday's date is {today}.")
    if preferences:
        rendered = "\n".join(f"- {key}: {value}" for key, value in sorted(preferences.items()))
        parts.append(f"\n\nKnown user preferences:\n{rendered}")
    return "".join(parts)
