# Journal

Dated working notes: what was tried, what was learned, what changed course. Newest first. Decisions that last go into an ADR; this is the trail that led to them.

## 2026-10-20: where a search's time goes (Lane A)

Measured on MX2 (4 cores, 8 GB) with `EXPLAIN (ANALYZE, BUFFERS)` and 20 timed runs, on the local index of Florida ch. 83 and ch. 718 under A2 (350 chunks, 268 with an embedding, one pg_search segment), pg_search 0.26.2, one question embedded by MX3's TEI. The statement is a/a5b-sql-retrieval's.

- **Dense is cheap.** The exact cosine leg computes all 268 distances and sorts them in 2.4 ms; the whole dense statement takes a median 4.1 ms. Exact search stays affordable far past this corpus: a few thousand leaves cost tens of milliseconds, so no approximate index is needed for Gate 1.
- **BM25 has a fixed cost.** Any pg_search query costs about 90 ms to execute here, whatever it matches: `key @@@ pdb.all()` over 350 rows takes 90 ms, the full BM25 leg 94 ms. The index has one segment, so it is not fragmentation; it looks like the cost of opening the index for each query.
- **Planning costs about 90 ms per search term in the SQL**, and it disappears when the statement is prepared. The hybrid statement names two fields (English and Spanish), so it plans in 183 ms; with only the English field, 91 ms. psycopg prepares a statement after its fifth run on a connection, and the retriever's text is the same for every question (every value is a bind parameter), so on a warm connection a repeated query skipped planning: 91 ms instead of 271 ms.
- **So a hybrid search costs about 100 ms on a warm connection, and about 280 ms on a cold one**, plus the question's embedding (about 300 ms round trip to MX3 for one short question, measured end to end at 320 ms for A2). The filters (variant, leaves, status, dates) change nothing measurable: pushing the variant into the query as a literal saved nothing.
- **To try on MX3** before Thursday: the same numbers on the production machine, and a pool large enough that the API's connections stay warm. If the 90 ms per query holds there, it is the largest part of retrieval and worth an issue with ParadeDB.
- **One property of the index to remember**: BM25's document frequencies are the whole index's, across every variant, so a borderline BM25 ranking can move when another variant is indexed. A retrieval test that ranked "Artículo 9" across jurisdictions flipped when other tests' rows were in the database (see a/a5b's test notes).

## 2026-10-20: the reranker on MX3's CPU

- bge-reranker-v2-m3 on MX3's TEI 1.9.4 CPU server (float32) took p50 33.4 s and p95 58.3 s to rerank 20 candidates per question, over 50 questions; the plan's budget was 1.5 s at p95. The candidates were real leaf chunks of the article-aware chunker over Fla. Stat. ch. 83, the LAU, Ley 820 and Dubai's Law No. 26, 20 per question from its own jurisdiction (95 reranker tokens at the median, 425 at p95). Results: `evals/results/rerank/benchmark.json`.
- A probe explains it: one short candidate costs half a second, five cost 2.6 s, twenty 10 s. Time is linear in tokens with no batching gain, about 110 GFLOP/s for a 568M-parameter model, so the CPU, not the other services on MX3, sets the cost.
- At 10 candidates: p50 16.1 s, p95 36.3 s (`benchmark-10.json`), half the 20-candidate time and still 24 times the budget. Neither of the plan's fallbacks reaches 1.5 s here, so ADR-0005 proposes reranking offline only (recorded once per pair) and answering online with Cohere on the full tier or the hybrid order without reranking.
- The benchmark took 32 minutes of MX3's CPU; a dev-split recording for one reranked configuration will take about 70.

## 2026-10-19: models, prices and the first answers (Lane C)

