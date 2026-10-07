from django.conf import settings

# Estados en los que un ticket todavía requiere atención de alguien.
ESTADOS_ACTIVOS = ("abierto", "en-progreso")


def _tipos_por_revisar(rol):
    """Avisos que cuentan en el morrito del menú para cada rol.

    Al usuario no le cuenta como "por revisar" el aviso de confirmación de su
    propia solicitud (el que aparece al crearla): lo que le interesa es lo que
    le llega del personal o lo que tiene pendiente de mirar.
    """
    from apps.notificaciones.models import Notificacion

    if rol == "usuario":
        return (
            Notificacion.Tipo.BIENVENIDA,
            Notificacion.Tipo.TICKET_CERRADO,
            Notificacion.Tipo.TICKET_EDITADO,
            Notificacion.Tipo.EVENTO,
            Notificacion.Tipo.TICKET_RECORDATORIO,
        )
    return tuple(Notificacion.Tipo.values)


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
            "panel_mostrar_actividad_glpi": cfg.panel_mostrar_actividad_glpi,
        })
    except Exception:
        # Si la tabla aún no existe (antes de migrar), se mantiene lo de settings.
        pass
    return {
        "DOGGER": d,
        **_contador_papelera(request),
        **_contador_mi_papelera(request),
        **_contador_sin_asignar(request),
        **_contadores_menu(request),
    }


def _contador_mi_papelera(request):
    """Cuántas solicitudes canceladas tiene el usuario en su propia papelera.

    Solo para el rol usuario: el staff usa la papelera general, que ya tiene
    su contador en el menú de administración.
    """
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return {"mi_papelera_total": 0}
    if getattr(usuario, "rol", None) != "usuario" or not getattr(usuario, "activo", False):
        return {"mi_papelera_total": 0}
    match = getattr(request, "resolver_match", None)
    if match is not None and match.url_name == "mi_papelera":
        return {}
    try:
        from apps.tickets.models import Ticket

        total = Ticket.en_papelera().filter(solicitante_email=usuario.email).count()
    except Exception:
        # Antes de aplicar la migración la columna no existe.
        return {"mi_papelera_total": 0}
    return {"mi_papelera_total": total}


def _contadores_menu(request):
    """Conteos de lo que falta por revisar, uno por entrada del menú.

    Ya no son cuentas cerradas de la base de datos sino de lo que cada persona
    tiene *sin mirar*: cuando ocurre un evento (un ticket nuevo, una respuesta,
    una edición) el morrito aparece y en cuanto se entra a esa pantalla se
    limpia. Así el número nunca queda congelado ni mintiendo.
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
    if rol == "observador":
        # El observador no tiene campana de avisos: se queda con la cuenta real
        # de los tickets de sus puntos.
        try:
            from apps.tickets.models import Ticket

            base = _tickets_de_puntos_del_observador(usuario, dict(estado__in=ESTADOS_ACTIVOS))
            return {
                "menu_total": base.count(),
                "menu_mios": ElementoMiLista.objects.filter(observador=usuario).count(),
                "menu_urgentes": base.filter(prioridad=Ticket.Prioridad.URGENTE).count(),
                "menu_respondidos": 0,
            }
        except Exception:
            return vacio

    try:
        from apps.notificaciones import services as avisos
        from apps.notificaciones.models import Notificacion

        tipos = _tipos_por_revisar(rol)
        sin_asignar = _sin_revisar_sin_asignar(usuario)
        total = avisos.sin_revisar(usuario, tipos=tipos)
        urgentes = avisos.sin_revisar(usuario, tipos=tipos, clave_prefijo="rec:urgentes")

        respondidos = 0
        if rol == "usuario":
            # Lo que el personal ya le respondió y sigue sin abrir.
            respondidos = Notificacion.objects.filter(
                usuario=usuario,
                leida=False,
                tipo__in=[Notificacion.Tipo.TICKET_CERRADO, Notificacion.Tipo.TICKET_EDITADO],
            ).count()
        elif rol == "admin":
            respondidos = Notificacion.objects.filter(
                usuario=usuario,
                leida=False,
                tipo=Notificacion.Tipo.TICKET_NUEVO,
            ).count()

        if rol == "tecnico":
            mios = sin_asignar
        elif rol == "admin":
            mios = sin_asignar
        else:
            mios = total

        return {
            "menu_total": total,
            "menu_mios": mios,
            "menu_urgentes": urgentes,
            "menu_respondidos": respondidos,
        }
    except Exception:
        # Antes de migrar, o si la tabla aun no existe, el menú va sin conteos.
        return vacio


def _sin_revisar_sin_asignar(usuario):
    """Avisos sin revisar que apuntan a la bandeja de "sin asignar".

    Cuenta los del recordatorio diario y los de los tickets que entraron sin
    técnico: ambas cosas se aclaran al abrir la bandeja.
    """
    from django.db.models import Q

    from apps.notificaciones import services as avisos
    from apps.notificaciones.models import Notificacion

    return Notificacion.objects.filter(
        usuario_id=usuario.pk,
        leida=False,
        tipo__in=list(_tipos_por_revisar(getattr(usuario, "rol", None))),
    ).filter(
        Q(url=_url_sin_asignar()) | Q(clave__startswith="rec:sin-asignar")
    ).count()


def _url_sin_asignar():
    from django.urls import reverse

    return reverse("tickets:sin_asignar")


def _tickets_de_puntos_del_observador(usuario, activos_extra):
    """Tickets de los puntos asignados al observador (o ninguno si no tiene)."""
    from apps.tickets.models import ObservadorPunto, Ticket

    puntos = list(
        ObservadorPunto.objects.filter(observador=usuario).values_list(
            "punto__nombre", flat=True
        )
    )
    if not puntos:
        return Ticket.objects.none()
    return Ticket.objects.filter(solicitante_punto__in=puntos, **activos_extra)


def _contador_sin_asignar(request):
    """Solicitudes sin técnico que el personal todavía no ha revisado."""
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return {"sin_asignar_total": 0}
    if not getattr(usuario, "es_staff_helpdesk", False):
        return {"sin_asignar_total": 0}
    match = getattr(request, "resolver_match", None)
    if match is not None and match.url_name == "sin_asignar":
        return {}
    try:
        total = _sin_revisar_sin_asignar(usuario)
    except Exception:
        return {"sin_asignar_total": 0}
    return {"sin_asignar_total": max(total, 0)}


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



def calificacion_lateral(request):
    """Calificación del técnico para el pie del menú lateral.

    Solo técnicos: dos conteos por página. Si la tabla aún no existe
    (antes de migrar), no se muestra nada.
    """
    vacio = {"calif_lateral": None}
    usuario = getattr(request, "user", None)
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return vacio
    if getattr(usuario, "rol", None) != "tecnico":
        return vacio
    try:
        from apps.tickets.views import _calificacion_de

        return {"calif_lateral": _calificacion_de(usuario)}
    except Exception:
        return vacio
