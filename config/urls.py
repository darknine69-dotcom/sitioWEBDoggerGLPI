import os
import re

from django.contrib import admin
from django.urls import path, include, re_path
from django.http import Http404
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.tickets.urls")),
    path("cuenta/", include("apps.accounts.urls")),
    path("programador/", include("apps.programador.urls")),
    path("notificaciones/", include("apps.notificaciones.urls")),
]

# Las páginas de "no tienes acceso" y "no encontramos esa página" son las de
# Dogger, no las grises de Django. Son dos manejadores y no uno porque varias
# vistas lanzan Http404 (que es un 404, no un 403) cuando el registro no es
# visible para quien pregunta.
handler403 = "apps.accounts.views.pagina_no_autorizada"
handler404 = "apps.accounts.views.pagina_no_encontrada"
handler500 = "apps.accounts.views.pagina_error"


def _adjunto_privado(request):
    raise Http404


# Evita saltarse los permisos de la vista de adjuntos mediante MEDIA_URL.
if settings.MEDIA_URL.startswith("/"):
    urlpatterns.append(re_path(r"^" + re.escape(settings.MEDIA_URL.lstrip("/")) + r"adjuntos/", _adjunto_privado))

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
elif os.getenv("DJANGO_SERVE_MEDIA", "False").lower() in ("1", "true", "yes"):
    # `static()` no agrega rutas con DEBUG=False. Solo se ofrecen los avatares
    # públicos; los adjuntos siguen pasando por la vista con autorización.
    from django.views.static import serve

    if settings.MEDIA_URL.startswith("/"):
        prefijo = re.escape(settings.MEDIA_URL.lstrip("/"))
        urlpatterns.append(re_path(
            r"^" + prefijo + r"avatars/(?P<path>.+)$", serve,
            {"document_root": settings.MEDIA_ROOT / "avatars", "show_indexes": False},
        ))
