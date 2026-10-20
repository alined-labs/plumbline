# Security

What protects Plumbline's public demo, and how each control is checked. Lane P keeps this file; the reasoning is in [ADR-0011](adr/0011-security-controls.md) and [ADR-0007](adr/0007-routing-and-spend-caps.md). Plumbline gives legal information, never legal advice, and it is a demo: it holds no accounts, and the only personal data it handles is a lease a visitor uploads.

Every control is backed by a test (run by `make check` and CI) or by a manual check recorded with its date. A control marked *planned* is not in place yet; nothing else on this page is a promise.

## Control map

### Exposure

| Control | Where | Checked by |
| --- | --- | --- |
| No published port in production; the API is reached only through the Cloudflare Tunnel | `deploy/compose.prod.yaml` | `apps/api/tests/security/test_production_compose.py`; `deploy/prod ps` shows no `->` mapping; rehearsal of 2026-10-20 (`docs/runbook.md`) |
| Postgres and Redis on an internal network with no route out | `deploy/compose.prod.yaml` | manual, 2026-10-20: `redis` cannot connect to 1.1.1.1 |
| Forwarded headers trusted only from cloudflared's address | `FORWARDED_ALLOW_IPS` in `deploy/compose.prod.yaml` | manual, 2026-10-20: `X-Forwarded-For` honoured from 172.30.42.10, ignored from 172.30.42.77 |
| The quota counts a visitor by `CF-Connecting-IP`, which Cloudflare sets and no visitor can: only cloudflared reaches the API | `api/quota.py` (Lane D), `deploy/compose.prod.yaml` | `apps/api/tests/security/test_production_compose.py` (no published port, the API's networks) |
| The server's exposure: published ports, listeners, clock, updates, secret files | `deploy/preflight.sh` | run before each deploy; findings in `docs/runbook.md` |
| Containers: no new privileges; the API and cloudflared read-only with every capability dropped; the API image runs as an unprivileged user | `deploy/compose.prod.yaml`, `deploy/api/Dockerfile` | `apps/api/tests/security/test_production_compose.py`; CI migrates a fresh database with the image under `--read-only --cap-drop ALL` |
| Browser headers: CSP (fetches only to the site and the API, no framing), HSTS, nosniff, referrer and permissions policies | `deploy/pages/_headers` | manual, 2026-10-20: a local export with these headers, only Zod's guarded `eval` probe reported |
| CORS limited to the web origin, with credentials | `CORS_ORIGINS` | Lane D's API tests |
| Rate limits at the edge on `/api/ask` and `/api/check-lease`: 5 requests per 10 s per address | Cloudflare, the rule in `deploy/cloudflare/rate-limit.md` | `deploy/edge-check.sh` once live (a burst must meet a 429) *planned* |

### Secrets

| Control | Where | Checked by |
| --- | --- | --- |
| Production secrets in root-only files, each readable by one container's group; no value printed | `deploy/secrets-init.sh`, `/etc/plumbline` | `deploy/preflight.sh` checks owner, group and mode; the script was run as root in a container on 2026-10-20 |
| Keys reach the code only through `plumbline.settings`; a test session never holds the developer's `.env` | `settings.py`, `pyproject.toml` | `apps/api/tests/security/test_environment.py` |
| No secret in a commit | the pre-commit hook; gitleaks over each pull request's commits | CI's `secrets` job |
| The admin routes need the admin token, compared in constant time; unset, they do not exist | `api/admin.py` | Lane D's admin tests |

### Abuse and spend

| Control | Where | Checked by |
| --- | --- | --- |
| Daily question and lease-check quotas per visitor and per address | `api/quota.py` (Lane D) | `apps/api/tests/api/test_quota.py` |
| Daily spend caps per provider; the premium route only under Anthropic's cap | `generation/router.py` (Lane C) | Lane C's router tests |
| Kill switch: Gemini or Anthropic at 80% of its cap drops the tier to `free`, either at its cap drops it to `static`, the next UTC day restores it | `security/killswitch.py`, the `killswitch` service | `apps/api/tests/security/test_killswitch.py`; manual, 2026-10-20 (below) |
| Uploads at most 10 MB, PDF, DOCX or text only, read in memory, zip bombs refused | `ingest/upload.py` (Lane D) | `apps/api/tests/ingest/test_upload.py`, `apps/api/tests/api/test_check_lease.py` |
| A Word document's XML neither expands entities nor reads a file it points to; a lease's text never reaches a log line, a header or the start response | `ingest/upload.py`, `api/leases.py` (Lane D) | `apps/api/tests/security/test_uploads.py` |
| Errors as problem details that say nothing about internals | `api/problems.py` (Lane D) | `apps/api/tests/api/test_problems.py` |
| Every model configuration caps output at 1,024 tokens, and each provider's request carries the cap | `evals/configs/`, `generation/llm.py` | `apps/api/tests/security/test_output_cap.py` |
| Row-level security forced on every tenant table, keyed on the current tenant; the application role cannot bypass it; the only untenanted tables it writes are settings, eval_runs and eval_results | migrations (Lane D) | `apps/api/tests/security/test_isolation.py` |

### Personal data and content

| Control | Where | Checked by |
| --- | --- | --- |
| Every real upload redacted before any model call; amounts, periods, dates and clause headings kept; a failure refuses the upload | `security/redaction.py` (P2) | `apps/api/tests/security/test_redaction.py` (on its branch until P2 merges); until then `SyntheticOnlyRedactor` refuses every real upload |
| Lease checks only on the full tier, whose billed key's inputs are not used for training | `generation/router.py` | Lane C's router tests |
| Sources whose terms forbid republishing show only the quoted passage | `api/restricted.py` (Lane D) | `apps/api/tests/api/test_chunks.py` |
| Retrieved passages and uploads are data, never instructions: prompts carry them in delimited blocks | Lane C's prompts | Lane C's recorded prompt-injection set; the red team (P4) *planned* |
| Model output rendered as text, never as HTML: the API serves only JSON, problem details and event streams; the web app writes markup only in its theme script, and every Markdown renderer skips HTML | Lane E's answer components | `apps/api/tests/security/test_no_html.py` |

## Against the OWASP Top 10 for LLM applications

The 2025 list, risk by risk: what Plumbline does about each, and where it is checked. The
plan's minimum was LLM01, 02, 05, 07, 08, 09 and 10; the other three are here too, so
nothing is left unstated.

| Risk | What Plumbline does | Checked by |
| --- | --- | --- |
| LLM01 Prompt injection | Retrieved passages, uploads and the judge's inputs reach a model only inside delimited data-only blocks, with their tags defused (`generation/prompt.py`'s `defuse`); every prompt says the blocks are data. The model has no tool to call, so an injection can at most change one answer, which the citation check then reads | recorded injection sets: `apps/api/tests/generation/test_injection.py`, `apps/api/tests/judge/test_judge_injection.py`, `apps/api/tests/leases/test_injection.py`; the planted poisoned listing end to end and the Promptfoo run (P4) *planned* |
| LLM02 Sensitive information disclosure | Uploads redacted before any model call (P2); a lease is read in memory, never stored, logged or echoed; Dubai and Colombian sources show only the quoted passage; production keys only in root-only files; the stored nightly score holds no question or answer | `apps/api/tests/security/test_redaction.py` (on its branch until allowed), `test_uploads.py`, `apps/api/tests/api/test_chunks.py`, `test_online_eval.py`, `deploy/preflight.sh` |
| LLM03 Supply chain | Every image pinned by digest, Python locked with hashes (`uv.lock`), the spaCy models pinned by URL and hash, JavaScript locked; pip-audit and pnpm audit in CI; Dependabot; models come from their publishers' APIs or pinned weights | CI's audit jobs; `apps/api/tests/security/test_production_compose.py` (digests) |
| LLM04 Data and model poisoning | The corpus is nine official sources pinned by sha256 in a manifest and re-checked against the publishers; nothing a visitor sends is ever indexed; no model is trained or fine-tuned | `python -m plumbline.corpus.fetch --check` (Lane B, last run 2026-10-20); the poisoned listing (P4) *planned* |
| LLM05 Improper output handling | Model output is text, never HTML: the API serves JSON, problem details and event streams, and the web renders Markdown with HTML skipped; structured output is validated against its schema before use, and an answer's citations are verified against the retrieved text | `apps/api/tests/security/test_no_html.py`; `apps/api/tests/generation/test_schema.py`, `test_verifier.py` |
| LLM06 Excessive agency | None granted: no model has tools, writes, or reaches anything but its own prompt; the MCP server calls the public API with a visitor's limits | by construction (no tool definitions in `generation/llm.py`); the MCP server's tests once it merges (Lane D, held for allow) |
| LLM07 System prompt leakage | The prompts are in the public repository and hold no secret, key or rule that is not also enforced in code (caps, quotas, tiers, redaction are all outside the model) | by construction; the Promptfoo run (P4) *planned* |
| LLM08 Vector and embedding weaknesses | One index of public law, built only from the pinned corpus; tenant rows under forced row-level security; embeddings computed locally, so no text leaves for an embedding API | `apps/api/tests/security/test_isolation.py` |
| LLM09 Misinformation | An answer cites the article it relies on or abstains; each citation's quote is verified in the retrieved text, and an unverified one withdraws the claim; the as-of date filters the law; the disclaimer wherever an answer appears; quality published with intervals and a nightly judged sample | `apps/api/tests/generation/test_verifier.py`, `test_abstain.py`; `/evals`; `apps/api/tests/security/test_online_eval.py` |
| LLM10 Unbounded consumption | Edge rate limits, per-visitor daily quotas, output capped at 1,024 tokens, a law budget on long-context prompts, upload size and page limits, at most four lease checks at once, daily spend caps and the kill switch | the rows above under "Abuse and spend" |

