#!/usr/bin/env bash
# build.sh — Render build script
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

echo "👤 Creando superusuario inicial (si no existe)..."
python manage.py shell -c "
from apps.accounts.models import Usuario
if not Usuario.objects.filter(rol='admin').exists():
    Usuario.objects.create_superuser('admin@dogger.com', nombre='Administrador', password='Admin123*')
    print('Superusuario creado: admin@dogger.com / Admin123*')
else:
    print('Ya existe un admin.')
" || true

echo "✅ Build completado."
