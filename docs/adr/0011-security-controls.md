# ADR-0011: Bound the demo's exposure and spend with a tunnel, root-only secrets, redaction and a spend-driven kill switch

- Status: proposed
- Date: 2026-10-20

## Context

Plumbline is a public demo served from a home machine (MX3) on a budget of tens of dollars ([ADR-0002](0002-home-server-behind-a-tunnel-with-a-static-tier.md)). Gemini has US$4.73 left with no top-up coming; Anthropic about US$25. Anyone on the internet can ask questions, and the lease checker takes uploads, which are personal data. What we found while building it, on 2026-10-20:

1. MX3 also runs the build: its two model servers publish ports to the LAN until Friday, and NFS, Samba and saned listen there. Docker writes its iptables rules ahead of the host firewall, so a published port is reachable whatever `ufw` says.
2. Production holds one Gemini key on a billed project. The `free` tier ([ADR-0007](0007-routing-and-spend-caps.md)) refuses lease checks and the premium route, but its questions still go to that billed key, so `free` lowers spend and does not stop it; only `static` does.
3. The public site answers and checks leases on Claude whatever the tier (the human's call on 2026-10-20, `api/answering.py`), so the `free` tier spends on Claude too. The API refuses a live answer once Anthropic's cap is spent, and nothing checks Gemini's: a cap is a number in the settings until something acts on it.

## Decision

1. **Nothing is reachable except through the tunnel.** Production Compose publishes no port. cloudflared dials out to Cloudflare and forwards to the API; Postgres and Redis sit on an internal network with no route out. uvicorn trusts forwarded headers only from cloudflared's fixed address.
2. **Secrets are root-only files.** `/etc/plumbline` holds the database password, the API's settings file and the tunnel's credentials, each root-owned, mode 0640, in the group of the one container user that reads it. The human creates them with `deploy/secrets-init.sh`, which prints no value; the build's sessions never read them.
3. **Every real upload is redacted before any model call.** Presidio, with spaCy's medium English and Spanish models and pattern recognizers for identifiers in both languages, replaces names, places, addresses, identity numbers, phones, emails, bank and card numbers with typed placeholders. Amounts, periods and dates stay as written, and clause headings are never redacted, because the lease checker reads the law against them. A failure refuses the upload.
4. **A kill switch drives the tier from the spend counters**, as its own service, every 30 s:
   - `free` once either Gemini or Anthropic has spent 80% of its daily cap: lease checks stop, questions still get answers;
   - `static` once either has spent its whole cap: no model is called until the next UTC day.

   Both counters are fed by the API's metered clients, Claude's answers and lease checks included.

   It lowers the tier during a day and never raises it. On a later UTC day, once the counters allow, it restores the tier it replaced, unless the tier was set by hand in between.

## Consequences

- The production caps (Gemini US$0.30 a day, Anthropic US$1.00) bound the worst day at US$1.30. A call in flight when a threshold is crossed still completes, and the switch acts within 30 s plus the tier's 10-second cache, so the overshoot is the cost of the calls made in about 40 seconds.
- `static` stops the live chat for the rest of the UTC day; the static export and its stored answers stay up.
- A tier raised by hand while a cap is spent is lowered again at the next check. To serve more, raise the cap, not the tier.
- Redaction is pattern and model based: it can miss a name a model does not recognise. Real uploads stay off until P2 merges, and the full tier, the only one that takes uploads, runs on a billed key whose inputs are not used for training.
- Every control above has a test or a recorded manual check: the control map in [`docs/security.md`](../security.md).

## Alternatives considered

- **Publishing the API on the host behind `ufw`:** Docker bypasses `ufw`, and a mistake exposes the API without Cloudflare's rate limits.
- **Compose `env_file` for the secrets:** the Compose client reads it as the user who runs Compose, so the file would have to be readable by that user, and its values would show in `docker inspect`.
- **Caps enforced only in the router, call by call:** one more Redis read on every call, and still no way to reach `static`, which is what stops all spending on a single billed key.
- **A cloud budget alert:** Google's budget alerts arrive hours late and do not stop anything.