## What is not covered

- **No formal penetration test, no SOC 2 or other certification.** The red team (P4) is automated and self-run.
- **No high availability.** Production is one home machine; when it is down, the static site on Pages stays up and says so, and nothing fails over.
- **No bot challenge.** The plan's Turnstile on `/api/ask` and `/api/check-lease` is not built: the edge rate limit, the daily quotas and the spend caps bound what a bot can cost, but not that it tries.
- **Redaction is pattern and model based.** A name the models miss and the lease never gives as a party gets through; real uploads stay off until P2 merges.
- **No off-machine backup yet.** A disk failure on MX3 loses the database with its dumps (`docs/runbook.md`, "Backups").
- **No managed WAF rules.** The Free plan's managed rules only; no custom firewall rules beyond the rate limit.

## The kill switch, triggered by hand (2026-10-20)

On the rehearsal stack (production Compose with scratch secrets, no tunnel), with the caps at Gemini US$0.30 and Anthropic US$1.00:

1. Tier `full`. `redis-cli INCRBYFLOAT spend:gemini:<today> 0.25` (above 80% of the cap): within 30 s the tier was `free`, and the switch logged `tier full lowered to free`.
2. `INCRBYFLOAT ... 0.06` (US$0.31, past the cap): within 30 s the tier was `static`.
3. The switch's mark back-dated to the day before and today's counter deleted, as at UTC midnight: within 30 s the tier was `full` again, logged as `a new UTC day, tier static restored to full`.

