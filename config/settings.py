"""
Django settings — Dogger HelpDesk
Conectado a Microsoft SQL Server 2022 (local), PostgreSQL (cloud) o
MySQL/MariaDB (hosting compartido).
"""
import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url
from django.core.exceptions import ImproperlyConfigured

load_dotenv(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")

DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() in ("1", "true", "yes")

# En producción, exigir una SECRET_KEY real (no un placeholder inseguro).
# Para desarrollo local, DJANGO_DEBUG=True en el .env.
if not DEBUG and not SECRET_KEY:
    raise RuntimeError(
        "DJANGO_SECRET_KEY es obligatorio cuando DJANGO_DEBUG=False. "
        "En desarrollo usa DJANGO_DEBUG=True; en producción genera una con: "
        "python -c \"import secrets; print(secrets.token_urlsafe(50))\""
    )

ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv(
        "DJANGO_ALLOWED_HOSTS",
        "localhost,127.0.0.1,0.0.0.0",
    ).split(",")
    if h.strip()
]
if "testserver" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("testserver")

CSRF_TRUSTED_ORIGINS = [
    h.strip()
    for h in os.getenv(
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        "http://localhost:8000,http://127.0.0.1:8000,http://0.0.0.0:8000",
    ).split(",")
    if h.strip()
]
if "http://testserver" not in CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append("http://testserver")

# ---------------------------------------------------------------------------
# Apps
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Apps del proyecto
    "apps.accounts",
    "apps.tickets",
    "apps.programador",
    "apps.notificaciones",
]

# La vista previa del manual se muestra dentro de un iframe de los ajustes.
# "DENY" (que es el valor por defecto de Django) la deja siempre en blanco,
# asi que se permite solo el mismo sitio: nadie mas puede embebernos.
X_FRAME_OPTIONS = os.getenv("DJANGO_X_FRAME_OPTIONS", "SAMEORIGIN")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "config.middleware.SeguridadHeadersMiddleware",
    "config.middleware.RolSincronizadoMiddleware",
]

if DEBUG:
    # En desarrollo WhiteNoise servía la copia vieja de staticfiles/ e
    # ignoraba los cambios (el ?v= no le afecta): sin él, Django sirve
    # directo del disco y siempre se ve lo último. En producción sigue.
    MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.notificaciones.context_processors.notificaciones",
                "apps.accounts.context_processors.atajos",
                "apps.accounts.page_header.encabezado_pagina",
                "apps.tickets.context_processors.dogger_config",
                "apps.tickets.context_processors.calificacion_lateral",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Base de datos — SQL Server 2022 (local), PostgreSQL (cloud) o MySQL (cPanel)
# ---------------------------------------------------------------------------
try:
    import pymysql

    pymysql.install_as_MySQLdb()
except ImportError:
    pass

DATABASE_URL = os.getenv("DATABASE_URL", "")
DB_ENGINE = os.getenv("DOGGER_DB_ENGINE", "").strip().lower()
if DB_ENGINE not in ("", "mysql", "mssql", "postgresql"):
    raise ImproperlyConfigured("DOGGER_DB_ENGINE debe ser mysql, mssql o postgresql.")

if os.getenv("SMOKE_TEST_SQLITE", "False").lower() in ("1", "true", "yes"):
    # Las pruebas aisladas nunca deben heredar DATABASE_URL de producción.
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "smoketest.sqlite3",
        }
    }
elif DATABASE_URL:
    # Una URL explícita selecciona el motor; nunca recurrir a otra base.
    _database = dj_database_url.parse(DATABASE_URL)
    _engines = {"mysql": "django.db.backends.mysql", "postgresql": "django.db.backends.postgresql"}
    if _database.get("ENGINE") not in _engines.values():
        raise ImproperlyConfigured("DATABASE_URL debe usar MySQL o PostgreSQL.")
    if DB_ENGINE and _engines.get(DB_ENGINE) != _database["ENGINE"]:
        raise ImproperlyConfigured("DOGGER_DB_ENGINE no coincide con DATABASE_URL.")
    if _database["ENGINE"] == _engines["mysql"]:
        if not all(_database.get(k) for k in ("NAME", "USER", "HOST")):
            raise ImproperlyConfigured("DATABASE_URL de MySQL requiere base, usuario y servidor.")
        _database.setdefault("OPTIONS", {})["charset"] = "utf8mb4"
    DATABASES = {
        "default": _database
    }
