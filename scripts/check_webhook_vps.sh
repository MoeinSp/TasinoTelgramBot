#!/bin/bash
set -euo pipefail
cd /opt/TasinoTelgramBot
set -a; source ./.env.prod; set +a

echo "==> containers"
docker ps -a --filter name=tasino_ --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

echo "==> listen ports"
ss -lptn | grep -E ':443|:80|:8443|:8001' || true

echo "==> nginx status"
systemctl is-active nginx || true
systemctl status nginx --no-pager -l | head -25 || true

echo "==> wait bot ready"
for i in $(seq 1 30); do
  if docker logs tasino_bot 2>&1 | grep -q 'Webhook server'; then
    echo "ready after ${i}s"
    break
  fi
  sleep 2
done

echo "==> recent bot logs"
docker logs --tail 50 tasino_bot 2>&1 | tail -50

echo "==> probe 8443"
curl -sv -o /tmp/wh.out -w "code:%{http_code}\n" --max-time 5 -X POST "http://127.0.0.1:8443/webhook" \
  -H "X-Telegram-Bot-Api-Secret-Token: ${WEBHOOK_SECRET}" \
  -H "Content-Type: application/json" -d '{"update_id":1}' 2>&1 | tail -20
echo "body:"; head -c 200 /tmp/wh.out; echo

echo "==> probe nginx 443"
curl -sv -o /tmp/wh2.out -w "code:%{http_code}\n" --max-time 8 --resolve tasino2.spayerx.ir:443:127.0.0.1 \
  -X POST "https://tasino2.spayerx.ir/webhook" \
  -H "X-Telegram-Bot-Api-Secret-Token: ${WEBHOOK_SECRET}" \
  -H "Content-Type: application/json" -d '{"update_id":1}' 2>&1 | tail -30

echo "==> getWebhookInfo"
curl -sS "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"; echo
