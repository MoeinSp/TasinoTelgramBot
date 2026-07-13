# استقرار تاسینو روی tasino.spayerx.ir

## پیش‌نیاز VPS — Docker Compose v2

`docker-compose` 1.29 با Docker جدید خطای **`ContainerConfig`** می‌دهد.

اگر `apt install docker-compose-plugin` جواب نداد:

```sh
cd /opt/TasinoTelgramBot
sh scripts/install-compose-v2.sh
docker-compose version   # باید v2.x باشد
```

### اگر فعلاً نمی‌خواهی نصب کنی — دور زدن موقت (v1)

```sh
cd /opt/TasinoTelgramBot
docker-compose down --remove-orphans
docker rm -f tasino_migrate tasino_bot 2>/dev/null || true

docker-compose up -d db redis
docker-compose run --rm --no-deps migrate
docker-compose up -d --no-recreate bot
```

**هرگز** با v1 قدیمی `up --build --force-recreate` نزن.

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

## nginx

### tasino2.spayerx.ir (ربات فعلی)

```sh
cd /opt/TasinoTelgramBot
git pull
sh scripts/setup-nginx-tasino2.sh
```

یا دستی:

```sh
apt install -y nginx certbot python3-certbot-nginx
mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled
cp docker/nginx-tasino2.spayerx.ir.conf /etc/nginx/sites-available/tasino2.spayerx.ir
ln -sf /etc/nginx/sites-available/tasino2.spayerx.ir /etc/nginx/sites-enabled/
certbot --nginx -d tasino2.spayerx.ir
nginx -t && systemctl reload nginx
```

### tasino.spayerx.ir

```sh
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
