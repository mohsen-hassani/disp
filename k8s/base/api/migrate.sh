# Runs as the `migrate` initContainer of the api Deployment (roadmap.md T5), on every
# api pod start. Idempotent: an up-to-date database is a no-op. Mounted from the
# `migrate-script` ConfigMap that kustomize generates from this file (editing it
# changes the ConfigMap's name hash, which rolls the pod).
set -eu

echo "== alembic: core"
alembic --name=core upgrade head

# Every module that ships migrations/versions owns a branch. Discovered,
# not hardcoded, exactly like `./dev migrate`: a module with migrations
# but no [section] in alembic.ini fails loudly here, which is correct.
for dir in /app/src/disp/modules/*/; do
  [ -d "${dir}migrations/versions" ] || continue
  name="$(basename "$dir")"
  echo "== alembic: ${name}"
  alembic --name="${name}" upgrade head
done

# `procrastinate schema --apply` is not idempotent (fails with "already
# exists" on a second run), so probe first. Exit codes: 0 = tables exist,
# 1 = absent, 2 = could not connect. Only 1 may proceed to apply.
echo "== procrastinate schema"
rc=0
python - <<'PY' || rc=$?
import sys

import psycopg

from disp.core.config import get_settings

try:
    url = get_settings().database_url_sync.replace("+psycopg", "")
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.procrastinate_jobs')")
        sys.exit(0 if cur.fetchone()[0] is not None else 1)
except Exception as exc:
    print(f"cannot check procrastinate schema: {exc!r}", file=sys.stderr)
    sys.exit(2)
PY
case "$rc" in
  0) echo "procrastinate schema already present, skipping" ;;
  1) procrastinate --app=disp.core.scheduler.app schema --apply ;;
  *) echo "aborting: could not determine procrastinate schema state" >&2
     exit "$rc" ;;
esac

echo "== migrations complete"
