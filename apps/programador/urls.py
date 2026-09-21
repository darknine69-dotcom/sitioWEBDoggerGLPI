from django.urls import path

from . import views

app_name = "programador"

urlpatterns = [
    path("", views.panel_programador, name="panel_programador"),
    path("api/datos/", views.programador_datos, name="datos"),
    path("api/agregar/", views.programador_agregar, name="agregar"),
    path("api/eliminar/", views.programador_eliminar, name="eliminar"),
    path("api/completado/", views.programador_completado, name="completado"),
    path("api/disponibilidad/", views.programador_disponibilidad, name="disponibilidad"),
    path("api/festivo/", views.programador_festivo, name="festivo"),
]