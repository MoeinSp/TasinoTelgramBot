#!/bin/sh
# ساخت سوپریوزر بدون prompt (برای VPS)
#   sh scripts/create-superuser.sh رمز_قوی
#   sh scripts/create-superuser.sh رمز_قوی myadmin
set -eu

cd "$(dirname "$0")/.."

PASS="${1:-}"
USER="${2:-admin}"

if [ -z "$PASS" ]; then
  echo "استفاده: sh scripts/create-superuser.sh PASSWORD [username]"
  exit 1
fi

if command -v docker-compose >/dev/null 2>&1; then
  DC=docker-compose
else
  DC="/usr/local/bin/docker-compose"
fi

echo "==> ساخت سوپریوزر: $USER"
$DC run --rm --no-deps \
  --entrypoint python \
  -e DJANGO_SUPERUSER_USERNAME="$USER" \
  -e DJANGO_SUPERUSER_PASSWORD="$PASS" \
  -e DJANGO_SUPERUSER_EMAIL="${USER}@tasino.local" \
  bot manage.py ensure_superuser

echo ""
echo "ورود: https://tasino2.spayerx.ir/admin/"
echo "نام کاربری: $USER"
