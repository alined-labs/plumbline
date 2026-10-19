# ADR-0002: Serve from a home server behind a tunnel, with a static tier as the floor

- Status: accepted
- Date: 2026-10-19

## Context

The live demo must stay up for months while the project is used in interviews, on a budget measured in tens of dollars: a US$100 API credit and a one-month cloud credit. The local models (the embedder and the reranker) need about 5 GB of RAM. Four home machines are available, one of them with 16 GB that can run the stack continuously.

## Decision

1. The API, Postgres, Redis and the model containers run under Docker Compose on the 16 GB home machine, reached only through a Cloudflare Tunnel (no open ports), with Cloudflare's WAF and rate limits in front.
2. The front end is a Next.js static export on Cloudflare Pages that calls the API from the browser.
3. A degradation ladder behind `DEMO_TIER`: `full` (premium route on), `free` (free-tier models only), `static` (the export alone, with `/evals`, `/about` and a replay chat serving stored answers for the golden questions). The static tier needs no server at all, so the project never goes fully dark.

## Consequences

- Running cost is the domain and electricity; model spend is capped per provider per day, and the kill switch drops the tier automatically.
- Availability depends on a home connection and one machine; monitoring (UptimeRobot, Sentry) and the static floor make an outage visible and survivable rather than impossible.
- The runbook must take a clean machine to live in under an hour, and backups go nightly to a second machine.

## Alternatives considered

- A managed cloud deployment (Azure Container Apps, Fly.io): the credit lasts a month, and the models' memory makes the cheapest tiers unworkable.
- Vercel Hobby for the front end: its terms are non-commercial, and the static export needs no Node host.
- Serverless model APIs for embeddings and reranking: per-call cost and a dependency the static replay cannot remove.
