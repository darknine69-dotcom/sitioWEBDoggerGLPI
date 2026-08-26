from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from apps.accounts.views_seed import seed_usuarios_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.tickets.urls")),
    path("cuenta/", include("apps.accounts.urls")),
    path("seed-usuarios/", seed_usuarios_view, name="seed_usuarios"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
