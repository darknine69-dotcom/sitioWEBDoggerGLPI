"""Índice de navegación segura: nunca ejecuta acciones que modifican datos."""
from difflib import SequenceMatcher
import unicodedata

from django.urls import reverse

from apps.accounts.atajos import CATALOGO

ALL = ("admin", "tecnico", "usuario", "observador")
STAFF = ("admin", "tecnico")

# Las acciones llevan a una página o pestaña existente; nunca a un POST.
# clave, nombre, descripción, términos, grupo, ruta, fragmento, icono, roles
REGISTRY = (
    ("perfil", "Mi perfil", "Consultar y editar mis datos", "cuenta usuario nombre correo configuracion", "Configuraciones", "accounts:ajustes", "perfil", "i-user", ALL),
    ("password", "Cambiar contraseña", "Seguridad de mi cuenta", "clave password seguridad configuracion", "Configuraciones", "accounts:ajustes", "password", "i-lock", ALL),
    ("notificaciones", "Configurar notificaciones", "Elegir avisos y preferencias", "notificacion aviso correo configuracion", "Configuraciones", "accounts:ajustes", "notificaciones", "i-bell", ALL),
    ("atajos", "Configurar accesos rápidos", "Personalizar los accesos rápidos", "atajos enlaces preferencias configuracion", "Configuraciones", "accounts:ajustes", "atajos", "i-grid", ALL),
    ("ayuda", "Ayuda y recorrido", "Consultar ayuda de la aplicación", "manual tutorial guia configuracion", "Configuraciones", "accounts:ajustes", "ayuda", "i-help", ALL),
    ("pagina", "Configuración de página y permisos", "Personalizar la página y gestionar permisos", "configuracion accesos permisos autorizacion privilegios dar permiso rol", "Usuarios y permisos", "accounts:ajustes", "pagina", "i-settings", ("admin",)),
    ("glpi", "Configuración GLPI", "Ajustar la integración GLPI", "configuracion integracion conexion", "Configuraciones", "accounts:ajustes", "glpi", "i-settings", ("admin",)),
    ("usuarios-admin", "Administrar usuarios", "Gestionar cuentas, roles y acceso", "crear cuenta editar usuario cambiar rol bloquear desactivar usuario accesos permisos", "Usuarios y permisos", "tickets:usuarios", "", "i-users", ("admin",)),
    ("reportes", "Consultar reportes", "Abrir reportes y opciones de exportación", "descargar reporte estadistica exportar", "Páginas y módulos", "tickets:reportes", "", "i-chart", ("admin",)),
    ("categorias", "Categorías de soporte", "Consultar categorías y subcategorías", "categoria subcategoria soporte", "Páginas y módulos", "tickets:categorias_arbol", "", "i-folder", STAFF),
    ("crear-categoria", "Crear categoría", "Abrir el formulario de categoría", "agregar crear categoria configuracion ticket sla ans", "Acciones rápidas", "tickets:categorias_arbol", "buscar-crear-categoria", "i-folder", ("admin",)),
    ("reasignar-ticket", "Reasignar técnico", "Abrir la bandeja y seleccionar un ticket", "asignar cambiar tecnico responsable ticket", "Acciones rápidas", "tickets:lista", "", "i-user", STAFF),
    ("prioridad-ticket", "Cambiar prioridad", "Abrir la bandeja y seleccionar un ticket", "prioridad urgente alta baja ticket", "Acciones rápidas", "tickets:lista", "", "i-ticket", STAFF),
    ("estado-ticket", "Cambiar estado de ticket", "Abrir la bandeja y seleccionar un ticket", "estado resolver cerrar progreso ticket", "Acciones rápidas", "tickets:lista", "", "i-ticket", STAFF),
    ("ans-ticket", "Consultar ANS y vencimientos", "Abrir la bandeja y consultar los tiempos", "sla ans vencido plazo resolucion ticket", "Acciones rápidas", "tickets:lista", "", "i-clock", STAFF),
    ("crear-cuenta", "Crear usuario", "Abrir el formulario de cuenta", "crear cuenta acceso usuario", "Usuarios y permisos", "tickets:usuarios", "buscar-crear-cuenta", "i-user", ("admin",)),
    ("asignar-rol", "Asignar rol de usuario", "Abrir la gestión de cuentas", "cambiar rol editar usuario acceso", "Usuarios y permisos", "tickets:usuarios", "", "i-users", ("admin",)),
    ("asignar-permisos", "Gestionar permisos", "Abrir los permisos de la página", "dar permiso acceso autorizacion privilegios rol", "Usuarios y permisos", "accounts:ajustes", "pagina", "i-lock", ("admin",)),
    ("monitoreo-admin", "Monitoreo de zonas", "Consultar supervisores, cuentas y zonas", "seguimiento monitoreo supervisor punto zona", "Monitoreo", "tickets:monitoreo_admin", "", "i-eye", ("admin",)),
    ("tecnico-monitoreo", "Monitoreo de técnico", "Consultar seguimiento de solicitudes", "seguimiento monitoreo tickets", "Monitoreo", "tickets:tec_monitoreo", "", "i-eye", ("tecnico",)),
    ("tecnico-historial", "Historial de técnico", "Consultar historial de solicitudes", "historial tickets seguimiento", "Páginas y módulos", "tickets:tec_historial", "", "i-clock", ("tecnico",)),
    ("obs-panel", "Panel de observador", "Consultar seguimiento de zonas", "observador supervisor monitoreo", "Monitoreo", "tickets:obs_panel", "", "i-eye", ("observador",)),
    ("papelera-usuario", "Papelera de mis solicitudes", "Consultar solicitudes eliminadas", "papelera recuperar restaurar", "Páginas y módulos", "tickets:mi_papelera", "", "i-trash", ("usuario",)),
    ("papelera-staff", "Papelera de tickets", "Consultar tickets eliminados", "papelera recuperar restaurar", "Páginas y módulos", "tickets:papelera", "", "i-trash", ("admin",)),
    ("faq", "Preguntas frecuentes", "Consultar respuestas y ayuda", "ayuda soporte faq", "Páginas y módulos", "tickets:faq", "", "i-help", ALL),
    ("categorias-consulta", "Consultar categorías", "Ver el catálogo de categorías de soporte", "categoria subcategoria clasificacion problema", "Páginas y módulos", "tickets:categorias_publico", "", "i-folder", ("usuario", "observador")),
    ("manual", "Manual de usuario", "Abrir el manual de uso", "ayuda guia instrucciones tutorial", "Páginas y módulos", "accounts:ver_manual", "", "i-help", ALL),
    ("avisos", "Preferencias de avisos", "Elegir las notificaciones de la cuenta", "notificaciones alertas aviso correo preferencias configuracion", "Configuraciones", "accounts:ajustes", "notificaciones", "i-bell", ALL),
    ("crear-zona", "Crear zona de seguimiento", "Abrir el formulario de zona", "crear zona carpeta observador supervisor", "Monitoreo", "tickets:obs_zonas", "crear-zona", "i-folder", ("observador",)),
    ("mi-lista", "Gestionar mi lista", "Consultar cuentas y puntos supervisados", "agregar cuenta persona punto seguimiento", "Monitoreo", "tickets:obs_mi_lista", "", "i-users", ("observador",)),
    ("seguimiento-obs", "Solicitar seguimiento de ticket", "Abrir monitoreo y seleccionar una solicitud", "presionar seguimiento tecnico incidencia ticket", "Monitoreo", "tickets:obs_monitoreo", "", "i-eye", ("observador",)),
    ("seguimiento-usuario", "Solicitar seguimiento", "Abrir mis solicitudes y seleccionar un ticket", "presionar tecnico demora seguimiento ticket", "Acciones rápidas", "tickets:mi_panel", "", "i-ticket", ("usuario",)),
    ("responder-usuario", "Responder solicitud", "Abrir mis solicitudes y seleccionar un ticket", "responder mensaje comunicacion chat ticket", "Acciones rápidas", "tickets:mi_panel", "", "i-message", ("usuario",)),
    ("exportar-usuario", "Exportar mis tickets", "Abrir mi panel para exportar solicitudes", "excel descargar exportar solicitud reporte", "Acciones rápidas", "tickets:mi_panel", "", "i-download", ("usuario",)),
    ("sin-asignar", "Tickets sin asignar", "Consultar solicitudes sin técnico", "cola asignacion tecnico pendiente ticket", "Páginas y módulos", "tickets:sin_asignar", "", "i-ticket", ("admin",)),
    ("agenda", "Agenda y calendario", "Consultar eventos y disponibilidad", "programador agenda calendario evento disponibilidad", "Páginas y módulos", "programador:panel_programador", "", "i-calendar", STAFF),
    ("reporte-exportar", "Exportar reportes", "Abrir reportes para elegir una descarga", "descargar reporte excel exportacion", "Acciones rápidas", "tickets:reportes", "", "i-chart", ("admin",)),
    ("version-sistema", "Información del sistema", "Consultar información de la aplicación", "quienes somos informacion ayuda sistema", "Páginas y módulos", "tickets:quienes_somos", "", "i-info", ALL),
)


