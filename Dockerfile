# Dogger HelpDesk — imagen genérica (funciona en cualquier VPS/hosting con Docker)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencias del sistema necesarias para Pillow / psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
        libjpeg62-turbo \
        zlib1g \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Dependencias Python
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Código de la app
COPY . .

# No exponer .env de desarrollo dentro de la imagen
RUN mkdir -p /app/staticfiles /app/media && rm -f .env

ENV DJANGO_DEBUG=False \
    DJANGO_SECURE_SSL_REDIRECT=False

# Build: migraciones + estáticos (el volumen de media se monta en runtime)
RUN python manage.py collectstatic --noinput || true

EXPOSE 8000

CMD ["sh", "/app/entrypoint.sh"]
