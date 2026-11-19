"""Resumen optativo de tickets propios; no modifica los tickets ni su ANS."""
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.tickets.models import Ticket

logger = logging.getLogger(__name__)
BOGOTA = ZoneInfo("America/Bogota")


def periodo_semanal(ahora):
    """Semana anterior completa, lunes a lunes, en hora colombiana."""
    local = timezone.localtime(ahora, BOGOTA)
    lunes = local.date() - timedelta(days=local.weekday())
    fin = datetime.combine(lunes, time.min, tzinfo=BOGOTA)
    return fin - timedelta(days=7), fin


def enviar_resumen(usuario_id, ahora):
    """Reserva un envío por semana; los fallos ambiguos requieren revisión manual."""
    inicio, fin = periodo_semanal(ahora)
    periodo = fin.date().isoformat()
    User = get_user_model()
    with transaction.atomic():
        usuario = User.objects.select_for_update().get(pk=usuario_id)
        prefs = dict(usuario.preferencias_notificaciones or {})
        registro = prefs.get("resumen_semanal_envio") or {}
        if not usuario.activo or not usuario.is_active or not usuario.email or prefs.get("correo_resumen") is not True:
            return "no_suscrito"
        if registro.get("periodo") == periodo:
            return "ya_procesado"
        prefs["resumen_semanal_envio"] = {"periodo": periodo, "estado": "reservado"}
        usuario.preferencias_notificaciones = prefs
        usuario.save(update_fields=["preferencias_notificaciones"])

    try:
        creados = Ticket.objects.filter(solicitante_email__iexact=usuario.email, fecha_creacion__gte=inicio, fecha_creacion__lt=fin).count()
        asignados = Ticket.objects.filter(tecnico_asignado_id=usuario.pk, fecha_creacion__gte=inicio, fecha_creacion__lt=fin).count()
        mensaje = (f"Hola, {usuario.nombre}.\n\nResumen del {inicio:%d/%m/%Y} al {(fin - timedelta(days=1)):%d/%m/%Y}:\n"
                   f"Tickets que solicitaste: {creados}.\n"
                   f"Tickets creados en ese periodo y actualmente asignados a ti: {asignados}.\n\n"
                   "Puedes cambiar esta preferencia en tu perfil de HelpDesk Dogger.")
        if send_mail("HelpDesk Dogger: resumen semanal", mensaje, settings.DEFAULT_FROM_EMAIL, [usuario.email], fail_silently=False) != 1:
            raise RuntimeError("El servidor no confirmó el envío")
    except Exception:
        logger.exception("No se pudo confirmar el resumen semanal del usuario %s", usuario.pk)
        estado = "revisar"
    else:
        estado = "enviado"
    with transaction.atomic():
        usuario = User.objects.select_for_update().get(pk=usuario_id)
        prefs = dict(usuario.preferencias_notificaciones or {})
        if prefs.get("resumen_semanal_envio") == {"periodo": periodo, "estado": "reservado"}:
            prefs["resumen_semanal_envio"] = {"periodo": periodo, "estado": estado}
            usuario.preferencias_notificaciones = prefs
            usuario.save(update_fields=["preferencias_notificaciones"])
    return estado
