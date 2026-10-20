# Every target the lanes, the hub and CI use. Frozen: change it only after a brain block.
#
# The hub runs one of check-docs, check-web, check-py or check on each branch, chosen by
# the paths it changes. Every check runs in replay mode: no keys, no network, no cost.
SHELL := /bin/bash
.DEFAULT_GOAL := help
UV ?= uv
PNPM ?= pnpm
WEB := --filter @plumbline/web
CLIENT := --filter @plumbline/ts-client
CONFIG ?= A2
SPLIT ?= dev

help: ## list the targets
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-15s %s\n", $$1, $$2}'

setup: ## once per clone or worktree: git hooks, Python and JavaScript dependencies, Chromium
	git config core.hooksPath scripts/githooks
	$(UV) sync --locked --all-extras
	$(PNPM) install --frozen-lockfile
	$(PNPM) $(WEB) exec playwright install chromium

check: check-py check-web ## everything, for branches that touch both sides or the tooling

check-py: export CACHE_MODE = replay
check-py: export DEEPEVAL_DISABLE_DOTENV = 1
check-py: ## Python: lint, format, strict types, tests, data validation, contract drift
	$(UV) sync --locked --all-extras --quiet
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy
	$(UV) run pytest
	$(UV) run python -m plumbline.corpus.validate

check-web: ## front end: client drift, format, lint, types, unit tests, build, size, e2e with axe, Lighthouse
	$(PNPM) install --frozen-lockfile
	$(PNPM) $(CLIENT) run check
	$(PNPM) $(WEB) run format:check
	$(PNPM) $(WEB) run lint
	$(PNPM) $(WEB) run typecheck
	$(PNPM) $(WEB) run test
	$(PNPM) $(WEB) run build
	$(PNPM) $(WEB) run size
	$(PNPM) $(WEB) run e2e
	$(PNPM) $(WEB) run lighthouse

check-docs: ## documentation-only branches: every relative link resolves
	python3 scripts/check_docs.py

fmt: ## format and autofix Python and the front end
	$(UV) run ruff format .
	$(UV) run ruff check --fix .
	$(PNPM) $(WEB) run format

test: export CACHE_MODE = replay
test: export DEEPEVAL_DISABLE_DOTENV = 1
test: ## Python tests only
	$(UV) run pytest

up: ## Postgres (ParadeDB, :5433) and Redis (:6380) for this machine
	docker compose up -d --wait db redis

up-models: ## the embedding and reranker servers (TEI, :8081 and :8082); about 5 GB of RAM
	docker compose --profile models up -d --wait embed rerank

up-ingest: ## docling-serve (:5001) for parsing
	docker compose --profile ingest up -d --wait docling

down: ## stop every container of this project on this machine
	docker compose --profile models --profile ingest down

api: ## the API on :8000, with reload
	$(UV) run uvicorn plumbline.api.app:create_app --factory --reload --port 8000

web: ## the front end on :3000
	$(PNPM) $(WEB) run dev

openapi: ## Lane D: regenerate the OpenAPI schema, the stream fixture and the TypeScript client
	$(UV) run python -m plumbline.api.openapi > packages/ts-client/openapi.json
	$(UV) run python -m plumbline.api.fixtures > packages/ts-client/fixtures/ask-stub.sse
	$(PNPM) $(CLIENT) run generate

fetch: ## Lane B: fetch the fetch-only sources (the Dubai PDFs) and check their hashes
	$(UV) run python -m plumbline.corpus.fetch

ingest: ## Lane D: parse, chunk, embed and index the corpus (CACHE_MODE decides record or replay)
	$(UV) run python -m plumbline.ingest

eval-retrieval: ## Lane A: retrieval metrics for CONFIG (default A2) on SPLIT (default dev)
	$(UV) run python -m plumbline.eval.run --config $(CONFIG) --split $(SPLIT) --retrieval-only

eval: ## Lane A: retrieval and judged generation metrics for CONFIG on SPLIT
	$(UV) run python -m plumbline.eval.run --config $(CONFIG) --split $(SPLIT)

eval-gate: export CACHE_MODE = replay
eval-gate: export DEEPEVAL_DISABLE_DOTENV = 1
eval-gate: ## Lane A: the CI eval gate, against evals/baseline.json
	$(UV) run python -m plumbline.eval.gate

reproduce: export CACHE_MODE = replay
reproduce: export DEEPEVAL_DISABLE_DOTENV = 1
reproduce: ## every number in the README, rebuilt from committed recordings at zero API cost
	$(MAKE) up
	$(UV) run python -m plumbline.ingest
	$(UV) run python -m plumbline.eval.reproduce

static: ## the static export, in apps/web/out
	$(PNPM) $(WEB) run build

.PHONY: help setup check check-py check-web check-docs fmt test up up-models up-ingest down api web openapi fetch ingest eval-retrieval eval eval-gate reproduce static
