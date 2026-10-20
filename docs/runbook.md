# Runbook

How Plumbline runs in production on MX3, and what to do when something breaks. Lane P keeps
it; every command here has been run at least once, and the date it was last run is beside
each section. Commands run from a checkout of `main` on MX3 (the production checkout,
separate from the lanes' worktrees), as a user in the `docker` group unless they say `sudo`.

## The stack

`deploy/compose.prod.yaml`, the Compose project `plumbline-prod`, separate from the build's
project `plumbline` (`compose.yaml`): its own networks, volumes and containers.

| Service | Image | Networks | Memory | Health |
|---|---|---|---|---|
| `db` | ParadeDB 0.26.2, Postgres 18 | backend | 1 GiB | `pg_isready` |
| `redis` | Redis 8.10.2, append-only, `noeviction` | backend | 256 MiB | `redis-cli ping` |
| `embed` | TEI cpu-1.9.4, Qwen3-Embedding-0.6B, `--max-batch-tokens 4096` | backend, egress | 3 GiB | `GET /health` |
| `migrate` | the API image, `alembic upgrade head`, then exits | backend | 512 MiB | exit status 0 |
| `api` | `plumbline-api:prod`, built from `deploy/api/Dockerfile` | backend, egress | 2 GiB | `GET /api/health` |
| `cloudflared` | cloudflared 2026.10.0 | egress, fixed at 172.30.42.10 | 256 MiB | `cloudflared tunnel ready` |

- **Nothing publishes a port.** The public reaches the API only through the tunnel, which
  dials out to Cloudflare. `backend` is an internal network with no route out (checked:
  `redis` cannot open a connection to 1.1.1.1). `egress` gives the API its model providers
  and `embed` its first weights download.
- **Forwarded headers** are trusted from `172.30.42.10` only (`FORWARDED_ALLOW_IPS`). Checked
  on 2026-10-20: an `X-Forwarded-For` from that address is the logged client; the same
  header from 172.30.42.77 is ignored.
- **Every container** restarts unless stopped, runs with `no-new-privileges`, and keeps at
  most 5 × 10 MB of logs (Docker's `local` driver). The API and cloudflared run on read-only
  filesystems with every capability dropped.
- **Memory:** the stack's limits add up to 6.75 GiB. Until Friday MX3 also runs the build's
  TEI servers (about 2.2 GiB each), and on 2026-10-20 about 3 GiB was free with the build
  running, so the production embedder starts only after the build's reranker is stopped
  (`docker stop plumbline-rerank-1`; it is offline-only now).
- **Spend caps** are settings in the compose file (`GEMINI_DAILY_CAP_USD` and the like);
  `docs/cost-model.md` says why each is what it is.

## Secrets (last run: not yet)

Three files in `/etc/plumbline`, each owned by root and readable only by the group of the
one container user that needs it; no login on MX3 is in those groups, so the user running
Compose never reads them (Docker's daemon makes the bind mounts as root).

| File | Owner, mode | Read by | Holds |
|---|---|---|---|
| `db_password` | root:999, 0640 | Postgres | the database password, generated |
| `api.env` | root:10001, 0640 | the API, as `/app/.env` | `DATABASE_URL`, `ADMIN_TOKEN` (both generated), the provider and Langfuse keys |
| `tunnel.json` | root:65532, 0640 | cloudflared | the tunnel's credentials |

The human creates them; no value is ever printed:

```sh
sudo bash deploy/secrets-init.sh                       # db_password and api.env
sudo -e /etc/plumbline/api.env                         # uncomment and paste the keys
sudo bash deploy/secrets-init.sh --tunnel ~/.cloudflared/<tunnel-id>.json
rm ~/.cloudflared/<tunnel-id>.json                     # the copy in /etc/plumbline is the one used
bash deploy/preflight.sh                               # checks owner, group and mode of all three
```

## First deploy (last run: rehearsed without the tunnel and the embedder, 2026-10-20)

1. `bash deploy/preflight.sh`: no failure except the build's model ports (below).
2. The tunnel (the human, once): `cloudflared tunnel login`, then
   `cloudflared tunnel create plumbline-prod`; put the UUID it prints in `deploy/prod.env`
   (`TUNNEL_ID`), then `cloudflared tunnel route dns plumbline-prod plumbline-api.alinedlabs.co`.
3. The secrets, as above.
4. `deploy/prod build`, then `deploy/prod up -d --wait`. The first start downloads the
   embedding weights; `embed` may take several minutes to turn healthy.
5. The index, copied from the build's database once Lane A's embeddings are done:

   ```sh
   docker exec plumbline-db-1 pg_dump -U plumbline -d plumbline --data-only -t documents -t chunks -Fc |
     deploy/prod exec -T db pg_restore -U plumbline -d plumbline --data-only --disable-triggers
   ```

6. `deploy/prod ps`: every service healthy, `migrate` exited 0, and the PORTS column shows
   no `->` mapping.

`deploy/prod up` refuses to start while a secret file is missing or `TUNNEL_ID` is still zeros.

## MX3's preflight findings (2026-10-20)

`bash deploy/preflight.sh`: 9 ok, 6 warnings, 2 failures.

- **FAIL: the build's model servers publish 8081 and 8082 on 0.0.0.0** (`MODELS_BIND` in the
  build's `.env`), so the other lanes' machines can embed against them. They stay that way
  until Friday's v1.0.0, then go back to loopback (remove `MODELS_BIND` and
  `make up-models`). Production does not use them: it has its own embedder with no port.
- **WARN: listening beyond loopback:** NFS (111, 2049 and the RPC ports), Samba (139, 445)
  and saned (6566), all on the LAN. Nothing from the internet reaches them while the
  router forwards no port to MX3; the tunnel needs none.
- **WARN: no unattended security updates.** The human runs:

  ```sh
  sudo apt install unattended-upgrades && sudo dpkg-reconfigure -plow unattended-upgrades
  ```

- **WARN: the cloudflared CLI is not installed;** it is needed once for step 2.
- **WARN: the three secret files do not exist yet.**
