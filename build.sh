#!/usr/bin/env bash
# build.sh — Script de build genérico para PaaS / VPS / Docker
set -o errexit

echo "📦 Instalando dependencias..."
pip install --upgrade pip
pip install -r requirements.txt

echo "🗄️  Ejecutando migraciones..."
python manage.py migrate --noinput

echo "📁 Recopilando archivos estáticos..."
python manage.py collectstatic --noinput

echo "🌱 Sembrando categorías iniciales..."
python manage.py seed_categorias || true

echo "👤 Creando usuarios iniciales..."
python manage.py seed_usuarios || true

echo "✅ Build completado."
