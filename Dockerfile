# ─── Stage 1: build ──────────────────────────────────────────────────────────
# gcc و libpq-dev فقط برای کامپایل psycopg2 لازمه، به runtime نمیره
FROM python:3.11-alpine AS builder

RUN apk add --no-cache gcc musl-dev libpq-dev

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ─── Stage 2: runtime ────────────────────────────────────────────────────────
FROM python:3.11-alpine

# فقط کتابخونه runtime پستگرس (بدون gcc)
RUN apk add --no-cache libpq

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/install/lib/python3.11/site-packages

WORKDIR /app

# کپی packages از stage قبل
COPY --from=builder /install /install

# کپی سورس (بدون .venv و cache — توسط .dockerignore فیلتر میشه)
COPY . .

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
