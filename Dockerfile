# فقط وابستگی‌ها — کد پروژه از volume می‌آید (بدون بیلد مجدد برای هر تغییر)
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libpq + postgresql-client برای pg_dump/pg_restore/psql (بکاپ از پنل)
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 curl postgresql-client \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
 && mkdir -p /app/staticfiles

ENTRYPOINT ["sh", "/entrypoint.sh"]
