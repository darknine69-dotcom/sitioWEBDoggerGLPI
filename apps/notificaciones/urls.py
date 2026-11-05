from django.urls import path

from . import views

app_name = "notificaciones"

urlpatterns = [
    path("", views.centro, name="centro"),
    path("leer-todas/", views.leer_todas_centro, name="leer_todas_centro"),
    path("alertas/", views.alertas_operativas, name="alertas_operativas"),
    path("alertas/<int:pk>/accion/", views.accion_alerta, name="accion_alerta"),
    path("<int:pk>/accion/", views.accion_centro, name="accion_centro"),
    path("marcar-todas/", views.marcar_todas, name="marcar_todas"),
    path("descartar/", views.descartar_todas, name="descartar_todas"),
    path("<int:pk>/quitar/", views.descartar, name="descartar_una"),
    path("<int:pk>/mostrada/", views.marcar_mostrada, name="marcar_mostrada"),
    path("<int:pk>/leer/", views.marcar_leida, name="marcar_leida"),
    path("api/", views.api, name="api"),
]
