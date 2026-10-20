# Cost model

What Plumbline costs to build, to run and to keep alive, with a source for every number: an invoice or a provider's dashboard, a price page with the date it was checked, or a measurement in this repository with its commit. Cells marked *to fill* are still open; each section says who fills it and from what.

Per-token prices are not repeated here. They live in code, in `PRICES` in [`generation/llm.py`](../apps/api/src/plumbline/generation/llm.py), with the date they were checked (`PRICES_CHECKED`); every cost this document derives uses that table.

## 1. Budget

What there is to spend, as of 2026-10-20 (the planning decision "Run to Thursday"). Figures are prepaid balances, not credit lines: when one runs out, that provider stops.

| Item | Amount | Since | Source |
| --- | --- | --- | --- |
| Google AI Studio (Gemini), prepaid balance | US$4.73 left, no top-up coming | 2026-10-20 | billing page, as reported in the decision |
| Anthropic, prepaid credit | about US$25, and up to US$100 more this week if needed | 2026-10-20 | Claude Console, as reported in the decision |
| Cohere | none: configuration R1 is dropped | 2026-10-20 | the decision |

How it is rationed while building:

- **Gemini** answers Plumbline's own questions and runs the golden set's cross-check. The lanes together stop at **US$4.50 recorded** (Lane C's cost tally, `observability`, sums every recording), leaving US$0.23 of headroom for what is not recorded. Every Gemini run states its expected cost before it starts, and a run of more than 100 calls goes through Google's Batch API at half price.
- **Claude Haiku 5.5** (US$0.10 in and US$0.50 out per million tokens) does everything else: the contextual headers, the query rewrite, the red team's attacks.
- **Production** draws on the same balances from Thursday. Its daily caps (section 3) keep the worst day at US$1.30, and the kill switch takes the demo to `static` before Gemini's cap is passed.

## 2. Accounts, plans and the limits that matter

The accounts in use on 2026-10-20. "Limit" is what could stop the service or start a charge. Cells marked *to fill* are filled when the account is opened or rechecked before launch.

| Provider | Plan | Used for | Limit that matters | Price | Checked on |
| --- | --- | --- | --- | --- | --- |
| Google AI Studio | paid tier, prepaid | generation (fast and strong routes), lease checks, the golden cross-check | the prepaid balance (section 1); the paid tier's rate limits | per token, in `PRICES` | 2026-10-20 |
| Anthropic | prepaid credit | the premium route, the judge, Haiku for headers, rewrites and attacks | the prepaid balance; the Console's monthly spend limit | per token, in `PRICES` | 2026-10-20 |
| Langfuse Cloud | Hobby (free) | traces of each answer | the plan's monthly event allowance | free | *to fill* |
| Cloudflare | Free | DNS, the Tunnel, Pages, one rate-limiting rule | the free plan's single rate-limiting rule; Pages' 500 builds a month (we upload, we do not build there) | free | *to fill* |
| UptimeRobot | Free | checks of `/api/health` and the web root every 5 minutes | 50 monitors, 5-minute interval | free | *to fill* |
| SonarCloud | free for public repositories | the quality gate | the token must exist for the job to run | free | *to fill* |
| GitHub | free for public repositories | CI, Dependabot, secret scanning, the Pages deploy | Actions minutes are unlimited on public repositories | free | *to fill* |

Dropped and not in use: Cohere (R1 dropped), Sentry (dropped for now).

## 3. Daily caps and the worst month

Each provider has a daily spend cap. Once Lane C's router (C6) and the kill switch (P5) enforce them, reaching a cap drops the tier from `full` to `free`, then to `static`, and logs the event. The defaults are in [`settings.py`](../apps/api/src/plumbline/settings.py), and production may set others in its environment.

| Setting | Default | Production |
| --- | --- | --- |
| `GEMINI_DAILY_CAP_USD` | US$1.00 | *to fill* |
| `ANTHROPIC_DAILY_CAP_USD` | US$1.00 | *to fill* |
| `COHERE_DAILY_CAP_USD` | US$0.50 | *to fill* |
| `DAILY_QUESTIONS_PER_IP` | 30 | *to fill* |

At the defaults the caps add up to US$2.50 a day, so the worst possible 30-day month spends US$75 on models: three quarters of the API credit. That bound holds only once the caps are enforced; until C6 and P5 are merged, the caps are settings, not limits.

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
| Domain | *to fill* | yearly price ÷ 12 | registrar invoice for `alinedlabs.co` |
| Electricity for MX3 | *to fill* | average watts × 720 h ÷ 1,000 × price per kWh | a plug meter over a week; the electricity bill |
| Cloudflare (DNS, Tunnel, Pages, one rate-limiting rule) | US$0 | Free plan | section 2 |
| Monitoring (UptimeRobot, Langfuse) | US$0 | free plans | section 2 |
| Backups (nightly `pg_dump` on MX3, `docs/runbook.md`) | US$0 beyond MX3's electricity | local disk | the runbook |
| Models | at most US$1.30 a day: Gemini US$0.30 and Anthropic US$1.00 | the production caps (section 3), enforced by the router and the kill switch | the spend counters; the provider dashboards |

Gemini's US$4.73 lasts at least 15 days at its full production cap, and longer at real traffic: at US$0.0007 a fast-route answer, 400 questions a day would spend about US$0.28. When the balance is gone, Gemini refuses every call; the spend counters stop growing, so the kill switch does not notice, and the tier must be set to `static` by hand through the admin route.

## 6. Building: recording costs

Model calls are recorded once, while a lane builds, and replayed at zero cost by tests, the hub, CI and `make reproduce`. Each lane's `done` entry states how many calls it recorded and what they cost; this table collects them.

| Task | Calls recorded | Cost | Provider |
| --- | --- | --- | --- |
| *to fill* | | | |

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
