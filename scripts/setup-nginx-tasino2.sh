#!/bin/sh
# نصب nginx + SSL برای tasino2.spayerx.ir
# اجرا: sh scripts/setup-nginx-tasino2.sh
set -eu

DOMAIN=tasino2.spayerx.ir

cd "$(dirname "$0")/.."

echo "==> نصب nginx و certbot"
apt update
apt install -y nginx certbot python3-certbot-nginx

mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled /var/www/html

# اول فقط HTTP (بدون SSL) تا certbot کار کند
sh scripts/remote-fix-nginx.sh
