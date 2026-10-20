# Security

What protects Plumbline's public demo, and how each control is checked. Lane P keeps this file; the reasoning is in [ADR-0011](adr/0011-security-controls.md) and [ADR-0007](adr/0007-routing-and-spend-caps.md). Plumbline gives legal information, never legal advice, and it is a demo: it holds no accounts, and the only personal data it handles is a lease a visitor uploads.

Every control is backed by a test (run by `make check` and CI) or by a manual check recorded with its date. A control marked *planned* is not in place yet; nothing else on this page is a promise.

## Control map

### Exposure

| Control | Where | Checked by |
| --- | --- | --- |
| No published port in production; the API is reached only through the Cloudflare Tunnel | `deploy/compose.prod.yaml` | `deploy/prod ps` shows no `->` mapping; rehearsal of 2026-10-20 (`docs/runbook.md`) |
| Postgres and Redis on an internal network with no route out | `deploy/compose.prod.yaml` | manual, 2026-10-20: `redis` cannot connect to 1.1.1.1 |
| Forwarded headers trusted only from cloudflared's address | `FORWARDED_ALLOW_IPS` in `deploy/compose.prod.yaml` | manual, 2026-10-20: `X-Forwarded-For` honoured from 172.30.42.10, ignored from 172.30.42.77 |
| The server's exposure: published ports, listeners, clock, updates, secret files | `deploy/preflight.sh` | run before each deploy; findings in `docs/runbook.md` |
| Containers: no new privileges; the API and cloudflared read-only with every capability dropped; the API image runs as an unprivileged user | `deploy/compose.prod.yaml`, `deploy/api/Dockerfile` | CI migrates a fresh database with the image under `--read-only --cap-drop ALL` |
| Browser headers: CSP (fetches only to the site and the API, no framing), HSTS, nosniff, referrer and permissions policies | `deploy/pages/_headers` | manual, 2026-10-20: a local export with these headers, only Zod's guarded `eval` probe reported |
| CORS limited to the web origin, with credentials | `CORS_ORIGINS` | Lane D's API tests |
| Rate limits at the edge on `/api/ask` and `/api/check-lease` | Cloudflare (P7a) | *planned* |

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
| Uploads at most 10 MB, PDF, DOCX or text only, read in memory, zip bombs refused | `ingest/upload.py` (Lane D) | `apps/api/tests/ingest/test_upload.py` |
| Errors as problem details that say nothing about internals | `api/problems.py` (Lane D) | `apps/api/tests/api/test_problems.py` |
| Quotas, an output-token cap and the cross-tenant test hardened | P3 | *planned* |

### Personal data and content

| Control | Where | Checked by |
| --- | --- | --- |
| Every real upload redacted before any model call; amounts, periods, dates and clause headings kept; a failure refuses the upload | `security/redaction.py` (P2) | `apps/api/tests/security/test_redaction.py` (on its branch until P2 merges); until then `SyntheticOnlyRedactor` refuses every real upload |
| Lease checks only on the full tier, whose billed key's inputs are not used for training | `generation/router.py` | Lane C's router tests |
| Sources whose terms forbid republishing show only the quoted passage | `api/restricted.py` (Lane D) | `apps/api/tests/api/test_chunks.py` |
| Retrieved passages and uploads are data, never instructions: prompts carry them in delimited blocks | Lane C's prompts | Lane C's recorded prompt-injection set; the red team (P4) *planned* |
| Model output rendered as text, never as HTML | Lane E's answer components | P3's test *planned* |

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
| `ANTHROPIC_API_KEY` | `api.env` | the premium route | a new key in the Claude Console, revoke the old one |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | `api.env` | traces | a new key pair in Langfuse |
| Tunnel credentials | `/etc/plumbline/tunnel.json` | cloudflared | `cloudflared tunnel delete` and create again, or rotate in the dashboard; then `secrets-init.sh --tunnel` |
| `CLOUDFLARE_API_TOKEN` | GitHub, the `production` environment | `deploy.yml` (Pages only) | a new token scoped to Pages: Edit; delete the old one |
| `SONAR_TOKEN` | GitHub secrets | `sonar.yml` | a new token in SonarCloud |

A key that may have leaked is revoked first and rotated second. The build's own keys, in each developer's `.env`, are separate from production's and never copied into `/etc/plumbline`.
