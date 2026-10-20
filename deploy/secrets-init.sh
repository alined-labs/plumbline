#!/usr/bin/env bash
# Creates the production stack's secret files in /etc/plumbline (Lane P). The human runs it
# as root; nothing else ever writes or reads these files, and it prints no value:
#
#   sudo bash deploy/secrets-init.sh                        # db_password and api.env
#   sudo bash deploy/secrets-init.sh --tunnel <file.json>   # also the tunnel's credentials
#   sudo -e /etc/plumbline/api.env                          # then paste in the provider keys
#
# It never overwrites a file that exists, so running it again is safe; to rotate one,
# delete it first (docs/security.md, the secrets inventory). Each file is owned by root
# and readable by the group of the one container user that needs it, a group no login on
# this machine belongs to:
#
#   db_password   root:999    (Postgres, POSTGRES_PASSWORD_FILE)
#   api.env       root:10001  (the API image's user; the settings read it as /app/.env)
#   tunnel.json   root:65532  (cloudflared's nonroot user)
set -Eeuo pipefail
umask 077
readonly DIR=/etc/plumbline

if ((EUID != 0)); then
  printf 'secrets-init: run it as root (sudo bash %s)\n' "$0" >&2
  exit 2
fi
tunnel=
if [[ ${1-} == --tunnel && -n ${2-} ]]; then
  tunnel=$2
elif (($#)); then
  printf 'usage: sudo bash %s [--tunnel <credentials.json>]\n' "$0" >&2
  exit 2
fi

install -d -o root -g root -m 0755 "$DIR"

# place <name> <gid>: moves the new file from stdin into place, root:<gid> 0640.
place() {
  local target=$DIR/$1 tmp
  tmp=$(mktemp "$DIR/.$1.XXXXXX")
  cat >"$tmp"
  chown "root:$2" "$tmp"
  chmod 0640 "$tmp"
  mv "$tmp" "$target"
  printf 'secrets-init: wrote %s (root:%s, 0640)\n' "$target" "$2"
}

if [[ -e $DIR/db_password ]]; then
  printf 'secrets-init: %s exists, kept\n' "$DIR/db_password"
else
  # Hex, so it needs no escaping inside the database URL.
  openssl rand -hex 32 | tr -d '\n' | place db_password 999
fi

if [[ -e $DIR/api.env ]]; then
  printf 'secrets-init: %s exists, kept\n' "$DIR/api.env"
else
  {
    printf '# The production API'"'"'s secrets (deploy/secrets-init.sh). Edit with: sudo -e %s\n' "$DIR/api.env"
    printf 'DATABASE_URL=%s://plumbline:%s@db:5432/plumbline\n' postgresql+psycopg "$(cat "$DIR/db_password")"
    printf 'ADMIN_TOKEN=%s\n' "$(openssl rand -hex 32)"
    # Commented out, not empty: an empty value would read as a key that is set.
    printf '# Remove the "# " and paste each key after its = sign; a provider left commented stays off.\n'
    printf '# GEMINI_API_KEY=\n# ANTHROPIC_API_KEY=\n# LANGFUSE_PUBLIC_KEY=\n# LANGFUSE_SECRET_KEY=\n'
  } | place api.env 10001
fi

if [[ -n $tunnel ]]; then
  if [[ -e $DIR/tunnel.json ]]; then
    printf 'secrets-init: %s exists, kept\n' "$DIR/tunnel.json"
  else
    place tunnel.json 65532 <"$tunnel"
    printf 'secrets-init: you may now delete %s\n' "$tunnel"
  fi
fi
