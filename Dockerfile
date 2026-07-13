# syntax=docker/dockerfile:1.7
# BuildKit لازم است (docker compose v2 به‌صورت پیش‌فرض روشن است)

# ─── Stage 1: وابستگی‌ها (کش pip/apk بین بیلدها) ─────────────────────────────
FROM python:3.12-alpine AS builder

WORKDIR /app

RUN --mount=type=cache,target=/var/cache/apk,sharing=locked \
    apk add gcc musl-dev libpq-dev

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install --prefix=/install -r requirements.txt

# ─── Stage 2: runtime ────────────────────────────────────────────────────────
FROM python:3.12-alpine

RUN --mount=type=cache,target=/var/cache/apk,sharing=locked \
    apk add libpq postgresql-client curl

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/install/bin:${PATH}" \
    PYTHONPATH=/install/lib/python3.12/site-packages

WORKDIR /app

COPY --from=builder /install /install

# کد پروژه — با .dockerignore سبک می‌ماند تا لایه سریع‌تر کپی شود
COPY . .

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
 && mkdir -p /app/staticfiles

ENTRYPOINT ["/entrypoint.sh"]
