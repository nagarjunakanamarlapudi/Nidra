.DEFAULT_GOAL := help
.PHONY: help install dev lint test build check

help:  ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies (npm ci)
	npm ci

dev:  ## Run the dev server
	npm run dev

lint:  ## Lint with eslint
	npm run lint

test:  ## Run tests (vitest)
	npm test

build:  ## Production build
	npm run build

check: lint test build  ## Run all gates
