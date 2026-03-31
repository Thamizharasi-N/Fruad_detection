#!/usr/bin/env bash
# run_app.sh

# Exit immediately if any command fails
set -o errexit

echo "==> Running Django Migrations..."
python manage.py migrate --noinput

echo "==> Starting Gunicorn Application Server..."
gunicorn proctoring_system.wsgi --timeout 120