def _normalizar(value):
    return "".join(c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c))


def buscar_funciones(user, query, current_path=""):
    if not user.is_authenticated or not user.is_active or user.rol not in ALL:
        return []
    palabras = _normalizar(query).split()
    if not palabras:
        return []
    entries = list(REGISTRY)
    # Reutiliza el catálogo de accesos existente; descargas y acciones JS no
    # se ejecutan desde búsqueda y quedan fuera del índice automático.
    excluded = {"exportar-rep", "obs-exportar", "reportes", "usuarios"}
    for key, name, icon, route, roles in CATALOGO:
        if route and key not in excluded:
            entries.append(("atajo-" + key, name, "Abrir " + name.lower(), name, "Páginas y módulos", route, "", icon, roles))
    output = []
    for key, name, description, keywords, group, route, fragment, icon, roles in entries:
        if user.rol not in roles:
            continue
        if key == "atajo-crear" and not getattr(user, "puede_crear_tickets", True):
            continue
        target = reverse(route) + ("#" + fragment if fragment else "")
        haystack = _normalizar(" ".join((name, description, keywords, group)))
        tokens = haystack.split()
        if not all(word in haystack or (len(word) >= 5 and any(SequenceMatcher(None, word, token).ratio() >= .8 for token in tokens)) for word in palabras):
            continue
        normalized_name = _normalizar(name)
        score = 100 if _normalizar(query) == normalized_name else 70 if _normalizar(query) in normalized_name else 40
        if current_path and target.split("#", 1)[0] == current_path:
            score += 5
        output.append({"id": key, "nombre": name, "descripcion": description, "categoria": group, "modulo": route, "url": target, "icono": icon, "tipo": "navegacion", "prioridad": score})
    return sorted(output, key=lambda item: (-item["prioridad"], item["nombre"]))[:30]
