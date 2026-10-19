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
