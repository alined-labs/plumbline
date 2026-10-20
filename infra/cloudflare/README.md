# Cloudflare, as code (Lane P, P7b)

What Plumbline holds at Cloudflare, in Terraform: the API's hostname on the tunnel, the
Pages project and its custom domain with its DNS record, and the edge's rate limit
(`deploy/cloudflare/rate-limit.md` explains the rule). The hosts and the tunnel id come
from `deploy/prod.env`, the one place the domain is set.

Not here, on purpose: **the tunnel itself**. A locally managed tunnel's secret would sit
in the Terraform state in plain text, so the tunnel is made once with
`cloudflared tunnel create` and referenced by `TUNNEL_ID`. Its credentials stay in
`/etc/plumbline/tunnel.json` (`docs/runbook.md`, "Secrets").

## Running it

`infra/cloudflare/tf` runs Terraform 1.16.6 from its pinned image (no install on MX3),
with the state in `~/.local/state/plumbline/cloudflare` (mode 0700, never in the
repository). It needs, in the environment only:

| Variable | What | Secret |
| --- | --- | --- |
| `CLOUDFLARE_API_TOKEN` | a token with Zone: DNS Edit, Zone: Zone WAF Edit, Account: Cloudflare Pages Edit | yes |
| `CLOUDFLARE_ACCOUNT_ID` | the account, from the dashboard's overview | no |
| `CLOUDFLARE_ZONE_ID` | the zone of `alinedlabs.co`, from the same page | no |

```sh
read -rs CLOUDFLARE_API_TOKEN && export CLOUDFLARE_API_TOKEN   # typed, never echoed or saved
export CLOUDFLARE_ACCOUNT_ID=... CLOUDFLARE_ZONE_ID=...
infra/cloudflare/tf init
infra/cloudflare/tf plan
```

## Adopting what Wednesday made by hand (once, on Friday)

Wednesday's steps create every resource here through the dashboard and `cloudflared`, so
Friday imports them instead of creating twins. The ids, read with the same token:

```sh
api=https://api.cloudflare.com/client/v4
get() { curl -fsS -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" "$api$1"; }
source deploy/prod.env
get "/zones/$CLOUDFLARE_ZONE_ID/dns_records?name=$API_HOST" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"][0]["id"])'
get "/zones/$CLOUDFLARE_ZONE_ID/dns_records?name=$WEB_HOST" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"][0]["id"])'
get "/zones/$CLOUDFLARE_ZONE_ID/rulesets/phases/http_ratelimit/entrypoint" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["id"])'
```

```sh
infra/cloudflare/tf import cloudflare_dns_record.api "$CLOUDFLARE_ZONE_ID/<api record id>"
infra/cloudflare/tf import cloudflare_dns_record.web "$CLOUDFLARE_ZONE_ID/<web record id>"
infra/cloudflare/tf import cloudflare_pages_project.web "$CLOUDFLARE_ACCOUNT_ID/plumbline"
infra/cloudflare/tf import cloudflare_pages_domain.web "$CLOUDFLARE_ACCOUNT_ID/plumbline/$WEB_HOST"
infra/cloudflare/tf import cloudflare_ruleset.rate_limit "zones/$CLOUDFLARE_ZONE_ID/<ruleset id>"
infra/cloudflare/tf plan    # expect no change, or only comments and descriptions
```

A plan that wants to replace a record or the project means the dashboard differs from
this file: read the diff, fix whichever is wrong, and never apply a replacement of the
API record during the demo (it drops the API until DNS settles).

## If the domain changes

Edit `WEB_HOST` and `API_HOST` in `deploy/prod.env`, then `infra/cloudflare/tf plan`
and `apply`: both records and the Pages domain follow, and `deploy.yml` builds the site
for the new API host on its next run. The tunnel keeps its id.
