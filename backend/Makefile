.DEFAULT_GOAL := help
.PHONY: help install test lint fmt fmt-check typecheck run migrate revision check

DATABASE_URL ?= postgresql+asyncpg://pragya:pragya@localhost:5432/pragya

help:  ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Sync dependencies (incl. dev group)
	uv sync

test:  ## Run the test suite
	uv run pytest

lint:  ## Lint with ruff
	uv run ruff check .

fmt:  ## Auto-format with ruff
	uv run ruff format .

fmt-check:  ## Verify formatting
	uv run ruff format --check .

typecheck:  ## Type-check with mypy
	uv run mypy src

run:  ## Run the API (dev, autoreload)
	uv run uvicorn pragya_assistant.main:app --reload --port 8000

migrate:  ## Apply migrations locally (alembic upgrade head)
	DATABASE_URL=$(DATABASE_URL) uv run alembic upgrade head

revision:  ## Autogenerate a migration: make revision m="message"
	DATABASE_URL=$(DATABASE_URL) uv run alembic revision --autogenerate -m "$(m)"

check: lint fmt-check typecheck test  ## Run all quality gates