To repeat it on production, run the same commands through `deploy/prod exec redis redis-cli ...` and watch `GET /api/settings/tier`. Then reset: `deploy/prod exec redis redis-cli DEL spend:gemini:<today> killswitch:lowered`, and set the tier back through the admin route.

## Secrets inventory

| Secret | Lives in | Used by | Rotate by |
| --- | --- | --- | --- |
| Database password | `/etc/plumbline/db_password`, and inside `DATABASE_URL` in `api.env` | Postgres, the API, the kill switch | `ALTER USER plumbline PASSWORD ...` in `db`, then the same value in both files, then `deploy/prod up -d` |
| `ADMIN_TOKEN` | `api.env` | the admin routes (tier, jobs) | a new `openssl rand -hex 32` in `api.env`, then `deploy/prod up -d api` |
| `GEMINI_API_KEY` | `api.env` | generation | a new key in Google AI Studio, revoke the old one |
| `ANTHROPIC_API_KEY` | `api.env` | every answer and lease check (the site is served on Claude), the nightly online evaluation's judge | a new key in the Claude Console, revoke the old one |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | `api.env` | traces | a new key pair in Langfuse |
| Tunnel credentials | `/etc/plumbline/tunnel.json` | cloudflared | `cloudflared tunnel delete` and create again, or rotate in the dashboard; then `secrets-init.sh --tunnel` |
| `CLOUDFLARE_API_TOKEN` | GitHub, the `production` environment | `deploy.yml` (Pages only) | a new token scoped to Pages: Edit; delete the old one |
| `SONAR_TOKEN` | GitHub secrets | `sonar.yml` | a new token in SonarCloud |

A key that may have leaked is revoked first and rotated second. The build's own keys, in each developer's `.env`, are separate from production's and never copied into `/etc/plumbline`.
