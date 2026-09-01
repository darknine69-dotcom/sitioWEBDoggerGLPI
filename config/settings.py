"""
Django settings — Dogger HelpDesk
Conectado a Microsoft SQL Server 2022 (local) o PostgreSQL (cloud).
"""
import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "cambia-esta-clave-en-produccion-usa-openssl-rand-hex-32",
)

DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() in ("1", "true", "yes")

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
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

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
                "apps.tickets.context_processors.dogger_config",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Base de datos — SQL Server 2022 (local) o PostgreSQL (cloud)
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "")

if DATABASE_URL:
    # PostgreSQL en la nube (Render, Railway, etc.)
    DATABASES = {
        "default": dj_database_url.parse(DATABASE_URL)
    }
elif os.getenv("SMOKE_TEST_SQLITE", "False").lower() in ("1", "true", "yes"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "smoketest.sqlite3",
        }
    }
else:
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
                "extra_params": os.getenv(
                    "DB_EXTRA_PARAMS",
                    "TrustServerCertificate=yes",
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
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Límites de subida
FILE_UPLOAD_MAX_MEMORY_SIZE = 8 * 1024 * 1024  # 8 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Seguridad para producción
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

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
    "enabled": (
        os.getenv("GLPI_ENABLED", "False").lower() in ("1", "true", "yes")
        and bool(DATABASE_URL) is False
    ),
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
        "SIESA ERP (Comercial, Manufactura, Financiero, POS-FE)",
        "SIESA Web (Nómina, Autogestión, SiesaAccess)",
        "SIESA CLOUD-ERP",
        "Correo (CORREOS HUGE / Servidor de Correos)",
        "POS / puntos de venta (PC-P1 …)",
        "Firewall Fortinet 200E / WatchGuard",
        "Server Principal / Terminal Server",
        "GenericTransfer / Web Services",
    ],
}
