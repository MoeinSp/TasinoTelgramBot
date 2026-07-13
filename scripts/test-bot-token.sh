#!/bin/sh
# تست توکن تلگرام بدون بالا آوردن کل bot
#   sh scripts/test-bot-token.sh
set -eu

cd "$(dirname "$0")/.."

if [ ! -f .env.prod ]; then
  echo "❌ .env.prod پیدا نشد"
  exit 1
fi

# فقط یک خط BOT_TOKEN (آخرین خط اگر تکراری باشد)
token=$(grep -E '^BOT_TOKEN=' .env.prod | tail -1 | cut -d= -f2- | tr -d '\r' | sed 's/^["'\'']//;s/["'\'']$//' | tr -d ' ')
proxy=$(grep -E '^PROXY=' .env.prod | tail -1 | cut -d= -f2- | tr -d '\r' | sed 's/^["'\'']//;s/["'\'']$//' || true)

if [ -z "$token" ] || [ "$token" = "123456:ABCDEF-your-telegram-bot-token" ]; then
  echo "❌ BOT_TOKEN خالی یا placeholder است"
  exit 1
fi

count=$(grep -cE '^BOT_TOKEN=' .env.prod || true)
if [ "$count" -gt 1 ]; then
  echo "⚠️  $count خط BOT_TOKEN در .env.prod — فقط یکی بماند"
fi

echo "==> تست getMe (بدون نمایش توکن کامل)"
id_part="${token%%:*}"
echo "    bot id prefix: ${id_part}"

if [ -n "$proxy" ]; then
  echo "    PROXY=$proxy"
fi

url="https://api.telegram.org/bot${token}/getMe"
if command -v curl >/dev/null 2>&1; then
  if [ -n "$proxy" ]; then
    resp=$(curl -sS --max-time 15 -x "$proxy" "$url" || true)
  else
    resp=$(curl -sS --max-time 15 "$url" || true)
  fi
  echo "$resp"
  echo "$resp" | grep -q '"ok":true' && echo "✅ توکن معتبر است" && exit 0
  echo "❌ توکن نامعتبر یا دسترسی به api.telegram.org نیست"
  exit 1
fi

echo "curl نصب نیست — از داخل کانتینر تست کن:"
echo "  docker-compose exec bot python -c \"import os; from dotenv import load_dotenv; load_dotenv('.env.prod'); import httpx; t=os.getenv('BOT_TOKEN','').strip(); print(httpx.get(f'https://api.telegram.org/bot{t}/getMe', timeout=15).text)\""
