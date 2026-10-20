# Architecture decision records

One file per decision, numbered, never rewritten: a reversal is a new record that names the one it replaces. Each has a context, the decision, its consequences and the alternatives considered.

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-monorepo-and-postgres-only-hybrid-search.md) | One monorepo, and hybrid search inside Postgres | accepted |
| [0002](0002-home-server-behind-a-tunnel-with-a-static-tier.md) | Serve from a home server behind a tunnel, with a static tier as the floor | accepted |
| [0003](0003-parsing-and-the-vision-fallback.md) | Read HTML in code, PDFs page by page through docling, and scans with a vision model | proposed |
| [0004](0004-local-embeddings.md) | Embed locally with Qwen3-Embedding-0.6B on TEI, searched exactly in Postgres | proposed |
| [0005](0005-the-reranker.md) | Rerank offline only with bge-reranker-v2-m3, at 10 candidates; nothing reranks online | proposed |
| [0006](0006-thin-orchestration.md) | Thin orchestration over the provider SDKs, with no LangChain in the core path | proposed |
| [0007](0007-routing-and-spend-caps.md) | Route each request by a rule, under the demo tier and daily spend caps | proposed |
| [0011](0011-security-controls.md) | Bound exposure and spend with a tunnel, root-only secrets, redaction and a spend-driven kill switch | proposed |

Planned, written when their evidence exists: 0008 the CI evaluation gate; 0009 the judge and its calibration; 0010 the retrieval configuration; 0012 what was not built, and why.
