#!/bin/sh
# نصب Docker Compose v2 روی اوبونتو وقتی docker-compose-plugin در apt نیست
# اجرا: sh scripts/install-compose-v2.sh
set -eu

ARCH=$(uname -m)
case "$ARCH" in
  x86_64|amd64) SUFFIX="x86_64" ;;
  aarch64|arm64) SUFFIX="aarch64" ;;
  *)
    echo "❌ معماری پشتیبانی نشده: $ARCH"
    exit 1
    ;;
esac

VER="${COMPOSE_VERSION:-v2.32.4}"
URL="https://github.com/docker/compose/releases/download/${VER}/docker-compose-linux-${SUFFIX}"
DEST="/usr/local/bin/docker-compose"

echo "==> دانلود Compose $VER ($SUFFIX)"
curl -fsSL "$URL" -o "$DEST"
chmod +x "$DEST"

# پلاگین docker compose (اختیاری)
mkdir -p /usr/local/lib/docker/cli-plugins
ln -sf "$DEST" /usr/local/lib/docker/cli-plugins/docker-compose

echo "==> نسخه جدید:"
"$DEST" version

if command -v docker >/dev/null 2>&1; then
  echo "==> docker compose:"
  docker compose version 2>/dev/null || echo "(فقط docker-compose در PATH)"
fi

echo ""
echo "✅ آماده. از این به بعد:"
echo "   docker-compose up -d"
echo "   یا: docker compose up -d"
