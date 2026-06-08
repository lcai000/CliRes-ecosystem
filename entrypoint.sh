#!/bin/bash
set -e

python manage.py migrate --noinput

exec gunicorn clires_dashboard.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
