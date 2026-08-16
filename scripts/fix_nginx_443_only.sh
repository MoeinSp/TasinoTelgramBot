#!/bin/bash
set -euo pipefail

echo "==> sites-enabled"
ls -la /etc/nginx/sites-enabled/

echo "==> all listen directives"
grep -RHn "listen " /etc/nginx/sites-enabled/ /etc/nginx/nginx.conf /etc/nginx/conf.d/ 2>/dev/null || true

# موقتاً سایت‌هایی که فقط/هم روی 80 هستند را از enabled بردار، بکاپ لینک‌ها
mkdir -p /root/nginx-sites-backup
for f in /etc/nginx/sites-enabled/*; do
  base=$(basename "$f")
  if [ "$base" = "tasino2.spayerx.ir" ]; then
    continue
  fi
  echo "disable $base"
  cp -a "$f" "/root/nginx-sites-backup/$base"
  rm -f "$f"
done

# مطمئن شو tasino2 فقط 443 دارد
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

# اگر default در conf.d روی 80 است
if grep -R "listen .*80" /etc/nginx/conf.d 2>/dev/null; then
  echo "WARN conf.d still has 80"
fi

nginx -t
systemctl start nginx
systemctl enable nginx
systemctl status nginx --no-pager | head -15
ss -lptn | grep ':443' || true

cd /opt/TasinoTelgramBot
set -a; source ./.env.prod; set +a
sed -i 's|^WEBHOOK_HOST=.*|WEBHOOK_HOST=https://tasino2.spayerx.ir|' .env.prod
set -a; source ./.env.prod; set +a

curl -sS "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  --data-urlencode "url=https://tasino2.spayerx.ir/webhook" \
  --data-urlencode "secret_token=${WEBHOOK_SECRET}" \
  --data-urlencode "drop_pending_updates=true"; echo

curl -sS -o /dev/null -w "nginx443:%{http_code}\n" --resolve tasino2.spayerx.ir:443:127.0.0.1 \
  -X POST https://tasino2.spayerx.ir/webhook \
  -H "X-Telegram-Bot-Api-Secret-Token: ${WEBHOOK_SECRET}" \
  -H "Content-Type: application/json" -d '{}'

curl -sS "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"; echo
echo "enabled now:"; ls /etc/nginx/sites-enabled/
echo "backed up:"; ls /root/nginx-sites-backup/
