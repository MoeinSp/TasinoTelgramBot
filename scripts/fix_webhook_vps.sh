#!/bin/bash
set -euo pipefail
cd /opt/TasinoTelgramBot

# nginx فقط tasino2 را به 8443 می‌دهد
sed -i 's|^WEBHOOK_HOST=.*|WEBHOOK_HOST=https://tasino2.spayerx.ir|' .env.prod
# اگر خط نبود اضافه کن
grep -q '^WEBHOOK_HOST=' .env.prod || echo 'WEBHOOK_HOST=https://tasino2.spayerx.ir' >> .env.prod

echo "==> env"
grep -E '^(WEBHOOK_HOST|USE_POLLING|WEBHOOK_PATH|WEBHOOK_PORT)=' .env.prod

set -a
# shellcheck disable=SC1091
source ./.env.prod
set +a

echo "==> restart bot"
docker compose up -d bot
sleep 8

echo "==> setWebhook"
curl -sS "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  --data-urlencode "url=${WEBHOOK_HOST}${WEBHOOK_PATH}" \
  --data-urlencode "secret_token=${WEBHOOK_SECRET}" \
  --data-urlencode "drop_pending_updates=true"
echo

echo "==> getWebhookInfo"
curl -sS "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"
echo

echo "==> local probe"
curl -sS -o /dev/null -w "local:%{http_code}\n" -X POST "http://127.0.0.1:8443${WEBHOOK_PATH}" \
  -H "X-Telegram-Bot-Api-Secret-Token: ${WEBHOOK_SECRET}" \
  -H "Content-Type: application/json" -d '{}' || true

echo "==> nginx local resolve probe"
curl -sS -o /dev/null -w "nginx:%{http_code}\n" --resolve tasino2.spayerx.ir:443:127.0.0.1 \
  -X POST "https://tasino2.spayerx.ir${WEBHOOK_PATH}" \
  -H "X-Telegram-Bot-Api-Secret-Token: ${WEBHOOK_SECRET}" \
  -H "Content-Type: application/json" -d '{}' || true

echo "==> bot logs"
docker logs --tail 40 tasino_bot 2>&1 | grep -E 'Webhook|بات آماده|ERROR|Error|https://|Traceback' | tail -25 || true

echo "==> nginx -t"
nginx -t 2>&1 || true
cat /etc/nginx/sites-enabled/tasino2.spayerx.ir
