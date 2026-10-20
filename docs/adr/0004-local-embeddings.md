# ADR-0004: Embed locally with Qwen3-Embedding-0.6B on TEI, searched exactly in Postgres

- Status: proposed
- Date: 2026-10-20

## Context

The dense leg of retrieval needs an embedding model that reads English questions and English and Spanish statutes, and every vector must replay from a recording so that `make reproduce` rebuilds every number at no cost. The machines have no GPU; MX2 has 8 GB, MX3 runs the model servers. The corpus is small: about 3,000 chunks per variant across the four jurisdictions, roughly 120,000 to 150,000 tokens of distinct text per variant.

## Decision

1. **Qwen3-Embedding-0.6B** (1,024 dimensions), served by Hugging Face's Text Embeddings Inference (TEI 1.9.4, CPU, float32) on MX3. It is multilingual, small enough for a CPU, open-weight, and its card states its query format, which `retrieval/embed.py` follows exactly: queries carry the card's instruction (`Instruct: ...\nQuery:...`), documents none.
2. **Every vector is a recording.** Each text is embedded once and stored under `cache/embed/` (committed sources) or the fetched cache (Dubai and Colombian text), so indexing and evaluation replay without the server; only new texts reach it, 32 to a request.
3. **Only leaves are embedded**: paragraphs, and articles without paragraphs. A parent article with paragraphs keeps no vector; the parent merge hands it to generation whole. No input approaches TEI's 4,096-token cap.
4. **Exact search, no approximate index.** The dense leg computes every distance inside the filtered set (`retrieval/sql.py`); on MX2's index that costs 4 ms. An HNSW index would add recall loss for no measurable gain at this size.
5. **The variant names the model.** `variant_key(config)` hashes the chunker, the header setting and the embedding model, so a second model (E1, BGE-M3, also 1,024 dimensions) indexes rows of its own in the same table.

## Consequences

- First recording is slow and replay is free: MX3 embeds about 50 tokens a second (61, 55 and 45 tokens/s for 1, 8 and 32 texts of 82 tokens), about an hour per 200,000 tokens. A0 and A2 for Spain and Colombia need about 1.3 hours, once (Lane D's ingest plan, 2026-10-20).
- A question's embedding costs one round trip to MX3 at answer time, about 300 ms; the question is recorded like any text, in the committed cache, since it holds no source text.
- A configuration whose text changes (a header setting, a chunker) re-embeds its distinct texts; unchanged paragraphs repeated across BOE versions share one recording.
- The query instruction is the card's generic example; a task-specific one may gain a few points (the card reports 1% to 5%), and trying it means re-embedding only the questions.

## Alternatives considered

- **A hosted embedding API** (Gemini, OpenAI): faster to record, but a paid call per text and per question, a key in CI for any new text, and Dubai and Colombian text sent to a third party; the budget and the licences both argue against it.
- **BGE-M3**: also multilingual and 1,024-dimensional, about three times the parameters; kept as ablation E1 if MX3's CPU has room.
- **An English-only model**: half the corpus is Spanish and every question is English, which is what a multilingual model is for.
- **HNSW in pgvector**: unnecessary at this size, and approximate.
