"""Restricciones administrativas por cuenta; nunca conceden permisos de rol."""

MODULOS = (
    ("tickets", "Tickets"), ("reportar", "Reportar incidencia"),
    ("calendario", "Calendario"), ("reportes", "Reportes"),
    ("monitoreo", "Monitoreo"), ("categorias", "Categorías"),
    ("papelera", "Papelera"), ("accesos", "Accesos"),
    ("historial", "Historial"), ("mi_lista", "Mi lista"),
    ("faq", "Preguntas frecuentes"), ("consultar", "Consultar ticket HD"),
)
CLAVES = frozenset(clave for clave, _ in MODULOS)
POR_ROL = {
    "admin": {"tickets", "calendario", "reportes", "monitoreo", "categorias", "papelera", "accesos", "faq", "consultar"},
    "tecnico": {"tickets", "calendario", "monitoreo", "categorias", "papelera", "historial", "faq", "consultar"},
    "usuario": {"reportar", "categorias", "papelera", "faq", "consultar"},
    "observador": {"monitoreo", "accesos", "categorias", "mi_lista", "faq", "consultar"},
}


def restringidos(usuario):
    preferencias = usuario.preferencias_notificaciones or {}
    valor = preferencias.get("modulos_restringidos", [])
    return frozenset(v for v in valor if isinstance(v, str) and v in CLAVES) if isinstance(valor, list) else frozenset()


def modulo_ruta(match):
    if match.namespace == "programador":
        return "calendario"
    if match.namespace != "tickets":
        return None
    nombre = match.url_name or ""
    if nombre in {"lista", "detalle", "staff_api_estado", "cambiar_estado", "ajustar_ans_ticket", "staff_reenviar_glpi"}:
        return "tickets"
    if nombre == "crear_ticket":
        return "reportar"
    if nombre == "tec_historial":
        return "historial"
    if nombre in {"obs_mi_lista", "obs_agregar", "obs_quitar", "obs_quitar_varios", "obs_auditoria_exportar"}:
        return "mi_lista"
    if nombre in {"faq", "consultar"}:
        return nombre
    if nombre in {"reportes", "exportar_admin", "exportar_reportes"}:
        return "reportes"
    if nombre.startswith(("categoria_", "categorias_")):
        return "categorias"
    if nombre in {"papelera", "mi_papelera", "restaurar", "purgar"}:
        return "papelera"
    if nombre.startswith(("usuario_", "usuarios_")) or nombre in {"usuarios", "obs_usuarios"}:
        return "accesos"
    if nombre.startswith(("monitoreo_", "obs_zona")) or nombre in {"tec_monitoreo", "obs_monitoreo", "obs_presionar", "obs_exportar"}:
        return "monitoreo"
    return None
