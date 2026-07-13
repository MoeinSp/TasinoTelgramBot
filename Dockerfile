# ─── Stage 1: build ──────────────────────────────────────────────────────────
FROM python:3.12-alpine AS builder

RUN apk add --no-cache gcc musl-dev libpq-dev

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ─── Stage 2: runtime ────────────────────────────────────────────────────────
FROM python:3.12-alpine

# libpq + کلاینت دامپ/بازیابی + ابزار شبکه برای healthcheck
RUN apk add --no-cache libpq postgresql-client curl

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/install/bin:${PATH}" \
    PYTHONPATH=/install/lib/python3.12/site-packages

WORKDIR /app

COPY --from=builder /install /install
COPY . .

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
 && mkdir -p /app/staticfiles

ENTRYPOINT ["/entrypoint.sh"]
