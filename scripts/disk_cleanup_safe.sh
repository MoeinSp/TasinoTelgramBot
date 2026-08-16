#!/bin/bash
set -euo pipefail

echo "========== BEFORE =========="
df -h /
df -i / | tail -1
echo
docker system df
echo

echo "========== Safe cleanup (no running containers/images) =========="

# لاگ‌های خیلی بزرگ کانتینرها (فقط truncate، کانتینر نمی‌میرد)
echo "==> truncate huge docker json logs (>100M)"
find /var/lib/docker/containers -name '*-json.log' -size +100M -print -exec truncate -s 0 {} \; 2>/dev/null || true

# کش بیلد
echo "==> docker builder prune"
docker builder prune -af || true

# کانتینرهای متوقف‌شده
echo "==> docker container prune (stopped only)"
docker container prune -f || true

# ایمیج‌های بدون استفاده (به هیچ کانتینری وصل نیستند؛ running دست نمی‌خورد)
echo "==> docker image prune unused"
docker image prune -af || true

# شبکه بلااستفاده
echo "==> docker network prune"
docker network prune -f || true

# volumeهای dangling (بدون نام، یتیم) — volumeهای نام‌دار دیتا را پاک نمی‌کند
echo "==> docker volume prune dangling only"
docker volume prune -f || true

# journal
echo "==> journal vacuum 200M"
journalctl --vacuum-size=200M || true

# apt cache
echo "==> apt clean"
apt-get clean || true
rm -rf /var/cache/apt/archives/* 2>/dev/null || true

# /tmp قدیمی‌تر از ۷ روز
echo "==> /tmp older than 7 days"
find /tmp -type f -mtime +7 -delete 2>/dev/null || true

# لاگ‌های سیستم خیلی بزرگ
echo "==> truncate huge /var/log files (>200M)"
find /var/log -type f -size +200M -print -exec truncate -s 0 {} \; 2>/dev/null || true

echo
echo "========== AFTER =========="
df -h /
echo
docker system df
echo
echo "Running containers still up:"
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' | head -40
echo DONE
