"""Avisos de la campana de Dogger: altas, cierres, bienvenidas y recordatorios.

Todo se crea desde aquí para que el mismo aviso llegue por dos caminos:
la campana del encabezado (con icono y enlace) y el correo con diseño.
`clave` evita duplicados: si ya existe un aviso con esa clave para ese
usuario, no se vuelve a crear (así los recordatorios son uno por día).
"""

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from .models import Notificacion

ICONO_POR_TIPO = {
    Notificacion.Tipo.BIENVENIDA: "i-star",
    Notificacion.Tipo.TICKET_NUEVO: "i-inbox",
    Notificacion.Tipo.TICKET_CERRADO: "i-check-circle",
    Notificacion.Tipo.TICKET_RECORDATORIO: "i-clock",
    Notificacion.Tipo.EVENTO: "i-calendar",
    Notificacion.Tipo.SISTEMA: "i-bell",
}


# --------------------------------------------------------------------- base
def crear(usuario, tipo, titulo, mensaje, url="", icono="", clave=""):
    """Crea un aviso. Devuelve None si el usuario no existe o ya fue avisado."""
    if usuario is None or not getattr(usuario, "pk", None):
        return None
    if clave and Notificacion.objects.filter(usuario_id=usuario.pk, clave=clave).exists():
        return None
    return Notificacion.objects.create(
        usuario=usuario,
        tipo=tipo,
        titulo=(titulo or "")[:140],
        mensaje=(mensaje or "")[:300],
        url=url or "",
        icono=icono or ICONO_POR_TIPO.get(tipo, "i-bell"),
        clave=clave or "",
    )


def no_leidas(usuario):
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return 0
    return Notificacion.objects.filter(usuario_id=usuario.pk, leida=False).count()


def lista(usuario, limite=15):
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return []
    return list(
        Notificacion.objects.filter(usuario_id=usuario.pk).order_by("-creada_en", "-id")[:limite]
    )


def pendientes_de_emergente(usuario, limite=1):
    """Avisos que todavía no se han mostrado en la ventana emergente."""
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return []
    return list(
        Notificacion.objects.filter(usuario_id=usuario.pk, mostrada_en__isnull=True)
        .order_by("-creada_en", "-id")[:limite]
    )


# --------------------------------------------------------------- bienvenida
def bienvenida(usuario):
    """Primer ingreso: mensaje de bienvenida con icono de estrella."""
    return crear(
        usuario,
        Notificacion.Tipo.BIENVENIDA,
        f"¡Bienvenido a Dogger, {nombre_corto(usuario)}!",
        "Tu mesa de ayuda TI ya está lista. Reporta una incidencia y sigue su "
        "estado con el código HD.",
        url=reverse("tickets:mi_panel") if usuario.rol == "usuario" else reverse("tickets:dashboard"),
        clave=f"bienvenida:{usuario.pk}",
    )


def nombre_corto(usuario):
    partes = (getattr(usuario, "nombre", "") or "").split()
    return partes[0] if partes else (getattr(usuario, "email", "") or "").split("@")[0]


# ------------------------------------------------------------------- tickets
def _es_usuario_registrado(email):
    if not email:
        return None
    return get_user_model().objects.filter(email__iexact=email, activo=True).first()


def _url_ticket(ticket, usuario):
    if usuario is not None and usuario.rol == "usuario":
        return reverse("tickets:mi_ticket", args=[ticket.pk])
    return reverse("tickets:detalle", args=[ticket.pk])


def _personal_activo():
    User = get_user_model()
    return User.objects.filter(
        rol__in=[User.Rol.ADMIN, User.Rol.TECNICO], activo=True, is_active=True
    )


