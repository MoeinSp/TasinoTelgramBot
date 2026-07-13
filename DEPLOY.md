# استقرار تاسینو روی tasino.spayerx.ir

## سرعت آپدیت

کد پروژه با **volume** داخل کانتینر است → تغییر پایتون = `restart`، نه بیلد.

```sh
# آپدیت معمولی (چند ثانیه) — بدون بیلد
sh scripts/deploy_spayerx.sh

# فقط وقتی requirements.txt یا Dockerfile عوض شد:
sh scripts/deploy_spayerx.sh --build

# یا دستی بعد از git pull:
docker compose restart bot
```

Image فقط پکیج‌های پایتون را دارد (`tasino-bot:deps`). بیلد سنگین Alpine/`cache_to` حذف شده.

## فایل‌های env

| فایل | نقش |
|------|------|
| `.env.prod` | توکن ربات، وب‌هوک، … |
| `.env` | `DB_PASSWORD` برای compose |

## استارت اول / کامل

```sh
chmod +x scripts/deploy_spayerx.sh docker/entrypoint.sh
sh scripts/deploy_spayerx.sh --build
```

ترتیب: `db/redis healthy` → **`migrate`** → **`bot`**

## nginx (یک‌بار)

```bash
sudo cp docker/nginx-tasino.spayerx.ir.conf /etc/nginx/sites-available/tasino.spayerx.ir
sudo ln -sf /etc/nginx/sites-available/tasino.spayerx.ir /etc/nginx/sites-enabled/
sudo certbot --nginx -d tasino.spayerx.ir
sudo nginx -t && sudo systemctl reload nginx
```

## آدرس‌ها

| سرویس | URL |
|--------|------|
| پنل ادمین | https://tasino.spayerx.ir/admin/ |
| وب‌هوک تلگرام | https://tasino.spayerx.ir/webhook |

- `USE_POLLING=false`
- `WEBHOOK_HOST=https://tasino.spayerx.ir`
- `WEBHOOK_PATH=/webhook`
