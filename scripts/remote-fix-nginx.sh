#!/bin/sh
set -eu

cat > /etc/nginx/sites-available/tasino2.spayerx.ir <<'EOF'
upstream tasino2_django { server 127.0.0.1:8001; keepalive 8; }
upstream tasino2_webhook { server 127.0.0.1:8443; keepalive 8; }

server {
    listen 80;
    listen [::]:80;
    server_name tasino2.spayerx.ir;

    location /.well-known/acme-challenge/ { root /var/www/html; }

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
EOF

ln -sf /etc/nginx/sites-available/tasino2.spayerx.ir /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

certbot --nginx -d tasino2.spayerx.ir --non-interactive --agree-tos --register-unsafely-without-email --redirect
nginx -t
systemctl reload nginx

cd /opt/TasinoTelgramBot
if command -v docker-compose >/dev/null 2>&1; then DC=docker-compose; else DC="/usr/local/bin/docker-compose"; fi
$DC restart bot
sleep 3

echo '---HTTPS---'
curl -sI https://tasino2.spayerx.ir/webhook | head -8
echo '---LOCAL---'
curl -sI http://127.0.0.1:8443/webhook | head -8
echo '---PS---'
$DC ps
echo '---LOG---'
$DC logs --tail=12 bot