def ticket_creado(ticket):
    """Un ticket nuevo: avisa al técnico (o a la bandeja) y al solicitante."""
    creadas = []

    if ticket.tecnico_asignado_id:
        creadas.append(
            crear(
                ticket.tecnico_asignado,
                Notificacion.Tipo.TICKET_NUEVO,
                f"Nuevo ticket {ticket.codigo}",
                f"{ticket.prioridad.upper()} · {ticket.titulo[:80]}",
                url=_url_ticket(ticket, ticket.tecnico_asignado),
                clave=f"ticket:{ticket.pk}:nuevo:{ticket.tecnico_asignado_id}",
            )
        )
    else:
        for persona in _personal_activo():
            creadas.append(
                crear(
                    persona,
                    Notificacion.Tipo.TICKET_NUEVO,
                    f"Ticket sin asignar {ticket.codigo}",
                    f"{ticket.prioridad.upper()} · {ticket.titulo[:80]}",
                    url=_url_ticket(ticket, persona),
                    clave=f"ticket:{ticket.pk}:nuevo:{persona.pk}",
                )
            )

    solicitante = _es_usuario_registrado(ticket.solicitante_email)
    if solicitante is not None:
        creadas.append(
            crear(
                solicitante,
                Notificacion.Tipo.TICKET_NUEVO,
                f"Registramos tu ticket {ticket.codigo}",
                f"{ticket.get_estado_display()} · {ticket.titulo[:80]}",
                url=_url_ticket(ticket, solicitante),
                clave=f"ticket:{ticket.pk}:nuevo:{solicitante.pk}",
            )
        )
    return [n for n in creadas if n]


def ticket_cerrado(ticket, actor=None):
    """Ticket cerrado o resuelto: avisa a quien lo pidió y al técnico."""
    creadas = []
    solicitante = _es_usuario_registrado(ticket.solicitante_email)
    quien = f" por {nombre_corto(actor)}" if actor is not None else ""

    if solicitante is not None:
        creadas.append(
            crear(
                solicitante,
                Notificacion.Tipo.TICKET_CERRADO,
                f"Tu ticket {ticket.codigo} fue cerrado",
                f"{ticket.get_estado_display()}{quien} · {ticket.titulo[:70]}",
                url=_url_ticket(ticket, solicitante),
                clave=f"ticket:{ticket.pk}:cerrado:{solicitante.pk}",
            )
        )
    if ticket.tecnico_asignado_id:
        creadas.append(
            crear(
                ticket.tecnico_asignado,
                Notificacion.Tipo.TICKET_CERRADO,
                f"Cerraste {ticket.codigo}",
                f"{ticket.get_estado_display()}{quien} · {ticket.titulo[:70]}",
                url=_url_ticket(ticket, ticket.tecnico_asignado),
                clave=f"ticket:{ticket.pk}:cerrado:{ticket.tecnico_asignado_id}",
            )
        )
    return [n for n in creadas if n]


def ticket_editado(ticket, actor, detalle=""):
    """Cambio en un ticket: avisa al técnico y a quien lo pidió.

    Se llama cuando alguien edita la solicitud, responde o cambia su estado,
    para que el otro lado se entere sin tener que recargar la página.
    """
    creadas = []
    quien = nombre_corto(actor)
    texto = (detalle or "Se actualizó el ticket").strip()

    # Al técnico asignado, salvo que sea el mismo quien editó.
    if ticket.tecnico_asignado_id and ticket.tecnico_asignado_id != getattr(actor, "pk", None):
        creadas.append(
            crear(
                ticket.tecnico_asignado,
                Notificacion.Tipo.TICKET_EDITADO,
                f"{ticket.codigo} se actualizó por {quien}",
                f"{texto} · {ticket.titulo[:70]}",
                url=_url_ticket(ticket, ticket.tecnico_asignado),
                icono="i-pencil",
                # Con el minuto de reloj para que dos cambios seguidos
                # del mismo ticket no se pisen entre sí.
                clave=f"ticket:{ticket.pk}:editado:{ticket.tecnico_asignado_id}:{timezone.now():%Y%m%d%H%M}",
            )
        )

    # Al solicitante, si tiene cuenta y no fue él quien editó.
    solicitante = _es_usuario_registrado(ticket.solicitante_email)
    if solicitante is not None and solicitante.pk != getattr(actor, "pk", None):
        creadas.append(
            crear(
                solicitante,
                Notificacion.Tipo.TICKET_EDITADO,
                f"{ticket.codigo} tuvo novedades",
                f"{quien}: {texto} · {ticket.titulo[:70]}",
                url=_url_ticket(ticket, solicitante),
                icono="i-pencil",
                clave=f"ticket:{ticket.pk}:editado:{solicitante.pk}:{timezone.now():%Y%m%d%H%M}",
            )
        )

    # A los administradores: la mesa necesita enterarse del movimiento.
    for admin in _personal_activo():
        if admin.rol != "admin" or admin.pk == getattr(actor, "pk", None):
            continue
        if admin.pk in (ticket.tecnico_asignado_id, getattr(solicitante, "pk", None)):
            continue
        creadas.append(
            crear(
                admin,
                Notificacion.Tipo.TICKET_EDITADO,
                f"{ticket.codigo}: {texto}",
                f"{quien} · {ticket.titulo[:70]}",
                url=_url_ticket(ticket, admin),
                icono="i-pencil",
                clave=f"ticket:{ticket.pk}:editado:admin{admin.pk}:{timezone.now():%Y%m%d%H%M}",
            )
        )
    return [n for n in creadas if n]


