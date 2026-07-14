#!/bin/sh
set -e

# ── Optional: run production storage verification ────────────────────────────
if [ "${RUN_VERIFICATION}" = "true" ]; then
    echo "→ Running production storage verification..."
    python manage.py verify_railway_storage_flows --execute
    exit $?
fi

# ── Optional: run pending migrations ──────────────────────────────────────────
if [ "${RUN_MIGRATIONS}" = "true" ]; then
    echo "→ Running database migrations..."
    python manage.py migrate --noinput
fi

# ── Collect static files ──────────────────────────────────────────────────────
echo "→ Collecting static files..."
python manage.py collectstatic --noinput --clear

# ── Start Gunicorn ────────────────────────────────────────────────────────────
WORKERS="${GUNICORN_WORKERS:-4}"
TIMEOUT="${GUNICORN_TIMEOUT:-120}"

echo "→ Starting Gunicorn (workers=${WORKERS}, timeout=${TIMEOUT})..."
PORT="${PORT:-8000}"

exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:"${PORT}" \
    --workers "${WORKERS}" \
    --timeout "${TIMEOUT}" \
    --access-logfile - \
    --error-logfile - \
    --worker-class sync
