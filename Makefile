.DEFAULT_GOAL := help

API_PORT ?= 8020
WEB_PORT ?= 3000

.PHONY: help setup dev dev-backend dev-backend-lite dev-frontend build test test-backend test-frontend

help: ## Show available project commands
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  make %-17s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Install locked backend and frontend dependencies
	cd backend && uv sync
	cd frontend && pnpm install --frozen-lockfile

dev: ## Start the API and web development servers together
	$(MAKE) --jobs=2 dev-backend dev-frontend

dev-backend: ## Start extract + judge API on one port (needs deploy/htodb/.env and DB)
	MSDS_API_PORT=$(API_PORT) MSDS_API_RELOAD=1 backend/scripts/serve_api.sh

dev-backend-lite: ## Start extract API only, file store, no DB (judge routes 404)
	cd backend && uv run uvicorn --app-dir src msds.api.extract_app:app --reload --host 127.0.0.1 --port $(API_PORT)

dev-frontend: ## Start Next.js on http://127.0.0.1:$(WEB_PORT)
	cd frontend && NEXT_PUBLIC_API_BASE=http://127.0.0.1:$(API_PORT) pnpm dev --hostname 127.0.0.1 --port $(WEB_PORT)

build: ## Build the static frontend for FastAPI to serve
	cd frontend && NEXT_PUBLIC_API_BASE= pnpm build

test: ## Run backend and frontend test suites
	$(MAKE) test-backend
	$(MAKE) test-frontend

test-backend: ## Run the backend test suite (database-backed tests need HTODB)
	cd backend && uv run pytest -q

test-frontend: ## Run the frontend test suite
	cd frontend && pnpm test
