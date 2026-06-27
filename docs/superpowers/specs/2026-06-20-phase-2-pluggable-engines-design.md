# Phase 2 — Pluggable Agent Engines (Claude Code + Codex) · Design Spec

**Status:** Approved direction (2026-06-20) — pluggable brain, Claude Code default; add Codex.
**Grounded in:** the real **openclaw** implementation (github.com/openclaw/openclaw) + agent best practices (Nous "Hermes" function-call format, Anthropic Claude Agent SDK, OpenAI Codex/Agents SDK, OSS agents).

---

## 1. Goal

Make the assistant's **brain pluggable** behind one interface, via a **single flat selector** (`AGENT_ENGINE`) spanning three plug categories:

| Category | `AGENT_ENGINE` value | Resolves to | Auth |
|---|---|---|---|
| **a) coding-agent subscription** | `claude-code` | `ClaudeCodeEngine` (claude-agent-sdk → Claude Code) | Claude subscription (or `ANTHROPIC_API_KEY`) |
| **a) coding-agent subscription** | `codex` | `CodexEngine` (`codex exec --json` → Codex) | ChatGPT subscription (or `OPENAI_API_KEY`) |
| **b) model API key** | `anthropic-api` | `LoopEngine(AnthropicChatProvider)` | `ANTHROPIC_API_KEY` |
| **b) model API key** | `openai-api` | `LoopEngine(OpenAIChatProvider)` | `OPENAI_API_KEY` |
| **c) local LLM** | `ollama` | `LoopEngine(OllamaChatProvider)` | none (local) |

The user picks **one** brain. The three loop-based values reuse the Phase-1 `LoopEngine` + `ChatProvider`; the two subscription values are coding-agent engines. This unlocks both the user's subscriptions (Claude + ChatGPT) for a single-user self-hosted assistant — the supported personal-use path. **`LLM_CHAT_PROVIDER` is removed** — `AGENT_ENGINE` subsumes it.

Default: `claude-code` (flips to it once that engine lands; `anthropic-api` is the interim default during the build).

Embeddings remain a **separate** selector (`LLM_EMBEDDING_PROVIDER` ∈ `openai`/`ollama`) since Claude/Codex expose no embeddings API.

## 2. Why this shape (validated by openclaw)

openclaw is a single-user self-hosted assistant with exactly this architecture:
- **Two tiers:** `ApiProvider` (raw LLM) vs `AgentHarness` (agent-as-engine). We mirror it: keep `ChatProvider`, add `AgentEngine`.
- **Drives coding agents as subprocesses** with stable contracts (Claude `claude -p --output-format stream-json`; Codex app-server JSON-RPC; ACP). We shell out similarly.
- **Capability negotiation** (`supports(ctx) → {supported, priority}`, `auto` policy). We adopt a simpler explicit selector now, `auto` later.
- **Reuses subscription credentials** from `~/.claude` / `~/.codex` (+ Keychain), prefers OAuth over keys, ignores workspace `.env` creds. We do the same.
- **Exposes its tools to engines over MCP.** We run one stdio MCP server wrapping our existing `Tool`s.
- **Memory split:** JSONL transcripts + SQLite/vector + periodic consolidation. We already have structured + pgvector; consolidation is a later option.

## 3. Architecture

```
            API / Telegram
                  │  respond(history, user_text)
            ┌─────▼───────── AgentEngine (Protocol) ─────────┐
            │ LoopEngine        ClaudeCodeEngine   CodexEngine│
            │  (ChatProvider     (claude-agent-sdk) (codex     │
            │   + ToolRegistry)   → Claude Code)     exec)     │
            └─────┬───────────────────┬───────────────┬───────┘
                  │ in-process tools   │ MCP           │ MCP
                  └─────────── Memory tools ───────────┘
                          (one stdio MCP server wrapping our Tools;
                           LoopEngine also calls them in-process)
                                     │
                          MemoryService → Postgres + pgvector
```

### `AgentEngine` interface
```python
class AgentEngine(Protocol):
    name: str
    async def respond(self, history: list[Message], user_text: str) -> tuple[str, list[Message]]: ...
```
Same signature as today's `Agent.respond`, so the API/Telegram layers are untouched. Each engine returns the final reply plus the `[user, assistant]` messages to persist (intermediate tool/agent turns stay inside the engine).

