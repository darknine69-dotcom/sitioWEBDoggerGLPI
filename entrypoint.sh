#!/usr/bin/env bash
# entrypoint.sh — inicialización al arrancar el contenedor
set -e

echo "Aplicando migraciones..."
python manage.py migrate --noinput

echo "Recopilando estáticos..."
python manage.py collectstatic --noinput || true

echo "Sembrando datos base (no rompe si ya existen)..."
python manage.py seed_categorias || true
python manage.py seed_usuarios || true

echo "Iniciando gunicorn..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${GUNICORN_WORKERS:-2} --timeout 120
