#!/usr/bin/env bash
# Nightly Postgres backup for disp, per docs/operations.md.
#
# Usage: ./scripts/backup.sh
#
# Reads DISP_DATABASE_URL_SYNC (or derives it from DISP_DATABASE_URL)
# from the environment or .env. Writes a timestamped custom-format dump to
# BACKUP_DIR, prunes old dumps per the retention policy below, then copies
# the fresh dump off-host if BACKUP_REMOTE is set.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

BACKUP_DIR="${BACKUP_DIR:-/var/backups/disp}"
# Destination for the off-host copy, e.g. "s3://my-bucket/disp-backups/" or
# "user@host:/path/". Leave unset to skip the off-host copy (not recommended
# for production).
BACKUP_REMOTE="${BACKUP_REMOTE:-}"
RETENTION_DAILY=7
RETENTION_WEEKLY=4

database_url_sync="${DISP_DATABASE_URL_SYNC:-}"
if [[ -z "$database_url_sync" ]]; then
    database_url_sync="${DISP_DATABASE_URL:?DISP_DATABASE_URL or DISP_DATABASE_URL_SYNC required}"
    database_url_sync="${database_url_sync/+asyncpg/}"
fi
# pg_dump wants a bare postgresql:// URL, no SQLAlchemy driver marker.
pg_dump_url="${database_url_sync/+psycopg/}"

mkdir -p "$BACKUP_DIR"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
dump_file="$BACKUP_DIR/disp-${timestamp}.dump"

echo "Dumping database to $dump_file"
pg_dump -Fc --dbname="$pg_dump_url" --file="$dump_file"

if [[ -n "$BACKUP_REMOTE" ]]; then
    echo "Copying $dump_file to $BACKUP_REMOTE"
    if [[ "$BACKUP_REMOTE" == s3://* ]]; then
        aws s3 cp "$dump_file" "$BACKUP_REMOTE"
    else
        rsync -az "$dump_file" "$BACKUP_REMOTE"
    fi
fi

# Retention: keep the most recent RETENTION_DAILY dumps unconditionally
# (one per day, since this runs nightly), plus one dump per week for the
# RETENTION_WEEKLY weeks before that (the oldest dump found in each of those
# weekly buckets), and delete everything else.
mapfile -t all_dumps < <(find "$BACKUP_DIR" -maxdepth 1 -name 'disp-*.dump' | sort -r)

keep=()
for ((i = 0; i < RETENTION_DAILY && i < ${#all_dumps[@]}; i++)); do
    keep+=("${all_dumps[i]}")
done

if (( ${#all_dumps[@]} > RETENTION_DAILY )); then
    older=("${all_dumps[@]:RETENTION_DAILY}")
    for ((week = 0; week < RETENTION_WEEKLY; week++)); do
        week_start=$((week * 7))
        week_end=$((week_start + 7))
        if (( week_start >= ${#older[@]} )); then
            break
        fi
        bucket_end=$(( week_end < ${#older[@]} ? week_end : ${#older[@]} ))
        # The oldest dump in this weekly bucket (last index in the slice,
        # since `older` is sorted newest-first).
        keep+=("${older[$((bucket_end - 1))]}")
    done
fi

for dump in "${all_dumps[@]}"; do
    found=0
    for k in "${keep[@]}"; do
        if [[ "$dump" == "$k" ]]; then
            found=1
            break
        fi
    done
    if [[ "$found" -eq 0 ]]; then
        echo "Pruning old backup: $dump"
        rm -f "$dump"
    fi
done

echo "Backup complete: $dump_file"
