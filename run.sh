#!/usr/bin/env bash
# run_app.sh

# Exit immediately if any command fails
set -o errexit

echo "==> Cleaning stale database files... (Force fresh start)"
rm -f db.sqlite3

echo "==> Verifying system integrity..."
python manage.py check

echo "==> Running migrations (Level 2 Verbosity)..."
python manage.py migrate --noinput --verbosity 2

echo "==> Final Migration Status:"
python manage.py showmigrations

echo "==> Starting Gunicorn Application Server..."
gunicorn proctoring_system.wsgi --timeout 120