### Engines
- **LoopEngine:** today's `Agent`, renamed. No behavior change.
- **ClaudeCodeEngine:** `claude_agent_sdk.query(...)` with our `build_system_prompt()`, our memory tools exposed (in-process `@tool`/`create_sdk_mcp_server` or the shared MCP server), `allowed_tools` restricting Claude Code's built-ins to our tools, `permission_mode` non-interactive, model from config; resume per conversation. Auth: Claude Code credentials (subscription) → fallback `ANTHROPIC_API_KEY`.
- **CodexEngine:** `asyncio` subprocess `codex exec --json` (prompt via stdin), parse JSONL (`thread.started`→session, `item.completed` `agent_message`→reply, `turn.completed`→usage), `resume <session_id>` keyed per conversation, model + sandbox via flags/`-c`, memory tools via the shared MCP server (`codex mcp add` / config). Auth: `codex login` (ChatGPT) → fallback `OPENAI_API_KEY`. In Docker, run with the container as the isolation boundary.

### Memory over MCP
One stdio MCP server, `python -m pragya_assistant.channels.mcp` (name TBD), exposing the same `build_memory_tools(memory)` Tools as MCP tools. Single source of truth; consumed by Claude Code (`mcp__pragya__*`) and Codex; LoopEngine keeps calling the Tools in-process.

### Auth (credential reuse)
Resolution order per engine: explicit API key (env) → the coding-agent CLI's own stored credentials (`~/.claude/.credentials.json` + Keychain "Claude Code-credentials"; `~/.codex/auth.json` + Keychain "Codex Auth") → fail with a clear message. Prefer subscription/OAuth on the home server; switch to API keys for unattended cloud. Never read provider creds from a workspace-local `.env`.

### Config
- `AGENT_ENGINE: Literal["claude-code","codex","anthropic-api","openai-api","ollama"] = "claude-code"` — the single brain selector (interim default `anthropic-api` until the Claude Code engine lands, then flips). Removes `LLM_CHAT_PROVIDER`.
- `LLM_CHAT_MODEL` — model for the loop-based brains (and a sensible default per coding agent).
- Engine-specific (optional): `CLAUDE_CODE_MODEL`, `CODEX_MODEL`, `CODEX_SANDBOX`, credential dir mounts.
- Embeddings unchanged: `LLM_EMBEDDING_PROVIDER`/`LLM_EMBEDDING_MODEL`/`LLM_EMBEDDING_DIM`.

## 4. Plan (incremental, TDD, each its own commit; repo stays green)

1. **Engine abstraction** — `AgentEngine` protocol; rename `Agent`→`LoopEngine`; flat `AGENT_ENGINE` selector replacing `LLM_CHAT_PROVIDER`; `build_engine(settings, memory)` factory mapping the 3 loop values → `LoopEngine(provider)` (coding-agent values raise NotImplementedError until steps 3–4). Interim default `anthropic-api`. All existing tests pass (renamed/retargeted).
2. **Memory MCP server** — stdio server exposing our memory Tools; integration test that lists/calls a tool over MCP.
3. **ClaudeCodeEngine** — claude-agent-sdk integration (SDK mocked in tests: assert system prompt, allowed_tools, tool wiring, reply extraction; auth resolution). Flip default to `claude-code`.
4. **CodexEngine** — `codex exec --json` subprocess (subprocess mocked with scripted JSONL: assert command/flags, parsing, resume, usage). Auth resolution.
5. **Infra** — Dockerfile: add Codex musl binary + `claude-agent-sdk`; mount `~/.claude` / `~/.codex` (rw) for subscription token refresh; config + `.env.example` + Makefile targets (`engine`, credential checks).
6. **Best-practice upgrades** — per-turn token/cost logging; engine `supports()` + `auto` routing; (later) context compaction, "dreaming" consolidation.

## 5. Non-goals (this phase)
- `auto` routing is deferred (explicit selection first).
- Memory "dreaming"/consolidation deferred.
- ACP transport deferred (subprocess-per-engine is enough for two engines).

## 6. Risks / tradeoffs
- **CLI output-contract coupling** (Codex JSONL, Claude stream): pin versions, tolerate unknown event types, treat "no agent_message / any error item" as failure (don't trust exit code alone).
- **Subscription ToS:** fine for single-user self-hosted; do not multi-tenant a subscription. Switch to API keys in cloud.
- **On a coding-agent engine you're vendor-specific** (Claude-only / OpenAI-only); the LoopEngine remains the provider-agnostic fallback.
- **Testability:** LoopEngine fully unit-tested; coding-agent engines tested with the SDK/subprocess mocked + a thin live smoke.
