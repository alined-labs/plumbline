# Cost model

What Plumbline costs to build, to run and to keep alive, with a source for every number: an invoice or a provider's dashboard, a price page with the date it was checked, or a measurement in this repository with its commit. Cells marked *to fill* are still open; each section says who fills it and from what.

Per-token prices are not repeated here. They live in code, in `PRICES` in [`generation/llm.py`](../apps/api/src/plumbline/generation/llm.py), with the date they were checked (`PRICES_CHECKED`); every cost this document derives uses that table.

## 1. Budget

The budget behind [ADR-0002](adr/0002-home-server-behind-a-tunnel-with-a-static-tier.md) is measured in tens of dollars.

| Item | Amount | Since | Source |
| --- | --- | --- | --- |
| API credit | US$100 | *to fill* | ADR-0002 |
| Cloud credit | one month | *to fill* | ADR-0002 |
| Google AI Studio, prepaid balance | *to fill* | *to fill* | billing page |
| Anthropic, prepaid credit and spend limit | *to fill* | *to fill* | Claude Console |

## 2. Accounts, plans and the limits that matter

The human fills this table when each account is opened (task H2) and rechecks it before launch. "Limit" is the quota that could stop the service or start a charge.

| Provider | Plan | Used for | Limit that matters | Price | Checked on |
| --- | --- | --- | --- | --- | --- |
| Google AI Studio | paid tier, prepaid | generation (fast and strong models) | *to fill* | per token, in `PRICES` | *to fill* |
| Anthropic | prepaid credit with a spend limit | the premium route and the judge | *to fill* | per token, in `PRICES` | *to fill* |
| Cohere | trial key | the API reranker comparison (R1) | *to fill* | *to fill* | *to fill* |
| Langfuse Cloud | Hobby (free) | traces, cost and error alerts | *to fill* | *to fill* | *to fill* |
| Cloudflare | *to fill* | domain, Tunnel, Pages, WAF, rate limits, Turnstile | *to fill* | *to fill* | *to fill* |
| SonarCloud | free for public repositories | the quality gate | *to fill* | *to fill* | *to fill* |
| UptimeRobot | *to fill* | uptime checks on `/api/health` and the web root | *to fill* | *to fill* | *to fill* |
| Sentry | *to fill* | errors in the API and the web | *to fill* | *to fill* | *to fill* |
| GitHub | free for public repositories | CI, Dependabot, secret scanning | *to fill* | *to fill* | *to fill* |

## 3. Daily caps and the worst month

Each provider has a daily spend cap. The router (C6) sends premium questions to the strong route once Anthropic's cap is spent, and the kill switch (P5, [ADR-0011](adr/0011-security-controls.md)) drives the tier: `free` once Gemini or Anthropic has spent 80% of its cap, `static` once either has spent its whole cap, logging each change and restoring the tier the next UTC day. The site answers on Claude on every tier but `static`, and production holds one billed Gemini key, so `free` lowers spend but only `static` stops it. The defaults are in [`settings.py`](../apps/api/src/plumbline/settings.py); production sets its own in [`deploy/compose.prod.yaml`](../deploy/compose.prod.yaml).

| Setting | Default | Production |
| --- | --- | --- |
| `GEMINI_DAILY_CAP_USD` | US$1.00 | US$0.30 |
| `ANTHROPIC_DAILY_CAP_USD` | US$1.00 | US$5.00 |
| `COHERE_DAILY_CAP_USD` | US$0.50 | US$0 (R1 dropped) |
| `DAILY_QUESTIONS_PER_IP` | 30 | 30 |

At production's caps the worst day spends US$5.30 on models (US$5.00 on Claude, US$0.30 on Gemini), plus the calls in flight during the switch's reaction time (about 40 s: a 30-second check and the tier's 10-second cache); the API also refuses a live answer itself once Anthropic's cap is spent, so the overshoot is at most the answers already streaming. The human set the Anthropic cap on 2026-10-20 (relayed by Lane D): the Anthropic key has a US$25 spend limit, and at most US$100 is spent in all, so Claude spending inside these limits needs no further question.

The worst 30-day month at the caps would be US$159, but two hard limits end it sooner: the Anthropic key's US$25 limit lasts at least five full-cap days (Tuesday 20 October to the end of launch week, shared with the lanes' judged dev runs), and Gemini's US$4.73 at least fifteen. When either balance is spent its counter stops growing; the kill switch then sees the answers fail (three exceptions in a row) and sets `static` itself, and the tier can also be set to `static` by hand ([runbook](runbook.md#set-the-tier-by-hand)), and the static tier carries the demo from there.

What the Anthropic cap buys, at the per-answer costs measured on 2026-10-20 (Lanes C and D): the tier drops to `free` once the day's spend reaches US$4.00 and to `static` at US$5.00.

