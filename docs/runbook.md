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

## Backups (last run: rehearsed, 2026-10-20)

`deploy/backup.sh` dumps the whole production database every night at 03:30 UTC
(`pg_dump --format=custom`), keeps it only if `pg_restore --list` reads it back, and deletes
dumps older than 14 days. The dumps hold visitors' queries and feedback, so
`~/plumbline-backups` is 0700 and each file 0600. Install the timer once, as the user who
runs the stack, from the production checkout at `~/plumbline-prod`:

```sh
mkdir -p ~/.config/systemd/user
cp deploy/systemd/plumbline-backup.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now plumbline-backup.timer
sudo loginctl enable-linger "$USER"     # user timers run without a login session
systemctl --user list-timers plumbline-backup.timer
```

**Prove a backup restores** at least once a week, and after any migration:

```sh
bash deploy/restore-test.sh ~/plumbline-backups/plumbline-<stamp>.dump
```

It restores into a throwaway container on the production image and prints every table's
row count beside production's. Rehearsed on 2026-10-20 on the rehearsal stack with 25
seeded tenants and a settings row: restored in 1 s, every count equal, schema 0005. The
index was still empty that day (the embeddings run overnight), so the test is repeated
on Wednesday with the real index, and its time goes here.

**Restore production** (not run yet; it replaces the live data, so stop the API first; `template0`, because the image puts ParadeDB's own schema in new databases from `template1`):

```sh
deploy/prod stop api killswitch
deploy/prod exec -T db dropdb -U plumbline --force plumbline
deploy/prod exec -T db createdb -U plumbline -T template0 plumbline
deploy/prod exec -T db pg_restore -U plumbline -d plumbline --exit-on-error < ~/plumbline-backups/plumbline-<stamp>.dump
deploy/prod up -d --wait
```

A copy off this machine (the second home machine in `docs/cost-model.md`) is not set up
yet; until it is, a disk failure on MX3 loses the backups with the database.

## Online evaluation (last run: not yet; tested on a seeded database, 2026-10-20)

Every night at 04:15 UTC, `python -m plumbline.security.online_eval` judges a tenth of
yesterday's production answers (at least one, at most 30) for faithfulness against the
passages they cite, with the calibrated judge (Claude Haiku), live and never recorded. It
logs the expected cost before it judges (at most US$0.30 a night, counted on the same
daily Anthropic counter as the site) and stores the night as eval run `online-<day>`:
the score with its 95% interval, and one verdict per judged answer, with no question or
answer copied. Install the timer once, beside the backup's:

```sh
cp deploy/systemd/plumbline-online-eval.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now plumbline-online-eval.timer
```

By hand, for one day (`--dry-run` counts and prices without judging):

```sh
deploy/prod run --rm --no-deps api python -m plumbline.security.online_eval --day 2026-10-22 --dry-run
```

Read a night's score: `deploy/prod exec -T db psql -U plumbline -c "select summary from eval_runs where run_id = 'online-2026-10-22'"`.

## Set the tier by hand

The admin token lives in the root-only `api.env`, so on MX3 the tier is set in the
database, the row the admin route writes; every API worker rereads it within 10 seconds,
and the kill switch treats a tier set by hand as the human's and never raises it back.
Set `static` when a provider's balance or key limit is spent (its counter then stops
growing, so the kill switch cannot see it; `docs/cost-model.md`, section 3), and `full`
to bring the live demo back:

```sh
deploy/prod exec -T db psql -U plumbline -d plumbline -c "insert into settings (key, value, updated_at) values ('demo_tier', '\"static\"', now()) on conflict (key) do update set value = excluded.value, updated_at = now()"
curl -fsS https://plumbline-api.alinedlabs.co/api/settings/tier     # {"tier":"static",...}
```

## Uptime monitoring (the human, once; last run: not yet)

UptimeRobot's free plan checks every 5 minutes and emails on failure.

1. Sign up at uptimerobot.com with the email that should get the alerts.
2. **Add New Monitor**: type HTTP(s), name `Plumbline API`, URL
   `https://plumbline-api.alinedlabs.co/api/health`, interval 5 minutes. Under
   **Advanced**, keyword monitoring is optional: the keyword `"status":"ok"`, alert when it
   does not exist.
3. **Add New Monitor**: type HTTP(s), name `Plumbline web`, URL
   `https://plumbline.alinedlabs.co/`, interval 5 minutes.
4. Both monitors alert your email contact by default; check that it is ticked on each.
5. Tell Lane P the two monitor ids in a brain note (not secret), so the runbook can link
   them. If the domain changes, edit both URLs to match `deploy/prod.env`.

A `static` tier from the kill switch still answers `/api/health` with `ok`; the tier is
in the same response (`"tier": "static"`), so a keyword monitor on `"tier":"full"` would
alert on it, if you want an email when the switch acts.
