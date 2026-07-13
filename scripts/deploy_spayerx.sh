#!/bin/sh
# آپدیت سریع:
#   sh scripts/deploy_spayerx.sh           → restart، بدون migrate
#   sh scripts/deploy_spayerx.sh --build   → rebuild image
#   sh scripts/deploy_spayerx.sh --migrate → migrate اجباری
set -eu

cd "$(dirname "$0")/.."

chmod +x docker/entrypoint.sh scripts/migrate-if-needed.sh 2>/dev/null || true

if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "❌ docker compose پیدا نشد"
  exit 1
fi

if [ ! -f .env.prod ]; then
  echo "❌ فایل .env.prod پیدا نشد"
  exit 1
fi
if [ ! -f .env ]; then
  echo "❌ فایل .env پیدا نشد (برای DB_PASSWORD در compose)"
  exit 1
fi

need_build=0
force_migrate=0
for arg in "$@"; do
  case "$arg" in
    --build) need_build=1 ;;
    --migrate) force_migrate=1 ;;
  esac
done

HASH_FILE=".deps-image.hash"
if [ "$need_build" -eq 1 ]; then
  :
elif [ ! -f "$HASH_FILE" ]; then
  need_build=1
else
  cur=$(cat Dockerfile requirements.txt | sha256sum | awk '{print $1}')
  old=$(cat "$HASH_FILE" 2>/dev/null || true)
  if [ "$cur" != "$old" ]; then
    echo "==> Dockerfile/requirements عوض شده → بیلد لازم است"
    need_build=1
  fi
fi

$DC up -d --no-build db redis

if [ "$need_build" -eq 1 ]; then
  echo "==> build image وابستگی‌ها"
  $DC build bot
  cat Dockerfile requirements.txt | sha256sum | awk '{print $1}' > "$HASH_FILE"
else
  echo "==> بدون بیلد"
fi

if [ "$force_migrate" -eq 1 ]; then
  sh scripts/migrate-if-needed.sh --force
else
  sh scripts/migrate-if-needed.sh
fi

echo "==> bot"
$DC up -d --no-build bot

echo "==> وضعیت"
$DC ps

echo ""
echo "ری‌استارت سریع بعدی: docker-compose restart bot"
echo "migrate اجباری: sh scripts/deploy_spayerx.sh --migrate"
