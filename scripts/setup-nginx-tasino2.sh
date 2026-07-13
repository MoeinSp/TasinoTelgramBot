#!/bin/sh
# نصب nginx + SSL برای tasino2.spayerx.ir
# اجرا: sh scripts/setup-nginx-tasino2.sh
set -eu

DOMAIN=tasino2.spayerx.ir
CONF_SRC="docker/nginx-tasino2.spayerx.ir.conf"
CONF_DST="/etc/nginx/sites-available/${DOMAIN}"

cd "$(dirname "$0")/.."

if [ ! -f "$CONF_SRC" ]; then
  echo "❌ $CONF_SRC پیدا نشد — اول git pull کن"
  exit 1
fi

echo "==> نصب nginx و certbot"
apt update
apt install -y nginx certbot python3-certbot-nginx

mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled /var/www/html

echo "==> کپی کانفیگ"
cp "$CONF_SRC" "$CONF_DST"
ln -sf "$CONF_DST" "/etc/nginx/sites-enabled/${DOMAIN}"

# حذف default اگر تداخل دارد (اختیاری)
if [ -f /etc/nginx/sites-enabled/default ]; then
  rm -f /etc/nginx/sites-enabled/default
fi

echo "==> تست اولیه (قبل SSL ممکن است خطای cert بدهد — طبیعی است)"
nginx -t || true

echo "==> SSL"
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m admin@${DOMAIN} || certbot --nginx -d "$DOMAIN"

nginx -t
systemctl enable nginx
systemctl reload nginx

echo ""
echo "✅ nginx آماده برای $DOMAIN"
echo "تست:"
echo "  curl -sI https://${DOMAIN}/webhook"
echo "  curl -sI http://127.0.0.1:8443/webhook"