else:
    if DB_ENGINE in ("mysql", "postgresql"):
        raise ImproperlyConfigured("El motor seleccionado requiere DATABASE_URL.")
    if not DEBUG and DB_ENGINE != "mssql":
        raise ImproperlyConfigured("Sin DATABASE_URL, configura DOGGER_DB_ENGINE=mssql explícitamente.")
    DATABASES = {
        "default": {
            "ENGINE": "mssql",
            "NAME": os.getenv("DB_NAME", "Tickets"),
            "USER": os.getenv("DB_USER", "DGT"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "localhost"),
            "PORT": os.getenv("DB_PORT", "1433"),
            "OPTIONS": {
                "driver": os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server"),
                "host_is_server": True,
                "extra_params": os.getenv("DB_EXTRA_PARAMS") or (
                    "TrustServerCertificate=yes" if DEBUG else "TrustServerCertificate=no"
                ),
            },
        }
    }

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.Usuario"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "tickets:dashboard"
LOGOUT_REDIRECT_URL = "tickets:portal"

# ---------------------------------------------------------------------------
# Internacionalización
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Archivos estáticos y media (capturas)
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    # En desarrollo se sirve directo del disco (con ?v= por fecha): el
    # manifest con hash dejaba el CSS/JS viejo o roto si no se corría
    # collectstatic en cada cambio. En producción sí va con manifest.
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG else
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

MEDIA_URL = os.getenv("DJANGO_MEDIA_URL", "/media/")
MEDIA_ROOT = Path(os.getenv("DJANGO_MEDIA_ROOT", BASE_DIR / "media"))

# Límites de subida
FILE_UPLOAD_MAX_MEMORY_SIZE = 8 * 1024 * 1024  # 8 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Versión visible del sistema (auditoría, pie, reportes).
DOGGER_VERSION = os.getenv("DOGGER_VERSION", "2.0")

# ---------------------------------------------------------------------------
# Caché y trabajo en segundo plano
# ---------------------------------------------------------------------------
# Sin Redis en el hosting: memoria local por proceso, con TTL cortos y
# claves versionadas. Para Redis real habría que instalar django-redis y
# apuntar esta URL por variable de entorno.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "dogger-cache",
        "TIMEOUT": int(os.getenv("DOGGER_CACHE_TIMEOUT", "300")),
        "OPTIONS": {"MAX_ENTRIES": int(os.getenv("DOGGER_CACHE_MAX", "2000"))},
    }
}

# Correos y avisos a GLPI en hilos daemon para no frenar el request.
# Apagar solo para depurar envíos (DOGGER_FONDO_ASINCRONO=false).
DOGGER_FONDO_ASINCRONO = os.getenv("DOGGER_FONDO_ASINCRONO", "True").lower() in (
    "1",
    "true",
    "yes",
)
# En producción no perder trabajos al reiniciar procesos web. El entorno de
# pruebas aislado y desarrollo conservan ejecución síncrona/hilos existentes.
_cola_default = "False" if DEBUG or os.getenv("SMOKE_TEST_SQLITE", "False").lower() in ("1", "true", "yes") else "True"
DOGGER_FONDO_DURABLE = os.getenv("DOGGER_FONDO_DURABLE", _cola_default).lower() in ("1", "true", "yes")
if DOGGER_FONDO_DURABLE and not DEBUG:
    from cryptography.fernet import Fernet
    try:
        Fernet((os.getenv("DOGGER_FERNET_KEY") or "").strip().encode())
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured("DOGGER_FERNET_KEY válida es obligatoria para la cola durable en producción.") from exc

# ---------------------------------------------------------------------------
# Seguridad para producción
# ---------------------------------------------------------------------------
# Cookies de sesión siempre explícitas (HttpOnly y SameSite los pone Django
# por defecto, aquí quedan blindados contra un cambio de versión).
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # el JS del chat lee el csrftoken de la cookie
SESSION_COOKIE_AGE = int(os.getenv("DJANGO_SESSION_AGE", "1209600"))

if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    # Secure por defecto en produccion (obligatorio con HTTPS), pero
    # overridable: sin TLS el navegador no guarda el cookie de sesion y
    # nadie puede iniciar sesion (util al publicar por tunel/HTTP interno).
    SESSION_COOKIE_SECURE = os.getenv("DJANGO_SESSION_COOKIE_SECURE", "True").lower() in (
        "1",
        "true",
        "yes",
    )
    CSRF_COOKIE_SECURE = os.getenv("DJANGO_CSRF_COOKIE_SECURE", "True").lower() in (
        "1",
        "true",
        "yes",
    )

    # HTTPS general: se habilita por defecto en producción, pero se puede
    # apagar (SECURE_SSL_REDIRECT=false) si un proxy/balancer ya fuerza HTTPS.
    SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "True").lower() in (
        "1",
        "true",
        "yes",
    )
    # Cuando un proxy (Nginx, Caddy, Load Balancer) termina el SSL, confiamos
    # en la cabecera X-Forwarded-Proto para no redirigir en bucle.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

    # HSTS solo cuando realmente servimos por HTTPS directo.
    if os.getenv("DJANGO_ENABLE_HSTS", "True").lower() in ("1", "true", "yes"):
        SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "31536000"))
        SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("DJANGO_HSTS_INCLUDE_SUBDOMAINS", "False").lower() in ("1", "true", "yes")
        SECURE_HSTS_PRELOAD = os.getenv("DJANGO_HSTS_PRELOAD", "False").lower() in ("1", "true", "yes")

