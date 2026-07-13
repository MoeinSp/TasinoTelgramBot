#!/bin/sh
# migrate فقط وقتی فایل migration عوض شده (یا --force)
#   sh scripts/migrate-if-needed.sh
#   sh scripts/migrate-if-needed.sh --force
set -eu

cd "$(dirname "$0")/.."

if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "❌ docker compose پیدا نشد"
  exit 1
fi

HASH_FILE=".migrations.hash"
cur=$(find . -path '*/migrations/*.py' ! -path './.venv/*' 2>/dev/null | LC_ALL=C sort | sha256sum | awk '{print $1}')
old=$(cat "$HASH_FILE" 2>/dev/null || true)

if [ "$cur" = "$old" ] && [ "${1:-}" != "--force" ]; then
  echo "==> migrate لازم نیست (فایل migration عوض نشده)"
  exit 0
fi

echo "==> migrate..."
$DC up -d --no-build db redis

$DC run --rm --no-deps --entrypoint sh bot -c '
  set -eu
  i=0
  while [ "$i" -lt 30 ]; do
    if python - <<PY
import os, sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "TasinoAiogram3.settings")
import django
django.setup()
from django.db import connection
connection.ensure_connection()
PY
    then break
    fi
    i=$((i + 1))
    sleep 1
  done
  python manage.py migrate --no-input
'

echo "$cur" > "$HASH_FILE"
echo "==> migrate انجام شد"
