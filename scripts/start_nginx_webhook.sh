#!/bin/bash
set -euo pipefail

echo "==> who owns 80/443"
ss -lptn | grep -E ':80|:443' || true
docker ps --format '{{.Names}} {{.Ports}}' | grep -E '80|443' || true

echo "==> try start nginx"
if ! systemctl start nginx; then
  echo "start failed, checking journal"
  journalctl -u nginx -n 40 --no-pager || true
fi

# اگر پورت 80 اشغال است، بلاک HTTP را موقتاً غیرفعال کن و فقط 443 را نگه دار
if ! ss -lptn | grep -q ':443'; then
  echo "==> 443 still down; patch site to avoid port 80 conflict"
  SITE=/etc/nginx/sites-enabled/tasino2.spayerx.ir
  cp -a "$SITE" "/root/tasino2.spayerx.ir.bak.$(date +%s)"
  # سرور listen 80 را کامنت/حذف عملی: فایل جایگزین فقط 443
  cat > /etc/nginx/sites-available/tasino2.spayerx.ir <<'NGX'
upstream tasino2_django { server 127.0.0.1:8001; keepalive 8; }
upstream tasino2_webhook { server 127.0.0.1:8443; keepalive 8; }

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name tasino2.spayerx.ir;

    ssl_certificate /etc/letsencrypt/live/tasino2.spayerx.ir/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/tasino2.spayerx.ir/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    location /webhook {
        proxy_pass http://tasino2_webhook;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_read_timeout 60s;
    }

    location /static/ {
        proxy_pass http://tasino2_django;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://tasino2_django;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
    }
}
NGX
  ln -sfn /etc/nginx/sites-available/tasino2.spayerx.ir /etc/nginx/sites-enabled/tasino2.spayerx.ir
  nginx -t
  systemctl start nginx
fi

systemctl enable nginx || true
systemctl status nginx --no-pager -l | head -20
ss -lptn | grep -E ':443|:80' || true

cd /opt/TasinoTelgramBot
set -a; source ./.env.prod; set +a

# مطمئن شو host درست است
sed -i 's|^WEBHOOK_HOST=.*|WEBHOOK_HOST=https://tasino2.spayerx.ir|' .env.prod
set -a; source ./.env.prod; set +a

curl -sS "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  --data-urlencode "url=https://tasino2.spayerx.ir/webhook" \
  --data-urlencode "secret_token=${WEBHOOK_SECRET}" \
  --data-urlencode "drop_pending_updates=true"
echo

echo "==> probes"
curl -sS -o /dev/null -w "local8443:%{http_code}\n" -X POST http://127.0.0.1:8443/webhook \
  -H "X-Telegram-Bot-Api-Secret-Token: ${WEBHOOK_SECRET}" \
  -H "Content-Type: application/json" -d '{}'

curl -sS -o /dev/null -w "nginx443:%{http_code}\n" --resolve tasino2.spayerx.ir:443:127.0.0.1 \
  -X POST https://tasino2.spayerx.ir/webhook \
  -H "X-Telegram-Bot-Api-Secret-Token: ${WEBHOOK_SECRET}" \
  -H "Content-Type: application/json" -d '{}' || true

curl -sS "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"; echo
echo DONE
