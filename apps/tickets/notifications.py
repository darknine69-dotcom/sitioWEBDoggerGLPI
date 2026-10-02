"""Avisos de Dogger cuando cambia un ticket.

Aquí conviven dos caminos:
- Correo: al técnico (o a la bandeja) y al usuario que reportó, siempre con
  diseño HTML y su alternativa en texto plano.
- Campana de notificaciones: aviso en la app con icono y enlace al ticket.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def _asunto(ticket, accion):
    return f"[Dogger HelpDesk] {accion} — {ticket.codigo}"


def _mensaje(ticket, accion, detalle=""):
    lineas = [
        f"Ticket: {ticket.codigo}",
        f"Titulo: {ticket.titulo}",
        f"Estado: {ticket.get_estado_display()}",
        f"Prioridad: {ticket.get_prioridad_display()}",
        f"Solicitante: {ticket.solicitante_nombre} <{ticket.solicitante_email}>",
        "",
        f"Accion: {accion}",
    ]
    if detalle:
        lineas.append(f"Detalle: {detalle}")
    return "\n".join(lineas)


def _destinatarios(ticket, incluir_solicitante=True, incluir_tecnico=True):
    destinatarios = []
    if incluir_solicitante and ticket.solicitante_email:
        destinatarios.append(ticket.solicitante_email)
    if incluir_tecnico and ticket.tecnico_asignado and ticket.tecnico_asignado.email:
        destinatarios.append(ticket.tecnico_asignado.email)
    return list(set(destinatarios))


def _enviar(asunto, mensaje, destinatarios, html=""):
    if not destinatarios:
        return
    if not settings.EMAIL_HOST_USER:
        logger.warning("SMTP no configurado (EMAIL_USER vacio). Correo no enviado: %s", asunto)
        return
    try:
        send_mail(
            asunto,
            mensaje,
            settings.DEFAULT_FROM_EMAIL,
            destinatarios,
            html_message=html or None,
            fail_silently=True,
        )
    except Exception as exc:
        logger.error("Error enviando correo '%s': %s", asunto, exc)


def _notificar_app(fn, *args, **kwargs):
    """Crea el aviso en la campana sin romper la operación si algo falla."""
    try:
        from apps.notificaciones import services

        return fn(*args, **kwargs)
    except Exception as exc:
        logger.warning("No se pudo crear la notificación: %s", exc)
        return []


def notificar_ticket_creado(ticket):
    """Ticket nuevo: correo al técnico (o a la bandeja) y al solicitante."""
    _notificar_app(_nuevo_tecnico, ticket)
    _notificar_app(_nuevo_usuario, ticket)


def _nuevo_tecnico(ticket):
    from django.contrib.auth import get_user_model

    from apps.notificaciones import emails, services

    servicios = services.ticket_creado(ticket)
    if ticket.tecnico_asignado_id:
        emails.correo_ticket_tecnico(ticket, ticket.tecnico_asignado)
    else:
        User = get_user_model()
        personal = User.objects.filter(
            rol__in=[User.Rol.ADMIN, User.Rol.TECNICO], activo=True, is_active=True
        )
        emails.correo_ticket_bandeja(ticket, list(personal))
    return servicios


def _nuevo_usuario(ticket):
    from apps.notificaciones import emails

    return emails.correo_ticket_usuario(ticket)


def notificar_ticket_actualizado(ticket, accion, detalle="", actor=None):
    """Cambio de estado o cierre: correo y aviso para quien corresponde."""
    cerrado = ticket.estado in (ticket.Estado.RESUELTO, ticket.Estado.CERRADO)
    if cerrado or "cerr" in (accion or "").lower() or "resuelt" in (accion or "").lower():
        _notificar_app(_cerrado, ticket, actor)
        return
    # Cualquier otro cambio tambien deja aviso en la campana, para que el
    # otro lado lo vea sin recargar la pagina.
    _notificar_app(_editado, ticket, actor, detalle or accion)
    _enviar(_asunto(ticket, f"Ticket {accion}"), _mensaje(ticket, accion, detalle), _destinatarios(ticket))


def _cerrado(ticket, actor=None):
    from apps.notificaciones import emails, services

    avisos = services.ticket_cerrado(ticket, actor)
    emails.correo_ticket_cerrado(ticket)
    return avisos


def _editado(ticket, actor=None, detalle=""):
    from apps.notificaciones import services

    return services.ticket_editado(ticket, actor, detalle)


def notificar_comentario(ticket, autor, comentario, es_interno=False, actor=None):
    """Respuesta en el hilo del ticket.

    Las notas internas son solo para el equipo, asi que no avisan al
    solicitante. El resto genera aviso en la campana para el otro lado.
    """
    if es_interno:
        return
    quien = getattr(actor, "nombre", None) or autor
    _notificar_app(_editado, ticket, actor, f"Respondio: {(comentario or '')[:90]}")
    _enviar(_asunto(ticket, "Nuevo comentario"), _mensaje(ticket, f"{quien or 'Anonimo'} comento", comentario), _destinatarios(ticket))
