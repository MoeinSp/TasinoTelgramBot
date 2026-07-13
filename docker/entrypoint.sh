#!/bin/sh
set -e

wait_for_db() {
  echo "==> waiting for database..."
  i=0
  while [ "$i" -lt 30 ]; do
    if python - <<'PY'
import os, sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "TasinoAiogram3.settings")
import django
django.setup()
from django.db import connection
try:
    connection.ensure_connection()
except Exception:
    sys.exit(1)
sys.exit(0)
PY
    then
      echo "==> database is ready"
      return 0
    fi
    i=$((i + 1))
    sleep 1
  done
  echo "==> database not ready after 30s" >&2
  exit 1
}

run_migrate() {
  echo "==> migrate"
  n=0
  while [ "$n" -lt 5 ]; do
    if python manage.py migrate --no-input; then
      return 0
    fi
    n=$((n + 1))
    echo "==> migrate failed (try $n/5), retry in 3s..."
    sleep 3
  done
  echo "==> migrate failed permanently" >&2
  exit 1
}

if [ "${1:-}" = "migrate-only" ]; then
  wait_for_db
  run_migrate
  echo "==> migrate-only done"
  exit 0
fi

wait_for_db

if [ "${SKIP_MIGRATE:-0}" != "1" ]; then
  run_migrate
fi

if [ "${SKIP_COLLECTSTATIC:-0}" != "1" ]; then
  echo "==> collectstatic"
  python manage.py collectstatic --no-input
fi

echo "==> admin (gunicorn) on :8000"
python -m gunicorn TasinoAiogram3.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 1 \
  --threads 2 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile - &

echo "==> bot start"
exec python -m bot.main
