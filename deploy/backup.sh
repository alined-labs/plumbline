#!/usr/bin/env bash
# The nightly backup of the production database (Lane P): a custom-format pg_dump of the
# whole database, written atomically, checked by reading its table of contents, and kept
# for KEEP_DAYS days. deploy/systemd/plumbline-backup.timer runs it at 03:30 UTC:
#
#   bash deploy/backup.sh [<directory>]     # default: $BACKUP_DIR or ~/plumbline-backups
#
# The dump holds the visitors' queries and feedback as well as the index, so the directory
# is created private (0700) and each file is 0600. Restore one with deploy/restore-test.sh,
# which proves it into a throwaway database first.
set -Eeuo pipefail
trap 'printf "backup: failed at line %d\n" "$LINENO" >&2' ERR
umask 077

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
prod=${PROD:-$here/prod}  # the compose wrapper; a rehearsal passes its own
dir=${1:-${BACKUP_DIR:-$HOME/plumbline-backups}}
readonly KEEP_DAYS=${KEEP_DAYS:-14}

mkdir -p "$dir"
chmod 0700 "$dir"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
target=$dir/plumbline-$stamp.dump
partial=$target.partial

"$prod" exec -T db pg_dump -U plumbline -d plumbline --format=custom --compress=6 >"$partial"
# A dump that pg_restore cannot list is not a backup: keep the last good ones instead.
entries=$("$prod" exec -T db pg_restore --list <"$partial" | grep -c ' TABLE DATA ') || true
if ((entries == 0)); then
  rm -f "$partial"
  printf 'backup: the dump lists no table data; nothing kept\n' >&2
  exit 1
fi
mv "$partial" "$target"
printf 'backup: %s, %s bytes, %d tables with data\n' "$target" "$(stat -c %s "$target")" "$entries"

find "$dir" -maxdepth 1 -name 'plumbline-*.dump' -mtime "+$KEEP_DAYS" -print -delete |
  sed 's/^/backup: removed /'