- Pinned from the providers' model pages: `gemini-3.5-flash-lite` for the fast route (the Flash-Lite Google points new projects to), `gemini-3.8-flash` for the strong and lease routes (the newest stable Flash; Google has no stable Pro yet), `claude-sonnet-5-5` for premium and `claude-haiku-5-5` for the judge. Their prices, read the same day, are in `generation/llm.py`; Gemini 3.8 Flash doubles on 2027-01-01, and the table already holds both prices.
- The SDKs had moved: anthropic 1.13 dropped `temperature` (current Claude models take no sampling parameters) and takes a raw JSON schema through `output_config`, and google-genai takes `response_json_schema`. Claude rejects `minimum`, `maximum` and `minLength` in a schema, so the answer schema folds its bounds into the descriptions, and Pydantic enforces them on parse.
- One answer schema works on all three providers. On a test prompt with an injected source, Flash-Lite, 3.8 Flash and Haiku all ignored the injection, all answered "partial" correctly (the Spanish source gives the deposit's size, not its return deadline), and Haiku glossed the Spanish quote. 3.8 Flash spent 661 thinking tokens on a 296-token answer.
- Google does not use paid-tier inputs for training (only the invite-only Contributor tier does), but it does use free-tier inputs, which is why lease checks run on the full tier only ([ADR-0007](../adr/0007-routing-and-spend-caps.md)).
- The first recorded answer through the pipeline cost $0.0007 on Flash-Lite (810 tokens in, 182 out): about 1,400 answers per dollar.

## 2026-10-19: where CI's time goes

- Over the twelve latest successful CI runs (pull requests and `main`, 23:37 to 23:52 UTC), the `web` job sets the wall time: 102 s on average, from 65 to 134 s, rising as the app shell added pages and tests. `python` takes 74 s, the image job 43 s and gitleaks 6 s. With the hub's own local check in front, a branch reaches `main` a few minutes after its push.
- Inside `make check-web` (91 s on E1b's run), Lighthouse takes 50 s for four pages, about 12 s a page; the e2e suite 14 s for 18 tests; the static build 12.5 s; format, lint, types and unit tests 12 s together. Lighthouse grows with every page it audits: ten pages would take it about two minutes.
- Installing Playwright's Chromium costs 22 s a run: 12 s of apt packages and 8.5 s of downloads. A browser cache could save only the downloads, less its own restore time, so CI goes without one.
- In the `python` job, starting the ParadeDB service takes 17 to 24 s, `make check-py` 23 to 34 s and pip-audit 15 to 20 s. Service containers start before any step runs, so their images cannot come from the Actions cache.
- On MX3, the e2e suites of Lane E's checkout, the hub's worktree and Lane P's all serve on port 3100, and Playwright reuses whatever server it finds there outside CI. The hub's check of PB2 failed that way at 23:45 UTC: every e2e test was refused once the other checkout's server stopped, while `main` was green on GitHub. One port per checkout would fix it; the file is Lane E's.

## 2026-10-19: the design system, before the build

- The Alined design system went into the seed before any lane started, so the front end is built on it from the first task and the placeholder token layer and Phase DS are gone.
- The tokens live once, in `apps/web/design/tokens.json` (W3C design tokens format, light and dark); `tokens.css`, the Tailwind theme and the contrast report are generated from it, and a unit test fails if they drift, if a colour pair falls under its WCAG 2.2 minimum, or if two colours that must be told apart come closer than 7 CIEDE2000, under normal vision and three simulated deficiencies.
- The theme resets Tailwind's colours, type sizes, radii, shadows and easings, so a class outside the system compiles to nothing instead of drifting.
- The logo is drawn with its own `brand` tokens: the accent turns lavender in the dark theme, and the bob disappeared against it. Focus on the inverse surface (the toast) has its own ring for the same reason.
- Fonts are self-hosted (Atkinson Hyperlegible Next and Mono, Source Serif 4 for the statutes' own words), icons are vendored from Lucide, and no dependency was added.

## 2026-10-19: the seed

- Cut the seed: the uv and pnpm workspaces, the frozen contracts (`core/types.py`, `core/config.py`, `core/stream.py`, `rag_eval/schema.py`), the record/replay cache, the statistics helpers, a stub pipeline that streams every part of the answer protocol, the static Next.js shell on placeholder tokens, and the gates (`make check-py`, `check-web`, `check-docs`, CI with gitleaks).
- The stream contract is pinned by a fixture: the exact bytes the stub streams are committed in `packages/ts-client/fixtures/ask-stub.sse`, and both the API tests and the browser tests read them.
- Chose pypdfium2 over PyMuPDF for page rendering and citation boxes: same capability, and its licence keeps the code Apache-2.0 clean (PyMuPDF is AGPL).
- Seven-day release-age policy on both ecosystems (`exclude-newer` for uv, `minimumReleaseAge` for pnpm).
