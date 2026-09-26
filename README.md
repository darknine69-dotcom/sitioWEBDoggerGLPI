# Dogger HelpDesk — Django + SQL Server 2022 / PostgreSQL + GLPI (opcional)

Mesa de ayuda de **Productos Alimenticios Dogger S.A.S.** alineada a la infraestructura STATU QUO (SIESA, POS, Fortinet, Server Principal).

**Desplegable en cualquier hosting** (Render, Railway, Fly.io, VPS con Docker, bare metal). Software 100% libre: Django + Gunicorn + PostgreSQL + Nginx. Ver sección [Despliegue](#despliegue).

## Características

- Portal público: crear tickets, adjuntar capturas, consultar por código `HD-XXXX`
- Panel staff: dashboard, filtros, estados, asignación de técnico, comentarios
- BD normalizada en **SQL Server 2022**
- Sincronización **opcional** hacia **GLPI** (API REST)
- Categorías de negocio: SIESA, POS, red/firewall, servidores, integraciones

## Inicio rápido

```bash
cd dogger_django
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# Editar .env (DB_* y DJANGO_SECRET_KEY)

python manage.py makemigrations accounts tickets
python manage.py migrate
python manage.py seed_categorias
python manage.py createsuperuser   # o shell create_user con rol=admin
python manage.py runserver
```

## Documentación

- **MANUAL.md** — operación, infraestructura Dogger, cómo hacer cambios, GLPI, smoke tests
- `.env.example` — variables de entorno

## Estructura

```
config/           settings, urls
apps/accounts/    Usuario + login
apps/tickets/     modelos, vistas, forms, services/glpi_client.py
templates/        portal, panel, consultar
static/css/       dogger-theme.css
media/adjuntos/   capturas
```

## GLPI

Por defecto `GLPI_ENABLED=False`. Cuando GLPI esté en la LAN:

```env
GLPI_ENABLED=True
GLPI_BASE_URL=http://glpi.dogger.local/apirest.php
GLPI_APP_TOKEN=...
GLPI_USER_TOKEN=...
```

Ver MANUAL.md sección 5.

## Despliegue

El proyecto está pensado para funcionar en **cualquier hosting** de forma genérica, leyendo toda la configuración desde variables de entorno (ver `.env.example`).

### Requisitos para producción

| Variable | Descripción |
|----------|-------------|
| `DJANGO_SECRET_KEY` | **Obligatorio** con `DJANGO_DEBUG=False`. |
| `DJANGO_ALLOWED_HOSTS` | Dominios/servicios permitidos (coma). |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Orígenes HTTPS del navegador (coma). |
| `DATABASE_URL` | Conexión a PostgreSQL (`postgres://...`). |
| `DJANGO_MEDIA_ROOT` | Ruta a un **volumen persistente** para adjuntos/avatares. |
| `GLPI_ENABLED` | `False` en la nube (GLPI solo para LAN). |

### Opción A — PaaS (Render, Railway, Fly.io)

1. Crea una base de datos PostgreSQL (la plataforma te da la `DATABASE_URL`).
2. Copia `.env.example` y define las variables de arriba.
3. En Render usa `render.yaml` o apunta build a `./build.sh` y start a `gunicorn config.wsgi:application`.
4. **Adjunta un disco/almacenamiento persistente** y apunta `DJANGO_MEDIA_ROOT` a él (los archivos se pierden si no).

### Opción B — VPS/hosting con Docker (Recomendado)

```bash
cp .env.example .env        # ajusta SECRET_KEY, dominio y password de BD
docker compose up -d --build
```

Esto levanta: **Django+Gunicorn**, **PostgreSQL** y **Nginx** (sirve estáticos/media y hace proxy). 

- Los volúmenes `pgdata` y `media` persisten los datos entre redespliegues.
- `nginx.conf` sirve por **HTTP** y es lo que funciona en local o detrás de un terminador TLS externo (Cloudflare, Caddy, proxy del hosting).

#### HTTPS en el mismo Nginx (p. ej. mi.com.co)

El orden importa: el bloque 443 no arranca sin certificados, así que pídelos primero (el `nginx.conf` por defecto ya sirve `/.well-known/acme-challenge/` desde `./certs`).

1. Con el stack en HTTP, pide el certificado a Let's Encrypt:

   ```bash
   docker run --rm -p 80:80 -v "$PWD/certs:/etc/letsencrypt" \
     certbot/certbot certonly --webroot -w /var/www/certbot \
     -d mi.com.co -d www.mi.com.co --agree-tos -m correo@dogger.com.co
   ```

2. Activa el TLS: `cp nginx.https.conf nginx.conf && docker compose up -d`
   (si tu dominio no es `mi.com.co`, cambia las 2 rutas `ssl_certificate` del bloque 443).

3. En `.env` del servidor:

   ```env
   DJANGO_ALLOWED_HOSTS=mi.com.co,www.mi.com.co
   DJANGO_CSRF_TRUSTED_ORIGINS=https://mi.com.co,https://www.mi.com.co
   DJANGO_SECURE_SSL_REDIRECT=True
   DJANGO_ENABLE_HSTS=True
   ```

4. Renueva antes de 90 días (crontab): el mismo `docker run ... certbot renew --webroot -w /var/www/certbot` y luego `docker compose restart nginx`.

`./certs/` está en `.gitignore` y `.dockerignore`: las llaves privadas nunca se versionan ni se copian dentro de la imagen.

### Opción C — Bare metal / servidor directo

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

Sirve estáticos con Nginx/Caddy y programa las tareas GLPI con tu cron.

### Seguridad al desplegar

- El `seed_usuarios` **ya no crea contraseñas hardcodeadas**: define `SEED_ADMIN_PASSWORD` (y `SEED_USUARIO_PASSWORD`) con valores seguros; en producción, si no se definen, **no se crean** usuarios de seed.
- Genera `DJANGO_SECRET_KEY` real para producción.
- No expongas SQL Server ni la API GLPI a internet.
