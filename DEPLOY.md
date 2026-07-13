# استقرار تاسینو روی tasino.spayerx.ir

## فایل‌های env (لوکال آماده شده‌اند)

| فایل | نقش |
|------|------|
| `.env.prod` | توکن ربات، وب‌هوک، دیتابیس (داخل کانتینر) |
| `.env` | `DB_PASSWORD` برای متغیرهای compose |

هر دو در `.gitignore` هستند و داخل image کپی نمی‌شوند.

## آپدیت / استارت روی سرور

```bash
# پروژه را بکش / آپلود کن (با .env و .env.prod)
chmod +x scripts/deploy_spayerx.sh
bash scripts/deploy_spayerx.sh

# یا مستقیم:
docker compose up -d --build
```

ترتیب: `db/redis healthy` → **`migrate` کامل** → **`bot`**

## nginx (یک‌بار)

```bash
sudo cp docker/nginx-tasino.spayerx.ir.conf /etc/nginx/sites-available/tasino.spayerx.ir
sudo ln -sf /etc/nginx/sites-available/tasino.spayerx.ir /etc/nginx/sites-enabled/
sudo certbot --nginx -d tasino.spayerx.ir   # اگر SSL نداری
sudo nginx -t && sudo systemctl reload nginx
```

## آدرس‌ها

| سرویس | URL |
|--------|------|
| پنل ادمین | https://tasino.spayerx.ir/admin/ |
| وب‌هوک تلگرام | https://tasino.spayerx.ir/webhook |

تنظیمات وب‌هوک در `.env.prod`:
- `USE_POLLING=false`
- `WEBHOOK_HOST=https://tasino.spayerx.ir`
- `WEBHOOK_PATH=/webhook`
