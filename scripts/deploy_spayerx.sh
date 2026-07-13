#!/bin/sh
# آپدیت سریع روی سرور (سازگار با sh):
#   sh scripts/deploy_spayerx.sh
#   sh scripts/deploy_spayerx.sh --build
set -eu

cd "$(dirname "$0")/.."

chmod +x docker/entrypoint.sh 2>/dev/null || true

# docker compose v2 ترجیح داده می‌شود (v1.29 با Docker جدید خطای ContainerConfig می‌دهد)
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
  echo "⚠️  docker-compose v1 — اگر خطای ContainerConfig دیدی، compose v2 نصب کن"
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

HASH_FILE=".deps-image.hash"
need_build=0
if [ "${1:-}" = "--build" ]; then
  need_build=1
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
  echo "==> بدون بیلد (کد از volume است)"
fi

# جلوگیری از باگ recreate در docker-compose v1
docker rm -f tasino_migrate 2>/dev/null || true

echo "==> migrate"
$DC run --rm --no-deps migrate

echo "==> bot"
docker rm -f tasino_bot 2>/dev/null || true
$DC up -d --no-build --force-recreate bot

echo "==> وضعیت"
$DC ps

echo ""
echo "لاگ: $DC logs -f bot"
