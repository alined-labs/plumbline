# Ingestion: from a source file to the index

`make ingest` turns the corpus manifest into rows in Postgres. It runs three stages, each of which can be skipped when its output is current, and each of which leaves its result where the next lane can read it without running the stage.

```
manifest ──► parse ──► chunk ──► embed ──► index
 (B)          (D)       (A)       (A)       (D)
             data/processed        cache/embed        chunks table
```

```bash
make up                      # Postgres and Redis
make ingest                  # parse, chunk, embed and index A0 and A2, the baseline of Gate 1
uv run python -m plumbline.ingest --source fl-stat-83-2026 --configs A2
uv run python -m plumbline.ingest --parse-only
```

`make ingest` brings the database to the current schema first, so a fresh clone needs nothing else. The exit status is 0 when every parsed source is indexed in every variant asked for, and 1 when one is not: a source that could not be chunked or embedded is named in the log and left out, and the others go on.

## Stage 1: parse

Each manifest source becomes one `ParsedDocument` in `data/processed/<source_id>.json`: Markdown per page, and for each page the method that produced it (`html`, `text_layer`, `vision`). The parse is reused while two things match: the source's `sha256` and the reader's version (`ParsedDocument.parser`). A parse made by an older reader is stale and is made again.

| Source format | Reader | What it keeps |
| --- | --- | --- |
| `html` | `ingest/html.py`, one profile per publisher host | the law's text, one block per paragraph; struck-through words as `~~text~~`; the Colombian Senate's validity notes as quotes |
| `xml` | `ingest/boe.py`, the BOE's open data | every version of every article, each after a line `<!-- plumbline:version block=a9 norm=BOE-A-2019-3108 published=… effective=… -->`; the BOE's notes as quotes |
| `pdf` | `ingest/parse.py`, docling-serve one page per call | each page's Markdown; a page keeps its raw text layer when docling drops more than a tenth of its words; a page with no text layer is transcribed by Gemini (`ingest/vision.py`) |

Notes are always written as `> ` quotes: they are never the law in force. A host without a profile, a page without its container and bytes that are not the declared charset are errors, never an empty parse.

Docling and the vision model are called through the cache (`kind: parse`), so a parse that was recorded replays without either.

## Stage 2 and 3: chunk, embed, index

For each variant of the configurations asked for, and each parsed source, one job in `ingestion_jobs` (`kind: index`):

1. **Chunk** with Lane A's chunker. A configuration's *variant* is a hash of what changes a chunk row's content: the chunker settings, the header mode and the embedding model (`retrieval/index.py`). Configurations that differ only in how they search (A1, A2, A3) share a variant, and so share rows.
2. **Embed** the leaves only, 32 texts at a time through TEI, each batch recorded as it returns. A leaf is a chunk no other chunk names as its parent: the dense leg searches paragraphs, and an article without numbered paragraphs is its own leaf. A parent keeps no vector and is found by BM25. Identical texts (an unchanged paragraph in every version of an article) are embedded once.
3. **Index**: the document's row and its chunks in one transaction, replacing that variant's earlier chunks of the document.

