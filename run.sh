#!/usr/bin/env bash
# run_app.sh

# Run migrations at startup to ensure ephemeral disk is initialized
python manage.py migrate --noinput

# Start the web server
gunicorn proctoring_system.wsgi --timeout 120
