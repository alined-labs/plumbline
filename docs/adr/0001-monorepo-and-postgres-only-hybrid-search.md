# ADR-0001: One monorepo, and hybrid search inside Postgres

- Status: accepted
- Date: 2026-10-19

## Context

Plumbline has an API and pipeline in Python, a front end in TypeScript, a benchmark harness that will be published on its own, a generated client, and an MCP server. Six parallel lanes build it, and every change passes one gate. Retrieval needs dense vectors, keyword search with per-language analysis, metadata filters (jurisdiction, language, as-of date) and tenant isolation, over a corpus of a few thousand chunks.

## Decision

1. One repository with a uv workspace (`apps/api`, `packages/rag-eval`) and a pnpm workspace (`apps/web`, `packages/ts-client`), one lockfile per ecosystem, and one `Makefile` as the interface every lane, the hub and CI share.
2. All retrieval runs in Postgres: pgvector for dense search (exact, no approximate index at this size), ParadeDB's `pg_search` for BM25, Reciprocal Rank Fusion (k = 60) in SQL, and the metadata filters and row-level security in the same query.

## Consequences

- A contract change (an OpenAPI field, a stream part, a golden-set field) lands in one commit with every consumer, and one gate checks the whole system.
- One datastore to back up, restore and secure; filters and fusion are transactional and testable with plain SQL.
- `rag-eval` must stay free of `plumbline` imports so it can ship to PyPI alone; the dependency only points the other way.
- The repository is larger to clone, and the gate chooses its target by path so documentation and front-end branches do not pay for the whole build.

## Alternatives considered

- Separate repositories per app: contract drift between them, and no single gate.
- A dedicated vector database (Qdrant, Weaviate) beside Postgres: a second store to operate for no gain at this corpus size, and fusion and filters would move into application code.
- Elasticsearch or OpenSearch for BM25: heavier to run on an 8 GB machine than an extension in the database we already need.
