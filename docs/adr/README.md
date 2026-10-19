# Architecture decision records

One file per decision, numbered, never rewritten: a reversal is a new record that names the one it replaces. Each has a context, the decision, its consequences and the alternatives considered.

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-monorepo-and-postgres-only-hybrid-search.md) | One monorepo, and hybrid search inside Postgres | accepted |
| [0002](0002-home-server-behind-a-tunnel-with-a-static-tier.md) | Serve from a home server behind a tunnel, with a static tier as the floor | accepted |

Planned, written when their evidence exists: 0003 parsing and the OCR fallback; 0004 local embeddings; 0005 the reranker, with its latency numbers; 0006 thin orchestration, no LangChain in the core path; 0007 routing and spend caps; 0008 the CI evaluation gate; 0009 the judge and its calibration; 0010 the retrieval configuration; 0011 security controls; 0012 what was not built, and why.
