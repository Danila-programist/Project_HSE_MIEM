#!/usr/bin/env bash
set -e

echo "[entrypoint] DATABASE_URL=$DATABASE_URL"
getent hosts db || echo "[entrypoint] DNS: db не резолвится"

python - <<'PY'
import os, sys, time
import psycopg
url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
print(f"[entrypoint] psycopg URL = {url}", flush=True)
last = None
for i in range(30):
    try:
        psycopg.connect(url, connect_timeout=2).close()
        print("[entrypoint] Postgres reachable", flush=True)
        sys.exit(0)
    except Exception as e:
        last = e
        print(f"[entrypoint] try {i+1}: {e!r}", flush=True)
        time.sleep(1)
print(f"[entrypoint] FATAL: {last!r}", file=sys.stderr, flush=True)
sys.exit(1)
PY

alembic upgrade head
python -m app.seed

exec uvicorn app.main:app --host 0.0.0.0 --port 8000