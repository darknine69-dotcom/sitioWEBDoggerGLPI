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


def _enviar(asunto, mensaje, destinatarios):
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
            fail_silently=True,
        )
    except Exception as exc:
        logger.error("Error enviando correo '%s': %s", asunto, exc)


def notificar_ticket_creado(ticket):
    asunto = _asunto(ticket, "Ticket creado")
    mensaje = _mensaje(ticket, "Se ha creado un nuevo ticket")
    destinatarios = _destinatarios(ticket, incluir_solicitante=False)
    _enviar(asunto, mensaje, destinatarios)


def notificar_ticket_actualizado(ticket, accion, detalle=""):
    asunto = _asunto(ticket, f"Ticket {accion}")
    mensaje = _mensaje(ticket, accion, detalle)
    destinatarios = _destinatarios(ticket)
    _enviar(asunto, mensaje, destinatarios)


def notificar_comentario(ticket, autor, comentario, es_interno=False):
    if es_interno:
        return
    asunto = _asunto(ticket, "Nuevo comentario")
    mensaje = _mensaje(ticket, f"{autor or 'Anonimo'} comento", comentario)
    destinatarios = _destinatarios(ticket)
    _enviar(asunto, mensaje, destinatarios)