# -------------------------------------------------------------- recordatorios
def sincronizar(usuario, clave, tipo, titulo, mensaje, url="", icono=""):
    """Deja un aviso de tipo recordatorio siempre con el dato actualizado.

    A diferencia de `crear`, que ignora los avisos repetidos por `clave`, aquí
    el aviso del día se refresca: si el número de tickets cambió porque se
    cerró o se asignó alguno, el título y el mensaje se corrigen en el sitio.
    Si el dato ya no aplica (por ejemplo, no queda ningún ticket pendiente) el
    aviso se borra, para que la campana no announce algo que ya no es cierto.
    """
    if usuario is None or not getattr(usuario, "pk", None):
        return None
    existentes = list(
        Notificacion.objects.filter(usuario_id=usuario.pk, clave=clave)
    )
    if not titulo:
        # El aviso se retira; no se devuelve porque no hay nada nuevo que ver.
        Notificacion.objects.filter(
            pk__in=[n.pk for n in existentes]
        ).delete()
        return None
    titulo = titulo[:140]
    mensaje = (mensaje or "")[:300]
    url = url or ""
    icono = icono or ICONO_POR_TIPO.get(tipo, "i-bell")
    if existentes:
        aviso = existentes[0]
        # Los avisos duplicados de días anteriores se limpian.
        Notificacion.objects.filter(
            pk__in=[n.pk for n in existentes[1:]]
        ).delete()
        if (
            aviso.titulo != titulo
            or aviso.mensaje != mensaje
            or aviso.url != url
        ):
            aviso.titulo = titulo
            aviso.mensaje = mensaje
            aviso.url = url
            aviso.icono = icono
            aviso.leida = False
            aviso.save(
                update_fields=[
                    "titulo", "mensaje", "url", "icono", "leida",
                ]
            )
            return aviso
        # Sin cambios: no se reporta como aviso nuevo, solo se conserva.
        return None
    return crear(
        usuario, tipo, titulo, mensaje, url=url, icono=icono, clave=clave
    )