| Served answer | Cost each | `free` after answer | `static` after answer |
| --- | --- | --- | --- |
| A2-claude, the served configuration (24,418 input tokens, Florida) | US$0.054 | 75th | 93rd |
| Long context, the whole law uncached | US$0.144 | 28th | 35th |
| Long context, a repeat question on the cached law prefix (C14) | US$0.011 | 364th | 455th |

## 4. Cost per question

Measured, not estimated: from the usage that every recorded model call carries, priced with `PRICES`, over the dev split of the golden set (Lane C's traces, C7, and the evaluation runs). Embedding and reranking run locally, so they cost electricity, not tokens; the API reranker is the exception.

| Tier | Model calls per question | Median input tokens | Median output tokens | Cost per question | Cost per 1,000 questions | Measured at |
| --- | --- | --- | --- | --- | --- | --- |
| `full` | *to fill* | *to fill* | *to fill* | *to fill* | *to fill* | *commit, date* |
| `free` | *to fill* | *to fill* | *to fill* | *to fill* | *to fill* | *commit, date* |
| `static` | 0 | 0 | 0 | US$0 | US$0 | stored answers only |

Questions a day each cap pays for: the cap divided by the cost per question of the tier that uses that provider. *To fill* once the table above is.

## 5. Running costs

| Item | Per month | How it is computed | Source |
| --- | --- | --- | --- |
| Domain | *to fill* | yearly price ÷ 12 | registrar invoice |
| Electricity for the server | *to fill* | average watts × 720 h ÷ 1,000 × price per kWh | a plug meter over a week; the electricity bill |
| Cloudflare (Tunnel, Pages, WAF, Turnstile) | *to fill* | plan price | Cloudflare dashboard |
| Monitoring (UptimeRobot, Sentry, Langfuse) | *to fill* | plan prices | section 2 |
| Backups (nightly `pg_dump` to a second home machine) | *to fill* | that machine's share of electricity | as above |
| Models | at most the caps (section 3) | measured spend | provider dashboards; the spend counters |

## 6. Building: recording costs

Model calls are recorded once, while a lane builds, and replayed at zero cost by tests, the hub, CI and `make reproduce`. Each lane's `done` entry states how many calls it recorded and what they cost; this table collects them.

| Task | Calls recorded | Cost | Provider |
| --- | --- | --- | --- |
| C1 to C10, CB1, CB2 (Lane C, 19 October): clients, answer prompt, pipeline, judge, lease checker, injection sets | 29 | US$0.0392 | Gemini (3.5 Flash-Lite, 3.8 Flash) |
| | 8 | US$0.0013 | Anthropic (Haiku 5.5) |
| C11, the golden cross-check: 180 drafts and 12 planted errors, Batch API (88 calls fetch-only) | 192 | US$0.2309 | Gemini (3.8 Flash) |
| C9, the judge on constructed labels: 105 rows written, 200 verdicts (56 calls fetch-only) | 305 | US$0.1176 | Anthropic (Haiku 5.5) |
| C9, the second judge on the same rows, Batch API (56 calls fetch-only) | 200 | US$0.0747 | Gemini (3.5 Flash-Lite) |
| C7b, one long-context answer from the Florida index, traced | 1 | US$0.0357 | Gemini (3.8 Flash) |
| CB3, the injection set against the lease checker | 26 | US$0.3260 | Anthropic (Sonnet 5.5) |

Spent but not recorded, so missing from the tally (`python -m plumbline.observability.spend`): about US$0.05 of Gemini on 20 October (a pilot whose replies ignored the schema, two diagnostic batches that found why, and a long-context answer cut off by its thinking, each deleted with the request it answered) and about US$0.05 of Haiku (two builds of C9's rows, replaced). The tally reads the working tree, so a checkout sees only the recordings of the branch it is on; run it on `main` plus your own branch.

## 7. Load and latency

k6 at 1 request per second for 10 minutes against `/api/ask` on the server (Lane P, P8), once per reranker. The targets: p95 at or under 6 s with the local reranker, and at or under 3 s with the API reranker.

| Reranker | p50 | p95 | Error rate | Target p95 | Server, commit, date |
| --- | --- | --- | --- | --- | --- |
| local (TEI) | *to fill* | *to fill* | *to fill* | 6 s | *to fill* |
| API | *to fill* | *to fill* | *to fill* | 3 s | *to fill* |

## 8. Keeping it current

- A price change goes into `PRICES` as a new entry with its `valid_from` date (Lane C), never as an edit of the old one, so past runs keep their cost.
- Sections 4 and 7 are refilled after any change to the default configuration, the prompts or the server, with the commit they were measured at.
- Sections 1, 2 and 5 are rechecked before launch and then monthly, at the same time as the provider dashboards.
