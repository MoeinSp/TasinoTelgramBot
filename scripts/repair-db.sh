#!/bin/sh
# تعمیر DB بعد از restore ناقص — بدون DROP DATABASE
#   sh scripts/repair-db.sh
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

echo "==> repair-db: orphan rows + fake migrations + migrate"
$DC up -d --no-build db redis

$DC run --rm --no-deps --entrypoint sh bot -c '
  set -eu
  i=0
  while [ "$i" -lt 30 ]; do
    if python - <<PY
import os
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
  python manage.py repair_db
'

# sync hash تا migrate-if-needed دوباره اجرا نشود
HASH_FILE=".migrations.hash"
find . -path '*/migrations/*.py' ! -path './.venv/*' 2>/dev/null \
  | LC_ALL=C sort | sha256sum | awk '{print $1}' > "$HASH_FILE"

echo "==> repair-db تمام شد"
