#!/usr/bin/env bash
# یک‌بار روی سرور بعد از آپلود پروژه اجرا کن:
#   bash scripts/deploy_spayerx.sh
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .env.prod ]]; then
  echo "❌ فایل .env.prod پیدا نشد"
  exit 1
fi
if [[ ! -f .env ]]; then
  echo "❌ فایل .env پیدا نشد (برای DB_PASSWORD در compose)"
  exit 1
fi

echo "==> build + up (migrate قبل از bot)"
docker compose up -d --build

echo "==> وضعیت سرویس‌ها"
docker compose ps

echo ""
echo "==> nginx روی هاست (اگر هنوز ست نشده):"
echo "  sudo cp docker/nginx-tasino.spayerx.ir.conf /etc/nginx/sites-available/tasino.spayerx.ir"
echo "  sudo ln -sf /etc/nginx/sites-available/tasino.spayerx.ir /etc/nginx/sites-enabled/"
echo "  sudo nginx -t && sudo systemctl reload nginx"
echo ""
echo "ادمین:   https://tasino.spayerx.ir/admin/"
echo "وب‌هوک:  https://tasino.spayerx.ir/webhook"
echo ""
echo "لاگ ربات: docker compose logs -f bot"
