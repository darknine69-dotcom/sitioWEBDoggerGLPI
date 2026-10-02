from django.urls import path

from . import views

app_name = "notificaciones"

urlpatterns = [
    path("marcar-todas/", views.marcar_todas, name="marcar_todas"),
    path("descartar/", views.descartar_todas, name="descartar_todas"),
    path("<int:pk>/quitar/", views.descartar, name="descartar_una"),
    path("<int:pk>/mostrada/", views.marcar_mostrada, name="marcar_mostrada"),
    path("api/", views.api, name="api"),
]
