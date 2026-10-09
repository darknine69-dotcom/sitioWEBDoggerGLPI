"""Atajos rápidos del botón X: catálogo por rol y selección del usuario."""
from django.urls import reverse

# clave, etiqueta, icono, vista (None = acción JS) y roles que la ven.
CATALOGO = [
    ("consultar", "Consultar ticket", "i-search", "tickets:consultar",
     ("usuario", "tecnico", "admin", "observador")),
    ("crear", "Reportar incidencia", "i-plus", "tickets:crear_ticket",
     ("usuario", "tecnico", "admin")),
    ("mi-panel", "Mis solicitudes", "i-home", "tickets:mi_panel", ("usuario",)),
    ("panel-tec", "Panel técnico", "i-grid", "tickets:panel_tecnico", ("tecnico",)),
    ("dashboard", "Panel admin", "i-grid", "tickets:dashboard", ("admin",)),
    ("tickets", "Tickets", "i-ticket", "tickets:lista", ("admin", "tecnico")),
    ("reportes", "Reportes", "i-chart", "tickets:reportes", ("admin",)),
    ("exportar-rep", "Descargar reporte", "i-download", "tickets:exportar_reportes",
     ("admin",)),
    ("calendario", "Calendario", "i-calendar", "programador:panel_programador",
     ("tecnico", "admin")),
    ("obs-monitoreo", "Monitoreo", "i-check-circle", "tickets:obs_monitoreo",
     ("observador",)),
    ("obs-usuarios", "Usuarios", "i-user", "tickets:obs_usuarios", ("observador",)),
    ("obs-lista", "Mi lista", "i-layers", "tickets:obs_mi_lista", ("observador",)),
    ("obs-zonas", "Zonas", "i-folder", "tickets:obs_zonas", ("observador",)),
    ("obs-exportar", "Descargar lista", "i-download", "tickets:obs_exportar",
     ("observador",)),
    ("chat", "Chat de soporte", "i-message", None,
     ("usuario", "tecnico", "admin", "observador")),
]

POR_ROL = {
    "usuario": ("consultar", "crear", "mi-panel", "chat"),
    "tecnico": ("panel-tec", "tickets", "calendario", "chat"),
    "admin": ("dashboard", "tickets", "reportes", "chat"),
    "observador": ("obs-monitoreo", "obs-usuarios", "obs-lista", "chat"),
}


def disponibles_para(rol):
    """Entradas del catálogo que puede ver el rol."""
    return [e for e in CATALOGO if rol in e[4]]


def para_usuario(usuario):
    """Atajos del botón X: los elegidos en Ajustes o los de su rol."""
    rol = getattr(usuario, "rol", "") or ""
    elegidos = [c for c in (getattr(usuario, "atajos_rapidos", None) or [])]
    if not elegidos:
        elegidos = list(POR_ROL.get(rol, ("consultar", "chat")))
    por_clave = {e[0]: e for e in disponibles_para(rol)}
    atajos = []
    for clave in elegidos:
        entrada = por_clave.get(clave)
        if entrada is None:
            continue
        _, etiqueta, icono, vista, _ = entrada
        atajos.append({
            "clave": clave,
            "etiqueta": etiqueta,
            "icono": icono,
            "url": reverse(vista) if vista else "",
        })
    return atajos
