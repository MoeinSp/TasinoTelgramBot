#!/bin/sh
# آپدیت سریع روی سرور (سازگار با sh — بدون bash):
#   sh scripts/deploy_spayerx.sh          → بدون بیلد (چند ثانیه)
#   sh scripts/deploy_spayerx.sh --build  → فقط وقتی requirements/Dockerfile عوض شده
set -eu

cd "$(dirname "$0")/.."

chmod +x docker/entrypoint.sh 2>/dev/null || true

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

# db/redis بالا باشند
docker compose up -d --no-build db redis

if [ "$need_build" -eq 1 ]; then
  echo "==> build image وابستگی‌ها (یک‌بار)"
  docker compose build bot
  cat Dockerfile requirements.txt | sha256sum | awk '{print $1}' > "$HASH_FILE"
else
  echo "==> بدون بیلد (کد از volume است)"
fi

echo "==> migrate"
docker compose run --rm --no-deps migrate

echo "==> bot"
docker compose up -d --no-build --force-recreate bot

echo "==> وضعیت سرویس‌ها"
docker compose ps

echo ""
echo "ادمین:   https://tasino.spayerx.ir/admin/"
echo "وب‌هوک:  https://tasino.spayerx.ir/webhook"
echo "لاگ:     docker compose logs -f bot"
echo ""
echo "تغییر کد بعدی فقط:"
echo "  docker compose restart bot"
echo "بیلد اجباری:"
echo "  sh scripts/deploy_spayerx.sh --build"