A job carries its configuration and a content hash (the source's text, the reader, the variant, the model and every field of every chunk), so a worker rebuilds the unit from the job alone and refuses to run if any of them changed since it was queued. The index, not the job log, decides what is done: a unit whose job succeeded is skipped while the index still holds its chunks and vectors, and runs again when it does not.

Progress is appended to the job's events as it happens. With the API running:

```bash
curl -N -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/api/admin/jobs/<id>/events
```

## What a run produces

On the committed Florida chapters, `make ingest` (A0 and A2) writes four units from 319 recorded embeddings, with no model server, in about a second:

| variant | source | chunks | with a vector |
| --- | --- | --- | --- |
| A0, fixed 800-token | `fl-stat-83-2026` | 22 | 22 |
| A0 | `fl-stat-718-2026` | 29 | 29 |
| A2, article-aware | `fl-stat-83-2026` | 181 | 153 |
| A2 | `fl-stat-718-2026` | 118 | 115 |

The 28 and 3 chunks without a vector are the articles whose numbered paragraphs carry theirs. Recording them took about 27 minutes of MX3's CPU, once; replaying them takes no model.

Spain and Colombia joined A2 on 20 October (Lane D, D4b), indexed on MX1 with embeddings from MX3's TEI. The run took about 39 minutes, most of it waiting on a busy embedding server:

| variant | source | chunks | with a vector | articles | unique texts embedded |
| --- | --- | --- | --- | --- | --- |
| A2 | `es-lau-boe-2026-10-13` | 929 | 762 | 232 | 334 |
| A2 | `es-lph-boe-2026-10-05` | 447 | 393 | 92 | 183 |
| A2 | `co-ley-820-senado-2026-10-15` | 153 | 136 | 43 | 131 |
| A2 | `co-ley-675-senado-2026-10-15` | 264 | 221 | 87 | 221 |

The "articles" are top-level chunks, versions included: the chunker keeps each dated version of a Spanish article apart. Spain's 517 embeddings are committed under `cache/embed`, so a fresh clone indexes Spain with no model server. Colombia's embeddings hold its text, which is fetch-only, so they are recorded only in the git-ignored `data/corpus/fetched/cache`. A clone without that cache reports the Colombian sources and skips them. Dubai and the A0 variant of every new source wait for Lane A's A3c.

## The index

`chunks` is keyed `(variant, id)`. Every query names its variant. The vector is exact cosine distance (`vector(1024)`, no HNSW: the corpus is a few thousand rows). BM25 (`pg_search`) has one field per language over that language's rows, with `unicode_words`, which keeps `83.49` as one token. `tests/db/test_search_index.py` is the reference for querying both. Row-level security applies to every table with a `tenant_id`; the statutes belong to a fixed public tenant that every tenant reads, and the application reaches them only through `tenant_session` (async) or `tenant_session_sync` (a worker thread).

## Fetch-only sources, and what is committed

A source whose licence does not let us redistribute it (Dubai's laws, Colombia's Senate pages) is not committed. Neither may its parse, which holds the whole text, nor any recording whose request holds its text (docling's, the vision model's, the embedder's). They stay under `data/corpus/fetched/`, which git ignores:

```
data/corpus/fetched/<source file>        make fetch
data/corpus/fetched/processed/<id>.json  its parse
data/corpus/fetched/cache/<kind>/…       its recordings
```

| | committed sources | fetch-only sources |
| --- | --- | --- |
| the file | `data/corpus/raw/` | `data/corpus/fetched/` |
| its parse | `data/processed/` | `data/corpus/fetched/processed/` |
| docling, vision, embedding recordings | `cache/` | `data/corpus/fetched/cache/` |

In replay mode (CI, the hub, `make reproduce`) a fetch-only source that this machine never parsed is reported and skipped, so a fresh clone indexes the committed jurisdictions and says what it left out. After `make fetch` and `make up-ingest`, `CACHE_MODE=record make ingest` parses and embeds the rest locally.

## Adding a source

1. Lane B adds the source to `corpus/fetch.py`'s table and runs `make fetch`, which writes its manifest row.
2. If it is HTML from a new publisher, add a profile to `ingest/html.py` (the element that holds the law, and what inside it to drop) with a test on an excerpt of its markup.
3. Add the law's short name to `ingest/laws.py` (until the manifest carries it).
4. The chunker needs a profile for the numbering of its articles (Lane A).
5. `make ingest`, and check the log: one line per source with its pages or chunks, and the totals.

## When something is wrong

| What you see | Why |
| --- | --- |
| `has no current parse: run make ingest` | the parse is missing or stale; run the parse stage |
| `no embed recording` (replay mode) | the chunks changed since the embeddings were recorded; `CACHE_MODE=record make ingest` with the embedding server up (`make up-models`, or `EMBED_URL`) |
| `is not what this job was queued for` | the source, reader, chunker or configuration changed after the job was queued; run `make ingest` again |
| `page N has no text layer and no vision reader` | a scanned page and no Gemini key in record mode |
| `<source> in <config>: cannot be chunked, so it is not indexed: …` | the chunker refused that source in that variant (the reason follows); the other sources are indexed and the run exits 1. A source with no short name in `ingest/laws.py` is one cause |
| `source is not on this machine (make fetch)` | a fetch-only source that has not been fetched; skipped on purpose |
