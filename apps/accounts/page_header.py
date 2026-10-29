"""Metadatos de navegación para la cabecera compartida."""
from django.utils import timezone
from django.urls import reverse

from .routing import landing_por_rol


# (sección, página actual, ruta intermedia opcional)
PAGINAS = {
    "tickets:dashboard": ("OPERACIÓN", "Panel", None),
    "tickets:panel_tecnico": ("OPERACIÓN", "Panel técnico", None),
    "tickets:mi_panel": ("OPERACIÓN", "Mi panel", None),
    "tickets:lista": ("GESTIÓN DE SOLICITUDES", "Tickets", None),
    "tickets:mis_tickets": ("GESTIÓN DE SOLICITUDES", "Mis tickets", None),
    "tickets:detalle": ("GESTIÓN DE SOLICITUDES", "Detalle", "tickets"),
    "tickets:mi_ticket": ("GESTIÓN DE SOLICITUDES", "Detalle", "tickets"),
    "tickets:mi_editar": ("GESTIÓN DE SOLICITUDES", "Editar solicitud", "tickets"),
    "tickets:crear_ticket": ("GESTIÓN DE SOLICITUDES", "Nueva solicitud", None),
    "tickets:sin_asignar": ("GESTIÓN DE SOLICITUDES", "Sin asignar", None),
    "tickets:papelera": ("GESTIÓN DE SOLICITUDES", "Papelera", None),
    "tickets:mi_papelera": ("GESTIÓN DE SOLICITUDES", "Mi papelera", None),
    "tickets:categorias_arbol": ("ADMINISTRACIÓN", "Categorías", None),
    "tickets:categorias_publico": ("CONSULTA", "Categorías", None),
    "tickets:usuarios": ("ADMINISTRACIÓN", "Usuarios", None),
    "tickets:reportes": ("ANÁLISIS Y ESTADÍSTICAS", "Reportes", None),
    "tickets:monitoreo_admin": ("SEGUIMIENTO OPERATIVO", "Monitoreo", None),
    "tickets:monitoreo_cuenta_detalle": ("SEGUIMIENTO OPERATIVO", "Detalle de cuenta", "monitoreo"),
    "tickets:tec_monitoreo": ("SEGUIMIENTO OPERATIVO", "Monitoreo", None),
    "tickets:tec_historial": ("SEGUIMIENTO OPERATIVO", "Historial", None),
    "tickets:obs_panel": ("OBSERVACIÓN", "Panel", None),
    "tickets:obs_buscar": ("OBSERVACIÓN", "Buscar", None),
    "tickets:obs_monitoreo": ("OBSERVACIÓN", "Monitoreo", None),
    "tickets:obs_usuarios": ("OBSERVACIÓN", "Usuarios", None),
    "tickets:obs_mi_lista": ("OBSERVACIÓN", "Mi lista", None),
    "tickets:obs_zonas": ("OBSERVACIÓN", "Zonas", None),
    "tickets:obs_zona_detalle": ("OBSERVACIÓN", "Detalle de zona", None),
    "tickets:consultar": ("AYUDA", "Consultar ticket", None),
    "tickets:faq": ("AYUDA", "Preguntas frecuentes", None),
    "tickets:quienes_somos": ("INFORMACIÓN", "Quiénes somos", None),
    "tickets:politica_privacidad": ("INFORMACIÓN", "Política de privacidad", None),
    "tickets:portal": ("MESA DE AYUDA TI", "Inicio", None),
    "programador:panel_programador": ("AGENDA Y PLANIFICACIÓN", "Programador", None),
    "accounts:ajustes": ("CONFIGURACIÓN DE CUENTA", "Mi perfil", None),
    "accounts:perfil": ("CONFIGURACIÓN DE CUENTA", "Ajustes de cuenta", None),
    "accounts:cambiar_password_forzado": ("CONFIGURACIÓN DE CUENTA", "Contraseña", None),
}


def encabezado_pagina(request):
    resolver = getattr(request, "resolver_match", None)
    nombre = resolver.view_name if resolver else ""
    seccion, actual, padre = PAGINAS.get(nombre, ("MESA DE AYUDA TI", "", None))
    user = request.user
    inicio = landing_por_rol(user)
    inicio_texto, inicio_icono = {
        "admin": ("Panel administrador", "i-chart"),
        "tecnico": ("Panel técnico", "i-wrench"),
        "usuario": ("Mi panel", "i-layers"),
        "observador": ("Monitoreo", "i-eye"),
    }.get(getattr(user, "rol", None), ("Portal", "i-home"))
    padres = []
    if padre == "tickets" and user.is_authenticated:
        ruta = {"admin": "tickets:lista", "tecnico": "tickets:mis_tickets", "usuario": "tickets:mi_panel"}.get(user.rol)
        if ruta:
            padres.append({"texto": "Tickets", "url": reverse(ruta)})
    elif padre == "monitoreo" and user.is_authenticated and user.rol == "admin":
        padres.append({"texto": "Monitoreo", "url": reverse("tickets:monitoreo_admin")})
    iconos = {"tickets": "i-ticket", "monitoreo": "i-eye"}
    if padre:
        icono = iconos.get(padre, "i-layers")
    elif nombre.startswith("accounts:"):
        icono = "i-user"
    elif nombre.startswith("programador:"):
        icono = "i-calendar"
    elif nombre in ("tickets:usuarios", "tickets:obs_usuarios"):
        icono = "i-users"
    elif nombre == "tickets:reportes":
        icono = "i-chart"
    elif nombre in ("tickets:monitoreo_admin", "tickets:tec_monitoreo", "tickets:obs_monitoreo"):
        icono = "i-eye"
    elif nombre in ("tickets:categorias_arbol", "tickets:categorias_publico"):
        icono = "i-folder"
    elif nombre in ("tickets:lista", "tickets:mis_tickets", "tickets:crear_ticket", "tickets:sin_asignar"):
        icono = "i-ticket"
    else:
        icono = inicio_icono if request.path == inicio else "i-layers"
    return {"encabezado": {"seccion": seccion, "actual": actual, "icono": icono, "padres": padres, "zona": timezone.get_current_timezone_name(), "perfil": nombre == "accounts:ajustes", "detalle_ticket": nombre in ("tickets:detalle", "tickets:mi_ticket", "tickets:mi_editar")}}
