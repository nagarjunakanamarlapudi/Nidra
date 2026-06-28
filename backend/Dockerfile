# syntax=docker/dockerfile:1

# ---- builder: install deps + project into a venv ----
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install dependencies first (cached unless the lockfile changes).
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Install the project itself.
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---- runtime: slim image with just the venv + app ----
FROM python:3.12-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HOME=/home/pragya

WORKDIR /app

# Claude Code CLI — the claude-code agent engine (claude-agent-sdk) drives the
# `claude` binary as a subprocess, so the runtime image needs Node + the CLI.
# Auth + base URL come from the environment at runtime (ANTHROPIC_BASE_URL +
# ANTHROPIC_AUTH_TOKEN for the DigitalOcean inference gateway), so nothing
# secret is baked into the image.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && npm install -g @anthropic-ai/claude-code \
 && npm cache clean --force \
 && apt-get purge -y --auto-remove gnupg \
 && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 pragya
COPY --from=builder --chown=pragya:pragya /app /app
RUN chmod +x /app/entrypoint.sh

USER pragya
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
