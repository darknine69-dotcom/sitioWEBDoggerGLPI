from django.conf import settings

# Estados en los que un ticket todavía requiere atención de alguien.
ESTADOS_ACTIVOS = ("abierto", "en-progreso")


def dogger_config(request):
    """Expone settings.DOGGER combinado con la configuración de la página
    editable desde el panel (apps.tickets.models.ConfigSitio).

    Los valores gestionados en la pestaña "Página" de Ajustes tienen
    prioridad sobre los valores por defecto de settings.py / variables de
    entorno.
    """
    d = dict(settings.DOGGER)
    try:
        from apps.tickets.models import ConfigSitio

        cfg = ConfigSitio.cargar()
        d.update({
            "pagina_mostrar_redes": cfg.pagina_mostrar_redes,
            "correo_activo": cfg.correo_activo,
            "correo_soporte": cfg.correo_soporte,
            "whatsapp_activo": cfg.whatsapp_activo,
            "whatsapp_soporte": cfg.whatsapp_numero,
            "tiktok_activo": cfg.tiktok_activo,
            "tiktok": cfg.tiktok_url,
            "instagram_activo": cfg.instagram_activo,
            "instagram": cfg.instagram_url,
            "facebook_activo": cfg.facebook_activo,
            "facebook": cfg.facebook_url,
        })
    except Exception:
        # Si la tabla aún no existe (antes de migrar), se mantiene lo de settings.
        pass
    return {
        "DOGGER": d,
        **_contador_papelera(request),
        **_contador_sin_asignar(request),
        **_contadores_menu(request),
    }


def _contadores_menu(request):
    """Conteos de lo que falta por revisar, uno por entrada del menú.

    Cada rol ve lo que le corresponde: el técnico cuenta sus tickets
    asignados, el administrador los abiertos de toda la mesa más los
    urgentes, y el usuario los suyos propios. El contexto se completa con
    ceros para que la plantilla pueda preguntar siempre por la misma clave.
    """
    vacio = {
        "menu_total": 0,
        "menu_mios": 0,
        "menu_urgentes": 0,
        "menu_respondidos": 0,
    }
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return vacio

    rol = getattr(usuario, "rol", None)
    try:
        from apps.tickets.models import Ticket

        activos = dict(estado__in=ESTADOS_ACTIVOS)
        urgente = Ticket.Prioridad.URGENTE

        if rol == "tecnico":
            base = Ticket.objects.filter(tecnico_asignado=usuario, **activos)
            mios = base
            total = base
        elif rol == "admin":
            base = Ticket.objects.filter(**activos)
            mios = base.filter(tecnico_asignado__isnull=True)
            total = base
        else:
            # El usuario solo ve lo suyo: lo que tiene abierto y lo que ya le
            # respondieron (resuelto o cerrado) y todavia no ha revisado.
            base = Ticket.objects.filter(solicitante_email=usuario.email, **activos)
            mios = base
            total = base

        respondidos = 0
        if rol != "tecnico":
            respondidos = Ticket.objects.filter(
                solicitante_email=usuario.email,
                estado__in=[Ticket.Estado.RESUELTO, Ticket.Estado.CERRADO],
            ).count()

        return {
            "menu_total": total.count(),
            "menu_mios": mios.count(),
            "menu_urgentes": base.filter(prioridad=urgente).count(),
            "menu_respondidos": respondidos,
        }
    except Exception:
        # Antes de migrar, o si la tabla aun no existe, el menú va sin conteos.
        return vacio


def _contador_sin_asignar(request):
    """Tickets abiertos sin técnico, para el contador de la navbar del personal."""
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return {"sin_asignar_total": 0}
    if not getattr(usuario, "es_staff_helpdesk", False):
        return {"sin_asignar_total": 0}
    match = getattr(request, "resolver_match", None)
    if match is not None and match.url_name == "sin_asignar":
        return {}
    try:
        from apps.tickets.models import Ticket

        total = (
            Ticket.objects.filter(
                estado__in=[Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO],
                tecnico_asignado__isnull=True,
            ).count()
        )
    except Exception:
        return {"sin_asignar_total": 0}
    return {"sin_asignar_total": total}


def _contador_papelera(request):
    """Tickets en la papelera, para el contador de la navbar (solo admins).

    Va en un context processor, pero se omite en la propia página de la
    papelera, que ya trae el total en su contexto (ahí se cuenta aparte).
    """
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return {"papelera_total": 0}
    if getattr(usuario, "rol", None) != "admin" or not getattr(usuario, "activo", False):
        return {"papelera_total": 0}
    match = getattr(request, "resolver_match", None)
    if match is not None and match.url_name == "papelera":
        return {}
    try:
        from apps.tickets.models import Ticket

        total = Ticket.en_papelera().count()
    except Exception:
        # Antes de aplicar la migración la columna no existe.
        return {"papelera_total": 0}
    return {"papelera_total": total}
