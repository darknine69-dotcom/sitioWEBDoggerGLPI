"""Datos de la campana de notificaciones para todas las vistas.

Se inyectan tres variables:
- `notif_no_leidas`: número del contador rojo de la campana.
- `notif_lista`: últimos avisos para la lista desplegable.
- `notif_emergente`: aviso que todavía no se mostró y debe saltar como
  ventana emergente.

Los recordatorios (tickets pendientes, tareas o eventos) se sincronizan en
cada visita para que el número siempre sea el real.
"""

from . import services


def notificaciones(request):
    usuario = getattr(request, "user", None)
    vacio = {
        "notif_no_leidas": 0,
        "notif_lista": [],
        "notif_emergente": None,
    }
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return vacio

    try:
        _generar_recordatorios(request, usuario)
        # La ventana emergente se arma primero: es este mismo aviso, el que
        # saltara y quedara marcado como visto al entrar a la pagina.
        emergente = services.pendientes_de_emergente(usuario, limite=1)
        # Entrar a una pantalla es revisarla: sus avisos dejan de contar y el
        # morrito del menu baja a cero hasta que pase algo nuevo.
        _revisar_la_vista(request, usuario)
        return {
            "notif_no_leidas": services.no_leidas(usuario),
            "notif_lista": services.lista(usuario),
            "notif_emergente": emergente[0] if emergente else None,
        }
    except Exception:
        # Si la tabla aún no existe (antes de migrar) el sitio sigue igual.
        return vacio


def _generar_recordatorios(request, usuario):
    """Refresca los recordatorios en cada visita GET.

    No se filtra por fecha a propósito: `services.recordatorios` sincroniza el
    número real de tickets y borra el aviso cuando ya no aplica, así que el
    contador de la campana queda al día aunque se cierren o asignen tickets
    durante el día. Es un lectura ligera (dos o tres COUNT) por página.
    """
    if request.method != "GET":
        return
    if getattr(request, "headers", {}).get("x-requested-with") == "XMLHttpRequest":
        return
    services.recordatorios(usuario)


def _revisar_la_vista(request, usuario):
    """Marca como revisados los avisos de la vista que se está abriendo."""
    if request.method != "GET":
        return
    if getattr(request, "headers", {}).get("x-requested-with") == "XMLHttpRequest":
        return
    match = getattr(request, "resolver_match", None)
    if match is None:
        return
    services.revisar_la_vista(usuario, match.url_name, url_actual=request.get_full_path())
