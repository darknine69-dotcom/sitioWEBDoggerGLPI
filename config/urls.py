import os

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.tickets.urls")),
    path("cuenta/", include("apps.accounts.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
elif os.getenv("DJANGO_SERVE_MEDIA", "False").lower() in ("1", "true", "yes"):
    # Sirve los archivos de media en producción cuando Django gestiona el
    # almacenamiento local (p. ej. Docker sin servidor externo). Usa esta
    # opción solo si no tienes Nginx/Caddy/cloud para servirlos.
    from django.conf.urls.static import static as _static

    urlpatterns += _static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
