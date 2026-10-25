"""Atajos rápidos del botón X: catálogo por rol y selección del usuario.

El botón X de la barra flotante muestra dos clases de atajos:

- los del catálogo (`CATALOGO`), que dependen del rol y que la persona elige
  en Ajustes de cuenta;
- los enlaces propios (`atajos_enlaces`), que cada quien agrega a mano con
  su nombre, su URL y un icono.

Ambos se guardan en el usuario y aquí se resuelven a la lista que pinta
`accounts/_atajos.html`.
"""
from django.urls import reverse

# clave, etiqueta, icono, vista (None = acción JS) y roles que la ven.
CATALOGO = [
    ("consultar", "Consultar ticket", "i-search", "tickets:consultar",
     ("usuario", "tecnico", "admin", "observador")),
    ("crear", "Nueva solicitud", "i-plus", "tickets:crear_ticket",
     ("usuario", "tecnico", "admin")),
    ("mi-panel", "Mis solicitudes", "i-home", "tickets:mi_panel", ("usuario",)),
    ("panel-tec", "Mis asignados", "i-grid", "tickets:panel_tecnico", ("tecnico",)),
    ("dashboard", "Panel admin", "i-grid", "tickets:dashboard", ("admin",)),
    ("tickets", "Tickets", "i-ticket", "tickets:lista", ("admin", "tecnico")),
    ("usuarios", "Todos", "i-users", "tickets:usuarios", ("admin",)),
    ("reportes", "Reportes", "i-chart", "tickets:reportes", ("admin",)),
    ("exportar-rep", "Descargar reporte", "i-download", "tickets:exportar_reportes",
     ("admin",)),
    ("calendario", "Calendario", "i-calendar", "programador:panel_programador",
     ("tecnico", "admin")),
    ("obs-monitoreo", "Monitoreo", "i-check-circle", "tickets:obs_monitoreo",
     ("observador",)),
    ("obs-usuarios", "Usuarios", "i-user", "tickets:obs_usuarios", ("observador",)),
    ("obs-lista", "Todos", "i-layers", "tickets:obs_mi_lista", ("observador",)),
    ("obs-zonas", "Zonas", "i-folder", "tickets:obs_zonas", ("observador",)),
    ("obs-exportar", "Descargar lista", "i-download", "tickets:obs_exportar",
     ("observador",)),
    ("chat", "Chat de soporte", "i-message", None,
     ("usuario", "tecnico", "admin", "observador")),
]

POR_ROL = {
    "usuario": ("crear", "mi-panel", "chat"),
    "tecnico": ("panel-tec", "tickets", "calendario", "chat"),
    "admin": ("tickets", "usuarios", "reportes", "chat"),
    "observador": ("obs-monitoreo", "obs-usuarios", "obs-lista", "chat"),
}

# Iconos que se pueden elegir para un enlace propio. Los mismos del sprite.
ICONOS_ENLACE = (
    "i-link", "i-search", "i-ticket", "i-users", "i-user", "i-home", "i-grid",
    "i-chart", "i-folder", "i-calendar", "i-clock", "i-download", "i-plus",
    "i-message", "i-layers", "i-map-pin", "i-star", "i-book", "i-external",
)

_MAX_ENLACES = 12


def por_clave():
    """Catálogo indexado por clave."""
    return {e[0]: e for e in CATALOGO}


def disponibles_para(rol):
    """Entradas del catálogo que puede ver el rol."""
    return [e for e in CATALOGO if rol in e[4]]


def normaliza_enlaces(crudos):
    """Limpia los enlaces propios que llegan de Ajustes o del POST.

    Se conserva solo lo que tenga nombre y URL; se recorta el largo y se
    filtran los iconos desconocidos para no inyectar clases raras.
    """
    limpios = []
    for e in crudos or []:
        if not isinstance(e, dict):
            continue
        nombre = (e.get("nombre") or "").strip()[:60]
        url = (e.get("url") or "").strip()[:400]
        icono = (e.get("icono") or "").strip()
        if not nombre or not url:
            continue
        if icono not in ICONOS_ENLACE:
            icono = "i-link"
        limpios.append({"nombre": nombre, "url": url, "icono": icono})
        if len(limpios) >= _MAX_ENLACES:
            break
    return limpios


def para_usuario(usuario):
    """Atajos del botón X: los del catálogo elegidos + los enlaces propios."""
    rol = getattr(usuario, "rol", "") or ""
    elegidos = list(getattr(usuario, "atajos_rapidos", None) or [])
    if not elegidos:
        elegidos = list(POR_ROL.get(rol, ("consultar", "chat")))
    catalogo = {e[0]: e for e in disponibles_para(rol)}
    atajos = []
    for clave in elegidos:
        entrada = catalogo.get(clave)
        if entrada is None:
            continue
        _, etiqueta, icono, vista, _ = entrada
        atajos.append({
            "clave": clave,
            "etiqueta": etiqueta,
            "icono": icono,
            "url": reverse(vista) if vista else "",
            "propio": False,
        })
    # Los enlaces propios van al final y siempre se muestran.
    for enlace in normaliza_enlaces(getattr(usuario, "atajos_enlaces", None)):
        atajos.append({
            "clave": "propio:" + enlace["nombre"],
            "etiqueta": enlace["nombre"],
            "icono": enlace["icono"],
            "url": enlace["url"],
            "propio": True,
        })
    return atajos