def recordatorios(usuario, forzar=False):
    """Recordatorios del día: tickets pendientes y tareas o eventos próximos.

    Los avisos se crean una vez por día y por usuario (la `clave` lo evita),
    pero en cada visita se refrescan con el número real de tickets, de modo que
    si se cierra o se asigna alguno el contador de la campana no se queda
    desactualizado. Si el total llega a cero, el aviso desaparece.
    """
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return []
    hoy = timezone.localdate().isoformat()
    User = get_user_model()
    nuevas = []

    if getattr(usuario, "es_staff_helpdesk", False):
        from apps.tickets.models import Ticket

        abiertos = [Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO]
        asignados = Ticket.objects.filter(
            tecnico_asignado_id=usuario.pk, estado__in=abiertos
        ).count()
        nuevas.append(
            sincronizar(
                usuario,
                f"rec:asignados:{hoy}",
                Notificacion.Tipo.TICKET_RECORDATORIO,
                f"Tienes {asignados} ticket{'s' if asignados > 1 else ''} activo"
                f"{'s' if asignados > 1 else ''}" if asignados else "",
                "Revisa el estado de tus solicitudes asignadas."
                if asignados
                else "",
                url=reverse("tickets:panel_tecnico"),
            )
        )

        sin_asignar = Ticket.objects.filter(
            estado__in=abiertos, tecnico_asignado__isnull=True
        ).count()
        nuevas.append(
            sincronizar(
                usuario,
                f"rec:sin-asignar:{hoy}",
                Notificacion.Tipo.TICKET_RECORDATORIO,
                f"{sin_asignar} ticket{'s' if sin_asignar > 1 else ''} pendiente"
                f"{'s' if sin_asignar > 1 else ''} de asignar" if sin_asignar else "",
                "Hay solicitudes en la bandeja esperando un técnico."
                if sin_asignar
                else "",
                url=reverse("tickets:sin_asignar"),
            )
        )

        urgentes = Ticket.objects.filter(
            estado__in=abiertos,
            prioridad__in=["urgente", "alta"],
        ).count()
        nuevas.append(
            sincronizar(
                usuario,
                f"rec:urgentes:{hoy}",
                Notificacion.Tipo.TICKET_RECORDATORIO,
                f"{urgentes} ticket{'s' if urgentes > 1 else ''} de prioridad alta u urgente"
                if urgentes
                else "",
                "Atiende primero los casos con mayor impacto."
                if urgentes
                else "",
                url=reverse("tickets:sin_asignar"),
            )
        )
    elif usuario.rol == User.Rol.USUARIO:
        from apps.tickets.models import Ticket

        mios = Ticket.objects.filter(
            solicitante_email__iexact=usuario.email,
            estado__in=[Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO],
        ).count()
        nuevas.append(
            sincronizar(
                usuario,
                f"rec:mios:{hoy}",
                Notificacion.Tipo.TICKET_RECORDATORIO,
                f"Tienes {mios} ticket{'s' if mios > 1 else ''} en curso"
                if mios
                else "",
                "Sigue el avance de tus solicitudes abiertas."
                if mios
                else "",
                url=reverse("tickets:mi_panel"),
            )
        )

    nuevas.extend(_recordatorio_eventos(usuario, hoy))
    return [n for n in nuevas if n]


def _recordatorio_eventos(usuario, hoy):
    """Tareas y eventos de calendario asignados para hoy o mañana.

    Se sincroniza también con los ya avisados: una tarea completada o que ya no
    está en la ventana de fechas desaparece de la campana.
    """
    try:
        from datetime import timedelta

        from apps.programador.models import CalendarioEvento
    except Exception:
        return []

    hoy_date = timezone.localdate()
    manana = hoy_date + timedelta(days=1)
    eventos = list(
        CalendarioEvento.objects.filter(
            tecnico_id=usuario.pk,
            completado=False,
            fecha__lte=manana,
            fecha__gte=hoy_date - timedelta(days=7),
        ).order_by("fecha", "hora")[:3]
    )

    nuevas = []
    for evento in eventos:
        when = "hoy" if evento.fecha == hoy_date else evento.fecha.strftime("%d/%m")
        nuevas.append(
            sincronizar(
                usuario,
                f"evento:{evento.pk}:{evento.fecha.isoformat()}",
                Notificacion.Tipo.EVENTO,
                f"{evento.get_tipo_display()}: {evento.titulo}",
                f"Programado para {when}"
                + (f" a las {evento.hora.strftime('%H:%M')}" if evento.hora else ""),
                url=reverse("programador:panel_programador"),
            )
        )

    # Los avisos de evento de hoy que ya no aplican (completados o vencidos)
    # se retiran para no dejar tareas fantasma en la campana.
    claves = {f"evento:{e.pk}:{e.fecha.isoformat()}" for e in eventos}
    Notificacion.objects.filter(
        usuario_id=usuario.pk,
        tipo=Notificacion.Tipo.EVENTO,
        clave__startswith="evento:",
    ).exclude(clave__in=claves).filter(clave__endswith=f":{hoy}").delete()

    return nuevas
