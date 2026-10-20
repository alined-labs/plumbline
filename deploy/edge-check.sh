#!/usr/bin/env bash
# Checks the public edge from outside (Lane P), against the hostnames in deploy/prod.env:
#
#   bash deploy/edge-check.sh
#
# The web app answers over HTTPS with its security headers; the API answers through
# Cloudflare (a cf-ray header) with /api/health ok; CORS admits the web origin and no
# other; and the rate limit (deploy/cloudflare/rate-limit.md) blocks a burst on /api/ask.
# The burst sends invalid questions, which the API refuses with 422 before any model call
# and does not count against the quota, so the check costs nothing.
set -Eeuo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=/dev/null # deploy/prod.env, plain assignments
source "$here/prod.env"
web=https://$WEB_HOST api=https://$API_HOST

fails=0
ok() { printf 'ok    %s\n' "$*"; }
fail() { printf 'FAIL  %s\n' "$*"; fails=$((fails + 1)); }
# headers <url> [curl args]: the response's headers, lower-cased.
headers() { curl -sS -o /dev/null -D - --max-time 10 "$@" | tr -d '\r' | tr '[:upper:]' '[:lower:]'; }

page=$(headers "$web/")
if grep -q '^http/[0-9.]* 200' <<<"$page"; then ok "$web/ answers 200"; else fail "$web/ does not answer 200"; fi
for header in content-security-policy strict-transport-security x-content-type-options referrer-policy; do
  if grep -q "^$header:" <<<"$page"; then ok "the web app sends $header"; else fail "the web app sends no $header"; fi
done

health=$(curl -sS --max-time 10 -D "${TMPDIR:-/tmp}/edge-check.$$" "$api/api/health" || true)
if grep -q '"status":"ok"' <<<"$health"; then ok "$api/api/health is ok: $health"; else fail "$api/api/health: $health"; fi
if grep -qi '^cf-ray:' "${TMPDIR:-/tmp}/edge-check.$$"; then ok "the API answers through Cloudflare"; else fail "the API answer has no cf-ray header"; fi
rm -f "${TMPDIR:-/tmp}/edge-check.$$"

cors() { headers "$api/api/ask" -X OPTIONS -H "Origin: $1" -H 'Access-Control-Request-Method: POST' |
  sed -n 's/^access-control-allow-origin: //p'; }
if [[ $(cors "$web") == "$web" ]]; then ok "CORS admits $web"; else fail "CORS does not admit $web"; fi
if [[ -z $(cors https://example.com) ]]; then ok "CORS admits no other origin"; else fail "CORS admits https://example.com"; fi

codes=()
for _ in $(seq 12); do
  codes+=("$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 -X POST "$api/api/ask" \
    -H 'Content-Type: application/json' -d '{}')")
done
if [[ " ${codes[*]} " == *" 429 "* ]]; then
  ok "a burst on /api/ask is rate limited (${codes[*]})"
else
  fail "12 requests in a burst on /api/ask were not rate limited (${codes[*]})"
fi

printf 'edge-check: %d failure(s)\n' "$fails"
((fails == 0))
