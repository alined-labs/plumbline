#!/usr/bin/env bash
# Proves a backup restores (Lane P): loads a dump from deploy/backup.sh into a throwaway
# Postgres container on the production image, then compares the row count of every table
# with the live production database. Touches nothing in production:
#
#   bash deploy/restore-test.sh <file.dump>
#
# Counts may differ for tables written since the dump (queries, feedback); the index
# (documents, chunks) and the schema version must match unless a migration or a re-index
# ran in between. To restore production itself, see docs/runbook.md.
set -Eeuo pipefail
trap 'printf "restore-test: failed at line %d\n" "$LINENO" >&2' ERR

if (($# != 1)) || [[ ! -r $1 ]]; then
  printf 'usage: bash deploy/restore-test.sh <file.dump>\n' >&2
  exit 2
fi
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
prod=${PROD:-$here/prod}  # the compose wrapper; a rehearsal passes its own
dump=$1
image=$(sed -n 's/^ *image: \(paradedb\/paradedb:[^ ]*\)$/\1/p' "$here/compose.prod.yaml")
name=plumbline-restore-test-$$

cleanup() { docker rm -f "$name" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# A random password: the container has no published port and lives for this script.
docker run -d --name "$name" -e POSTGRES_USER=plumbline -e POSTGRES_DB=plumbline \
  -e POSTGRES_PASSWORD="$(openssl rand -hex 16)" "$image" >/dev/null
for _ in $(seq 60); do
  # Over TCP: the image's temporary init server listens on the socket only.
  docker exec "$name" pg_isready -h 127.0.0.1 -U plumbline -d plumbline >/dev/null 2>&1 && break
  sleep 1
done

# Roles are cluster-wide, so a dump does not carry them; the schema's grants need this one.
# The image sets up ParadeDB's own schema in its default database, so the dump goes into
# an empty one built from template0.
docker exec "$name" psql -U plumbline -d plumbline -qc 'CREATE ROLE plumbline_app NOLOGIN' \
  -c 'CREATE DATABASE restored TEMPLATE template0'

started=$(date +%s)
docker exec -i "$name" pg_restore -U plumbline -d restored --no-owner --exit-on-error <"$dump"
printf 'restore-test: restored %s in %d s\n' "$dump" "$(($(date +%s) - started))"

# One line per table, "name count", from the restored copy and from production.
counts() {
  local db=$1
  shift
  "$@" psql -U plumbline -d "$db" -AtF ' ' -c "
    SELECT format('SELECT %L, count(*) FROM %I;', table_name, table_name)
    FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    ORDER BY table_name" | "$@" psql -U plumbline -d "$db" -AtF ' ' 2>/dev/null |
    sed '/^$/d'
}
restored=$(counts restored docker exec -i "$name")
live=$(counts plumbline "$prod" exec -T db)
version=$(docker exec "$name" psql -U plumbline -d restored -Atc 'SELECT version_num FROM alembic_version')

printf '%-24s %10s %10s\n' table restored live
join <(sort <<<"$restored") <(sort <<<"$live") -a1 -e - -o 0,1.2,2.2 |
  awk '{ printf "%-24s %10s %10s%s\n", $1, $2, $3, ($2 == $3 ? "" : "   differs") }'
printf 'restore-test: schema version %s\n' "$version"