# ---------------------------------------------------------------------------
# Email (SMTP — Servidor Dogger directo)
# ---------------------------------------------------------------------------
# Se aceptan ambas convenciones de nombre de variable: EMAIL_* y DJANGO_EMAIL_*
EMAIL_BACKEND = os.getenv(
    "DJANGO_EMAIL_BACKEND",
    os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"),
)
EMAIL_HOST = os.getenv("DJANGO_EMAIL_HOST", os.getenv("EMAIL_HOST", "smtp.office365.com"))
EMAIL_PORT = int(os.getenv("DJANGO_EMAIL_PORT", os.getenv("EMAIL_PORT", "587")))
EMAIL_TIMEOUT = int(os.getenv("DJANGO_EMAIL_TIMEOUT", "15"))
EMAIL_USE_TLS = os.getenv(
    "DJANGO_EMAIL_USE_TLS", os.getenv("EMAIL_USE_TLS", "True")
).lower() in ("1", "true", "yes")
EMAIL_HOST_USER = os.getenv("DJANGO_EMAIL_HOST_USER", os.getenv("EMAIL_USER", ""))
EMAIL_HOST_PASSWORD = os.getenv("DJANGO_EMAIL_HOST_PASSWORD", os.getenv("EMAIL_PASSWORD", ""))
DEFAULT_FROM_EMAIL = os.getenv("DJANGO_DEFAULT_FROM_EMAIL", os.getenv("EMAIL_FROM", EMAIL_HOST_USER))

# Sin credenciales SMTP configuradas (o en el entorno de pruebas), el envío
# se hace por consola para que la recuperación de contraseña nunca falle en silencio.
_smoke_test = os.getenv("SMOKE_TEST_SQLITE", "False").lower() in ("1", "true", "yes")
if _smoke_test or (DEBUG and not EMAIL_HOST_USER and not EMAIL_HOST_PASSWORD):
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
elif not DEBUG:
    if EMAIL_BACKEND in ("django.core.mail.backends.console.EmailBackend", "django.core.mail.backends.dummy.EmailBackend", "django.core.mail.backends.filebased.EmailBackend"):
        raise ImproperlyConfigured("El backend de correo de producción debe entregar mensajes.")
    if EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend" and (not EMAIL_HOST_USER or not EMAIL_HOST_PASSWORD):
        raise ImproperlyConfigured("Configura las credenciales SMTP para producción.")

