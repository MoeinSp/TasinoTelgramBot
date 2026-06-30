#!/bin/sh
set -e

echo "==> migrate"
python manage.py migrate --no-input

echo "==> bot start"
exec python -m bot.main
