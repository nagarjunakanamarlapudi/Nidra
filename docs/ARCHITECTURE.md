# Pragya — Architecture

A single-user, self-hosted personal assistant. Reactive chat over a web app +
Telegram, hybrid memory (structured Postgres + semantic pgvector), and a
**pluggable "brain"** that can run on a coding-agent subscription (Claude Code,
Codex), a model API key (Anthropic, OpenAI), or a local LLM (Ollama).

> Diagrams use [Mermaid](https://mermaid.js.org/) — they render on GitHub and in
> most Markdown viewers/IDEs.

---

## 1. System context (zoom level 0)

Who talks to what.

```mermaid
flowchart TB
    user([You])

    subgraph clients[Clients]
        web[Web app<br/>Next.js / React]
        tg[Telegram]
    end

    subgraph pragya[Pragya backend]
        api[HTTP API<br/>/chat /conversations /digests /finance /health]
        poller[Telegram poller<br/>long-poll worker · own container]
        sched[Scheduler<br/>daily digest · Plaid sync · weekly finance digest]
        engine[Agent engine<br/>the brain]
        mem[Memory service]
        fin[Finance service<br/>Plaid Link + sync]
    end

    db[(Postgres + pgvector)]
    plaid[Plaid API]

    subgraph brains[Brain backends - pick ONE via AGENT_ENGINE]
        cc[Claude Code<br/>your Claude sub]
        cx[Codex<br/>your ChatGPT sub]
        apis[Anthropic / OpenAI<br/>API keys]
        oll[Ollama<br/>local]
    end

    user --> web --> api
    poller -->|getUpdates, reply| tg
    sched -->|digest push| tg
    api --> engine
    poller --> engine
    sched --> engine
    engine --> mem --> db
    engine --> fin
    fin --> db
    fin -.->|Link + sync| plaid
    sched -.->|daily sync| fin
    engine --> cc
    engine --> cx
    engine --> apis
    engine --> oll
```

**Key ideas:** the API and memory layers are engine-agnostic — swapping the brain
is a one-line config change (`AGENT_ENGINE`). Pragya is also **proactive** (the
scheduler pushes a daily digest) and **reachable** (a long-polling worker serves
two-way Telegram chat with no public URL).

---

## 2. Backend components (zoom level 1)

```mermaid
flowchart TB
    subgraph api_layer[API layer · api/]
        app[create_app<br/>CORS + request-id + auth]
        chat["POST /chat"]
        convs["GET /conversations · /conversations/{id}"]
        health["GET /health · /ready"]
        tgwh["POST /telegram/webhook"]
        fin_routes["POST /finance/link/token<br/>POST /finance/link/exchange<br/>POST /finance/sync<br/>GET /finance/accounts"]
        deps[AppComponents<br/>composition root]
    end

    subgraph agent_layer[Agent layer · agent/]
        iface{{AgentEngine<br/>Protocol}}
        factory[build_engine<br/>selector → engine]
        loop[LoopEngine]
        ccode[ClaudeCodeEngine]
        codex[CodexEngine]
        tools[ToolRegistry<br/>+ build_memory_tools<br/>+ build_finance_tools]
        prompts[build_system_prompt]
    end

    subgraph mcp_layer[MCP · mcp_memory.py]
        srv[stdio MCP server<br/>wraps the same tools]
    end

    subgraph memory_layer[Memory layer · memory/]
        svc[MemoryService]
        repos[Repositories<br/>People / Note / Preference]
        conv[ConversationStore]
        models[(SQLAlchemy models)]
    end

    subgraph finance_layer[Finance layer · finance/]
        fsvc[FinanceService]
        fstore[FinanceStore<br/>PlaidItem / Account / Transaction<br/>Holding / Liability<br/>institution name + logo + color]
        fapi[PlaidApiClient<br/>Protocol: PlaidClient]
        crypto[crypto.py<br/>encrypt / decrypt access token]
    end

    subgraph llm_layer[LLM layer · llm/]
        prov[ChatProvider / EmbeddingProvider<br/>Protocols + factory]
    end

    chat --> deps --> iface
    factory --> loop & ccode & codex
    iface -.implemented by.-> loop & ccode & codex
    loop --> tools --> svc
    loop --> tools --> fsvc
    loop --> prov
    ccode --> tools
    codex --> srv --> tools
    svc --> repos --> models
    chat --> conv --> models
    convs --> conv
    prompts --> loop & ccode & codex
    fin_routes --> fsvc --> fstore --> models
    fsvc --> fapi
    fsvc --> crypto
```

| Layer | Responsibility | Depends on |
|---|---|---|
| **api/** | HTTP surface, auth, request wiring | agent, memory, finance |
| **agent/** | the brain interface + the 3 engines + tools | llm, memory, finance |
| **mcp_memory.py** | expose memory tools over stdio MCP (for Codex) | agent.tools, memory |
| **memory/** | persistence + retrieval (structured + semantic) | llm (embeddings), Postgres |
| **tasks/** | task store + tools (add/list/complete/due) | agent.tools, Postgres |
| **calendars/** | read-only `.ics` service + tools (recurrence, TTL cache) | agent.tools, httpx |
| **digests/** | compose (via engine) + store + deliver the daily digest | agent, memory, telegram |
| **scheduling/** | in-process APScheduler — daily digest + Plaid sync + weekly finance digest | digests, finance |
| **channels/telegram/** | client, webhook + long-poll worker (`process_telegram_update`) | agent, memory |
| **finance/** | Plaid Link + read-only sync (accounts/transactions/holdings/liabilities) | Plaid API, Postgres, crypto |
| **crypto.py** | Fernet symmetric encryption of Plaid access tokens at rest | `APP_SECRET_KEY` |
| **llm/** | provider-agnostic model I/O (chat + embeddings) | vendor SDKs |

Two clean seams keep vendors out of the core:
- **`ChatProvider`** — raw model I/O (one request → one response). Anthropic / OpenAI / Ollama hide behind it.
- **`AgentEngine`** — a whole turn ("given history + message, produce a reply"). The loop is one implementation; Claude Code and Codex are others.

---

## 3. The pluggable brain

One flat selector chooses the engine; loop-based brains additionally pick a `ChatProvider`.

```mermaid
flowchart LR
    sel["AGENT_ENGINE"]

    sel -->|claude-code| CC[ClaudeCodeEngine]
    sel -->|codex| CX[CodexEngine]
    sel -->|anthropic-api| L1[LoopEngine]
    sel -->|openai-api| L2[LoopEngine]
    sel -->|ollama| L3[LoopEngine]

    L1 --> PA[AnthropicChatProvider]
    L2 --> PO[OpenAIChatProvider]
    L3 --> POL[OllamaChatProvider]

    CC -.->|subscription| subA[Claude Code]
    CX -.->|subscription| subB[Codex CLI]

    classDef sub fill:#e8f0ff,stroke:#4a72d0;
    class CC,CX sub;
```

| `AGENT_ENGINE` | Category | Engine | Tools reach memory via | Auth |
|---|---|---|---|---|
| `claude-code` *(default)* | subscription | `ClaudeCodeEngine` | in-process SDK MCP | Claude login / `CLAUDE_CODE_OAUTH_TOKEN` |
| `codex` | subscription | `CodexEngine` | stdio MCP server | `codex login` / `OPENAI_API_KEY` |
| `anthropic-api` | API key | `LoopEngine` | in-process call | `ANTHROPIC_API_KEY` |
| `openai-api` | API key | `LoopEngine` | in-process call | `OPENAI_API_KEY` |
| `ollama` | local | `LoopEngine` | in-process call | none |

All five satisfy the same interface:

```python
class AgentEngine(Protocol):
    async def respond(self, history: list[Message], user_text: str) -> tuple[str, list[Message]]: ...
```

---

## 4. Request lifecycle — what happens on every message

The engine-agnostic outer flow (`/chat`):

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant API as Chat API
    participant CS as ConversationStore
    participant E as AgentEngine
    participant DB as Postgres

    U->>API: POST {message}  + Bearer token
    API->>CS: get_or_create conversation (by external id)
    CS->>DB: SELECT conversation + recent messages
    DB-->>CS: history
    CS-->>API: history : list[Message]
    API->>E: respond(history, message, effort)
    Note over E: engine-specific (§7, §8, §9)<br/>may call memory tools mid-turn,<br/>logs engine_usage and engine_reasoning
    alt engine fails
        E-->>API: raises
        API-->>U: 502 + log chat_engine_failed (request-id)
    else success
        E-->>API: (reply, [user_msg, assistant_msg])
        API->>CS: append(user_msg, assistant_msg)
        CS->>DB: INSERT messages
        API-->>U: {reply} + log chat_completed (engine, duration_ms)
    end
```

**Persisted on every turn:** the conversation row (created once), plus the user
and assistant messages. Memory writes (notes / people / preferences) happen
*inside* `respond` only when the model decides to call a memory tool. Every turn
also emits structured logs — `chat_completed` (engine, duration) and
`engine_usage` (token counts) — tagged with a per-request id. The web app's
**history sidebar** reads `GET /conversations` (each titled by its first user
message) and loads a chat via `GET /conversations/{id}`.

Each turn also carries an optional per-chat **reasoning effort** — the composer's
Auto/Low/Medium/High selector → `ChatRequest.effort` → the active engine
(Anthropic `output_config.effort` · Claude SDK `effort` · Codex
`model_reasoning_effort`); captured model reasoning is logged as `engine_reasoning`.

---

## 5. Memory model — what's stored

```mermaid
erDiagram
    PEOPLE {
        int id PK
        string name
        string relationship
        date birthday
        text notes
    }
    NOTES {
        int id PK
        text text "the note body"
        vector embedding "pgvector(1536)"
        timestamp created_at
    }
    PREFERENCES {
        int id PK
        string key UK
        text value
    }
    CONVERSATIONS {
        int id PK
        string external_id "telegram chat / web session"
        timestamp created_at
    }
    MESSAGES {
        int id PK
        int conversation_id FK
        string role "user|assistant"
        text content
        timestamp created_at
    }
    PLAID_ITEMS {
        int id PK
        string institution_name
        text institution_logo "base64 PNG — optional"
        string institution_color "hex primary_color — optional"
        text access_token "Fernet-encrypted"
        string item_id UK
        text transactions_cursor
        timestamp last_synced_at
    }
    ACCOUNTS {
        int id PK
        int item_id FK
        string plaid_account_id UK
        string name
        string official_name "Plaid official name — optional"
        string mask "last-4 digits — optional"
        string type "depository|investment|credit|loan"
        string subtype "checking|savings|credit card|etc."
        decimal current_balance
        decimal available_balance
        string iso_currency
    }
    TRANSACTIONS {
        int id PK
        int account_id FK
        string plaid_txn_id UK
        date date
        string name
        decimal amount
        string category
    }
    HOLDINGS {
        int id PK
        int account_id FK
        string security_name
        string ticker
        decimal value
    }
    LIABILITIES {
        int id PK
        int account_id FK
        string kind "mortgage|credit|student"
        decimal balance
        date next_payment_due
    }
    CONVERSATIONS ||--o{ MESSAGES : has
    PLAID_ITEMS ||--o{ ACCOUNTS : has
    ACCOUNTS ||--o{ TRANSACTIONS : has
    ACCOUNTS ||--o{ HOLDINGS : has
    ACCOUNTS ||--o{ LIABILITIES : has
```

Two kinds of memory, deliberately separate:

- **Episodic (conversation):** `conversations` + `messages` — the raw transcript,
  written every turn, read back as short-term context for the next turn.
- **Semantic / structured (long-term):** `people`, `notes`, `preferences` —
  durable facts the assistant chooses to remember, written only via tools.

---

## 6. When data is persisted, and how it's retrieved

```mermaid
flowchart LR
    subgraph writes[WRITE — when]
        w1[every turn:<br/>conversation + 2 messages]
        w2[tool remember_note:<br/>note + embedding]
        w3[tool remember_person:<br/>person upsert by name]
        w4[tool set_preference:<br/>preference upsert by key]
    end
    subgraph store[Postgres + pgvector]
        t1[(messages)]
        t2[(notes)]
        t3[(people)]
        t4[(preferences)]
    end
    subgraph reads[READ — how]
        r1[history:<br/>recent messages by conversation]
        r2[recall_notes:<br/>pgvector cosine_distance KNN]
        r3[find_people / upcoming_birthdays:<br/>name ilike / birthday math]
        r4[get_preferences:<br/>by key]
    end

    w1 --> t1 --> r1
    w2 --> t2 --> r2
    w3 --> t3 --> r3
    w4 --> t4 --> r4
```

**Semantic recall** is the interesting one — `remember_note` embeds the text on
write; `recall_notes` embeds the *query* and finds nearest neighbours:

```mermaid
sequenceDiagram
    autonumber
    participant T as Tool (remember_note / recall_notes)
    participant M as MemoryService
    participant EMB as EmbeddingProvider
    participant DB as pgvector

    rect rgb(238,248,238)
    Note over T,DB: WRITE
    T->>M: remember_note(text)
    M->>EMB: embed([text]) → vector[1536]
    M->>DB: INSERT note(content, embedding)
    end

    rect rgb(238,242,255)
    Note over T,DB: READ
    T->>M: recall_notes(query)
    M->>EMB: embed([query]) → vector[1536]
    M->>DB: SELECT ... ORDER BY cosine_distance(embedding, q) LIMIT k
    DB-->>M: nearest notes
    end
```

---

## 7. Low-level — the loop engine (API keys / local LLM)

Pragya owns the agent loop: call the model, run any tool calls, repeat until the
model stops asking for tools (bounded by `max_steps`).

```mermaid
sequenceDiagram
    autonumber
    participant E as LoopEngine
    participant P as ChatProvider
    participant R as ToolRegistry
    participant M as MemoryService

    E->>E: assemble [system, ...history, user]
    loop until no tool_calls (≤ max_steps)
        E->>P: chat(messages, tools)
        P-->>E: ChatResult(text, tool_calls)
        alt has tool_calls
            loop each call
                E->>R: run(ToolCall)
                R->>M: memory op
                M-->>R: result
                R-->>E: tool result message
            end
        else final answer
            E-->>E: return text
        end
    end
```

The provider normalizes vendor differences (Anthropic blocks vs OpenAI
tool_calls vs Ollama) into one `ChatResult`/`ToolCall` shape — the loop never
sees vendor types.

---

## 8. Low-level — the Claude Code engine

`ClaudeCodeEngine` delegates the whole turn to **Claude Code** via the Claude
Agent SDK. Our memory tools are registered **in-process** as SDK MCP tools, and
`allowed_tools` restricts Claude Code to *only* those (no bash/file/web).

```mermaid
sequenceDiagram
    autonumber
    participant E as ClaudeCodeEngine
    participant SDK as claude_agent_sdk.query
    participant CC as Claude Code (bundled CLI)
    participant T as our @tool wrappers
    participant M as MemoryService

    Note over E: build options once:<br/>system_prompt, mcp_servers={pragya},<br/>allowed_tools=[mcp__pragya__*],<br/>permission_mode=bypassPermissions,<br/>setting_sources=[]
    E->>SDK: query(prompt, options)
    SDK->>CC: spawn (auth: ~/.claude / CLAUDE_CODE_OAUTH_TOKEN)
    loop agent turn
        CC->>T: call mcp__pragya__remember_person(...)
        T->>M: remember_person(...)
        M-->>T: "Saved ..."
        T-->>CC: tool result
    end
    CC-->>SDK: AssistantMessage(TextBlock...)
    SDK-->>E: stream of messages
    E->>E: collect TextBlock.text → reply
```

```mermaid
flowchart LR
    subgraph proc[Pragya backend process]
        E[ClaudeCodeEngine]
        wrap["@tool wrappers"]
        M[MemoryService]
    end
    cli[Claude Code<br/>subprocess]
    E -- query --> cli
    cli -- "mcp__pragya__* over SDK MCP" --> wrap --> M --> db[(Postgres)]
```

Why in-process MCP: same `Tool` objects the loop uses, zero serialization
service, and Claude Code can only touch memory — nothing else on the box.

---

## 9. Low-level — the Codex engine

Codex has no Python SDK, so `CodexEngine` shells out to `codex exec --json` and
parses its JSONL event stream. Codex is a *separate process*, so our tools are
exposed through a **standalone stdio MCP server** that Codex spawns and calls.

```mermaid
sequenceDiagram
    autonumber
    participant E as CodexEngine
    participant CX as codex exec --json (subprocess)
    participant SRV as python -m pragya_assistant.mcp_memory
    participant M as MemoryService

    Note over E: cmd = codex exec --json<br/>--dangerously-bypass-approvals-and-sandbox<br/>-c mcp_servers.pragya.command/args/env<br/>prompt via stdin
    E->>CX: spawn (auth: codex login / OPENAI_API_KEY)
    CX->>SRV: spawn MCP server (env: DATABASE_URL, embeddings…)
    loop agent turn
        CX->>SRV: call pragya.remember_person(...)
        SRV->>M: ToolRegistry.run → remember_person
        M-->>SRV: "Saved ..."
        SRV-->>CX: TextContent
    end
    CX-->>E: JSONL: item.completed{agent_message}, turn.completed{usage}
    E->>E: parse last agent_message → reply
```

```mermaid
flowchart LR
    E[CodexEngine] -- "codex exec --json (stdin prompt)" --> CX[codex subprocess]
    CX -- "spawns + MCP/JSON-RPC" --> SRV[mcp_memory stdio server]
    SRV -- ToolRegistry --> M[MemoryService] --> db[(Postgres)]
    CX -- "JSONL events (stdout)" --> E
```

Trade-off (single-user, your machine): Codex runs with
`--dangerously-bypass-approvals-and-sandbox` so the MCP server can reach
Postgres and so headless MCP tool calls work — Codex still only gets *our*
memory tools. The MCP server reuses `build_memory_tools` + `ToolRegistry` — the
**same tool definitions** the other engines use (one source of truth).

---

## 10. Memory-over-MCP — one tool set, three deliveries

```mermaid
flowchart TB
    src["build_memory_tools(memory)<br/>+ ToolRegistry<br/>— single source of truth —"]

    src --> A[LoopEngine<br/>in-process call]
    src --> B[ClaudeCodeEngine<br/>in-process SDK MCP @tool]
    src --> C[mcp_memory server<br/>stdio MCP → CodexEngine]

    A & B & C --> M[MemoryService] --> db[(Postgres + pgvector)]
```

The 7 tools: `remember_note`, `remember_person`, `recall_notes`, `find_people`,
`upcoming_birthdays`, `set_preference`, `get_preferences`. Defined once; the
delivery mechanism differs per engine, the behaviour does not.

---

## 11. Auth & secrets

```mermaid
flowchart TB
    subgraph local[Local — make engine-smoke / make run]
        l1[claude-code → macOS Keychain<br/>'Claude Code-credentials']
        l2[codex → ~/.codex/auth.json + Keychain]
    end
    subgraph docker[Docker — make up]
        d1[claude-code → CLAUDE_CODE_OAUTH_TOKEN<br/>from claude setup-token, via .env]
        note[ANTHROPIC_API_KEY must be empty<br/>so the subscription token wins]
    end
    subgraph app[App secrets]
        a1[API_AUTH_TOKEN — single-user bearer auth]
        a2[APP_SECRET_KEY — signing / encryption]
    end
```

Rules: never commit `.env`; never read provider creds from a workspace-local
`.env`; on the home server, subscriptions are the supported personal-use path;
in cloud, switch to API keys (a config change, by design).

**Fail-fast:** when `APP_ENV ≠ local`, the app refuses to boot with a
placeholder/weak `API_AUTH_TOKEN` or `APP_SECRET_KEY`; it also rejects a known
embedding model paired with the wrong `LLM_EMBEDDING_DIM` at config time (so a
mismatch fails at startup, not mid-chat).

---

## 12. Deployment topology

```mermaid
flowchart TB
    subgraph compose[docker compose · make up]
        fe[frontend<br/>Next.js standalone<br/>:3000]
        be[backend<br/>FastAPI · uvicorn · digest + finance scheduler<br/>:8000→:APP_PORT<br/>bundles Claude Code CLI]
        poller[telegram_poller<br/>long-poll worker · own logs]
        dbc[(db<br/>pgvector/pgvector:pg16<br/>:5432, healthcheck)]
    end
    browser([Browser]) --> fe
    fe -->|NEXT_PUBLIC_API_BASE| be
    be -->|alembic upgrade head on start| dbc
    poller --> dbc
    poller -.->|getUpdates, sendMessage| tgapi[Telegram API]
    be -.->|claude-code| subscription[Claude subscription]
    be -.->|Plaid Link + sync| plaidapi[Plaid API]
```

**Plaid Link flow** (Connect-a-bank in the web app):

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant FE as Finance.tsx (web)
    participant BE as Backend /finance/link/*
    participant PL as Plaid API
    participant DB as Postgres

    U->>FE: click "Connect a bank"
    FE->>BE: POST /finance/link/token
    BE->>PL: /link/token/create
    PL-->>BE: link_token
    BE-->>FE: {link_token}
    FE->>U: open Plaid Link widget
    U->>FE: select bank + credentials → public_token
    FE->>BE: POST /finance/link/exchange {public_token}
    BE->>PL: /item/public_token/exchange
    PL-->>BE: access_token + item_id
    BE->>DB: save_item (access_token encrypted with APP_SECRET_KEY)
    BE->>PL: /item/get → institution_id
    BE->>PL: /institutions/get_by_id {include_optional_metadata: true}
    PL-->>BE: name + logo (base64 PNG, may be null) + primary_color (may be null)
    BE->>DB: set_institution (name, logo, color)
    BE-->>FE: {institution: name}
    Note over BE,DB: scheduler: daily Plaid sync at finance_sync_hour<br/>+ weekly finance digest on finance_weekly_day<br/>backfill_institutions: retroactively fetches metadata for existing items
```

**Finance accounts API + web UI:**

- `GET /finance/accounts` returns `AccountOut` objects each with `institution`,
  `institution_logo` (base64 PNG or null), `institution_color` (hex or null),
  `official_name`, `mask` (last-4 digits), `type`, `subtype`, `current_balance`.
- The **Finance page** (`Finance.tsx`) groups accounts **by institution**, shows a
  brand-color initial badge (or the logo image if present), renders
  `official_name ?? name` + mask suffix (e.g. `•••• 1234`), and displays a **Net
  Worth** headline (assets − credit/loan balances) above all institution groups.
- The `account_balances` chat tool prefixes each balance line with the institution
  name (format: `Institution · Account name (subtype): balance`).
- `PLAID_ENV` = `sandbox` | `production` (set in config; maps to the Plaid SDK
  `Environment`). The free **Trial** plan gives real-data access for up to 10
  connected institutions (Items) with no business enrollment required.

- **Startup order:** db (healthcheck gate) → backend (`alembic upgrade head` then
  serve, running the daily-digest + finance scheduler) → frontend + `telegram_poller`
  (both gated on backend healthy). The poller is its own container/process so its
  logs stay separate (`make logs-poller`).
- **Resilience:** all services run `restart: unless-stopped` (survive reboots);
  `/ready` is a real DB probe (503 when the DB is down) so healthchecks mean something.
- **Backups:** `make backup` → `backups/pragya-<timestamp>.sql.gz`; `make restore FILE=…`.
- **Observability:** structured JSON logs with a per-request id; per-turn
  `chat_completed` (duration) + `engine_usage` (tokens); engine failures surface
  as a clean `502`, never a leaked 500.
- **Tests** run against a separate `pragya_test` database so the suite never wipes
  dev/smoke data.
- **Home-server first, cloud-portable:** same images redeploy to AWS/Azure;
  only auth/secrets sourcing changes.

---

## 13. Roadmap context

- **Phase 1 (done):** walking skeleton — agent loop, memory, API, Telegram, web app, Docker, CI.
- **Phase 2 (done):** pluggable engines — Claude Code, Codex, API/local; memory-over-MCP; conversation-history sidebar.
- **Hardening (done):** fail-fast config, real `/ready`, DB backups, restart policies, clean errors + per-turn usage logging.
- **Phase 3 (done):** proactive daily **digest** (scheduler → Telegram + web), per-chat reasoning effort, **tasks**, read-only **calendar** (.ics), and **two-way Telegram** via a long-polling worker. Remaining 3d: **web search**.
- **Phase 4 (done):** **email** inbox (Gmail/IMAP read → triage → summarize) and **web search** integration.
- **Phase 5 (live — Trial plan, single institution):** **finance** — Plaid Link connect-a-bank flow, read-only sync (accounts/transactions/holdings/liabilities), 6 finance chat tools, Fernet encryption of access tokens at rest, daily Plaid sync + weekly finance digest scheduler jobs, finance line in the daily digest, and a Finance web page. Institution metadata (real name, logo, brand color) fetched via `item/get` → `institutions/get_by_id` (`include_optional_metadata`) on link and via `backfill_institutions` for existing items; stored as `institution_logo` + `institution_color` on `plaid_items` (migrations 0005–0006). Finance page groups accounts by institution with brand-color badges and a Net Worth headline. `PLAID_ENV` = `sandbox` | `production`; currently live against a real institution on the free Plaid Trial plan (up to 10 Items, no business enrollment needed). Single-user only.
- **Later:** WhatsApp/Slack integration, voice interface, opt-in autonomy (draft + send), India Account Aggregator migration (if/when GA).

See [`docs/superpowers/specs/`](superpowers/specs/) for the per-phase design specs.