# ---------------------------------------------------------------------------
# Configuración Dogger
# ---------------------------------------------------------------------------
DOGGER = {
    "empresa": "DOGGER",
    "nombre_completo": "Productos Alimenticios Dogger S.A.S.",
    "direccion": "Envigado, Antioquia, Colombia",
    "direccion_detalle": "Calle 39 sur 26-09, Envigado, Antioquia, Colombia",
    "mapa_google": "https://www.google.com/maps?q=Productos%20Alimenticios%20Dogger%20Envigado%20Antioquia&output=embed",
    "correo_soporte": os.getenv("DOGGER_CORREO", "sistemasbogota@dogger.com.co"),
    "whatsapp_soporte": os.getenv("DOGGER_WHATSAPP", "3103716129"),
    # Contacto y ventana de atención (se muestran en la portada y en el pie).
    "telefono_soporte": os.getenv("DOGGER_TELEFONO", ""),
    "horario_atencion": os.getenv(
        "DOGGER_HORARIO",
        "Lunes a jueves 8:00 a.m.–5:30 p.m. · Viernes y sábado 7:00 a.m.–3:30 p.m.",
    ),
    # Agenda detallada: se muestra como tabla en la sección de contacto.
    "horario_detalle": [
        {"dias": "Lunes a jueves", "hora": "8:00 a.m. – 5:30 p.m.",
         "nota": "Mesa de ayuda y atención en sitio"},
        {"dias": "Viernes y sábado", "hora": "7:00 a.m. – 3:30 p.m.",
         "nota": "Mesa de ayuda y atención en sitio"},
        {"dias": "Domingos y festivos", "hora": "Horario hábil",
         "nota": "Soporte en horario hábil"},
    ],
    # Aviso destacado de la portada. Vacío = no se muestra banda de aviso.
    # Ejemplo: "Mantenimiento programado de SIESA el sábado 3 de octubre, 6:00 p.m."
    "aviso_destacado": os.getenv("DOGGER_AVISO", ""),
    # Redes sociales (se muestran como iconos en el pie del portal).
    "pagina_mostrar_redes": True,
    "correo_activo": True,
    "whatsapp_activo": True,
    "facebook": os.getenv("DOGGER_FACEBOOK", "https://web.facebook.com/DoggerColombia"),
    "facebook_activo": True,
    "instagram": os.getenv("DOGGER_INSTAGRAM", "https://www.instagram.com/dogger1996"),
    "instagram_activo": True,
    "tiktok": os.getenv("DOGGER_TIKTOK", ""),
    "tiktok_activo": True,
    "teams": os.getenv("DOGGER_TEAMS", ""),
    "teams_activo": True,
    "max_adjuntos": 5,
    "max_adjunto_mb": 8,
    # Puntos Dogger activos (mostrados con mapa en el pie del portal).
    # Editar aquí cuando abran/cierren un punto. 'maps_q' = búsqueda de Google Maps.
    "puntos": [
        {
            "nombre": "Sede principal · Planta",
            "ciudad": "Envigado",
            "detalle": "Calle 39 Sur 26-09",
            "tipo": "planta",
            "maps_q": "Productos Alimenticios Dogger Envigado Antioquia",
        },
        {
            "nombre": "CC Viva Envigado",
            "ciudad": "Envigado",
            "detalle": "Cra. 48 #32B Sur-139 · Pisos 1 y 3",
            "tipo": "local",
            "maps_q": "Dogger Viva Envigado",
        },
        {
            "nombre": "Éxito Envigado",
            "ciudad": "Envigado",
            "detalle": "Centro comercial Éxito Envigado",
            "tipo": "local",
            "maps_q": "Dogger Éxito Envigado",
        },
        {
            "nombre": "Punto Medellín",
            "ciudad": "Medellín",
            "detalle": "Cra. 65A #13-175, Local 31A",
            "tipo": "local",
            "maps_q": "Dogger Carrera 65A 13-175 Medellín",
        },
        {
            "nombre": "Aeropuertos · Aéreo DG",
            "ciudad": "Rionegro (JMC)",
            "detalle": "Puntos en aeropuertos",
            "tipo": "aeropuerto",
            "maps_q": "Dogger Aeropuerto José María Córdova Rionegro",
        },
    ],
}

# ---------------------------------------------------------------------------
# GLPI (sincronización opcional hacia el ITSM corporativo)
# ---------------------------------------------------------------------------
# En la nube, GLPI queda desactivado por defecto (solo accesible en LAN).
GLPI = {
    "enabled": os.getenv("GLPI_ENABLED", "False").lower() in ("1", "true", "yes"),
    "base_url": os.getenv("GLPI_BASE_URL", "http://glpi.dogger.local/apirest.php"),
    "app_token": os.getenv("GLPI_APP_TOKEN", ""),
    "user_token": os.getenv("GLPI_USER_TOKEN", ""),
    "timeout": int(os.getenv("GLPI_TIMEOUT", "30")),
    # Si True, falla silencioso (solo log) al no poder sincronizar
    "fail_silent": True,
}

# Secret compartido con el webhook configurado en GLPI (header X-Dogger-Secret)
GLPI_WEBHOOK_SECRET = os.getenv("GLPI_WEBHOOK_SECRET", "")

# Infraestructura de referencia (documentación / portal)
DOGGER_INFRA = {
    "empresa": "Productos Alimenticios Dogger S.A.S.",
    "direccion": "Calle 39 sur 26-09, Envigado, Antioquia, Colombia",
    "telefono": "57(604)3333232",
    "sistemas_clave": [
        "SIESA ERP (ventas, producción, contabilidad, facturación electrónica)",
        "SIESA Web (Nómina, Autogestión, SiesaAccess)",
        "SIESA CLOUD-ERP",
        "Correo (CORREOS HUGE / Servidor de Correos)",
        "POS / puntos de venta (PC-P1 …)",
        "Firewall Fortinet 200E / WatchGuard",
        "Server Principal / Terminal Server",
        "GenericTransfer / Web Services",
    ],
}
