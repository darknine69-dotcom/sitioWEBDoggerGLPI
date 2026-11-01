"""Cola persistente optativa para correo y seguimientos de GLPI.

Una tarea reservada que pierde su worker no se reenvía automáticamente: el
servidor externo pudo haberla recibido. Debe revisarse antes de reintentarse.
"""
import json
import logging
from datetime import timedelta

from django.core.mail import send_mail
from django.db.models import F
from django.utils import timezone

from apps.tickets.models import TareaDiferida, Ticket
from apps.tickets.services.glpi_client import sync_followup_to_glpi

logger = logging.getLogger(__name__)


def encolar(func, args, kwargs, *, reset_token_id=None):
    """Persistir solo tareas admitidas, con los datos cifrados en reposo."""
    if func is send_mail:
        if len(args) != 4:
            raise ValueError("Firma de correo no compatible con la cola")
        payload = {"asunto": args[0], "texto": args[1], "remitente": args[2],
                   "destinatarios": args[3], "html": kwargs.get("html_message")}
        if reset_token_id is not None:
            payload["reset_token_id"] = reset_token_id
        tipo = "correo"
    elif func is sync_followup_to_glpi:
        if len(args) != 2 or not isinstance(args[0], Ticket) or not args[0].pk:
            raise ValueError("Seguimiento GLPI no compatible con la cola")
        payload = {"ticket_id": args[0].pk, "texto": args[1]}
        tipo = "glpi_seguimiento"
    else:
        raise ValueError("La función no está autorizada para ejecutarse en la cola")
    return TareaDiferida.objects.create(tipo=tipo, datos=json.dumps(payload, ensure_ascii=False))


def procesar_una():
    """Reserva atómicamente un trabajo; devuelve su id o None si no hay."""
    while True:
        pk = (TareaDiferida.objects.filter(estado=TareaDiferida.Estado.PENDIENTE,
                                         disponible_en__lte=timezone.now())
              .order_by("disponible_en", "pk").values_list("pk", flat=True).first())
        if pk is None:
            return None
        ahora = timezone.now()
        reservado = TareaDiferida.objects.filter(pk=pk, estado=TareaDiferida.Estado.PENDIENTE).update(
            estado=TareaDiferida.Estado.PROCESANDO, reservado_en=ahora,
            actualizado_en=ahora, intentos=F("intentos") + 1,
        )
        if reservado:
            break
    tarea = TareaDiferida.objects.get(pk=pk)
    try:
        datos = json.loads(tarea.datos)
        if tarea.tipo == "correo":
            if "reset_token_id" in datos:
                from apps.accounts.models import ResetPasswordToken

                token = ResetPasswordToken.objects.select_related("usuario").filter(
                    pk=datos["reset_token_id"], usado=False,
                    usuario__activo=True, usuario__is_active=True,
                ).first()
                destinatarios = datos["destinatarios"]
                if (token is None or token.expirado or len(destinatarios) != 1
                        or destinatarios[0].casefold() != token.usuario.email.casefold()):
                    tarea.estado = TareaDiferida.Estado.FALLIDA
                    tarea.ultimo_error = "Código de recuperación no vigente"
                    tarea.datos = ""
                    tarea.save(update_fields=["estado", "ultimo_error", "datos", "actualizado_en"])
                    return pk
            cantidad = send_mail(datos["asunto"], datos["texto"], datos["remitente"],
                                 datos["destinatarios"], html_message=datos.get("html"),
                                 fail_silently=False)
            if cantidad != 1:
                raise RuntimeError("El backend no confirmó el envío")
        elif tarea.tipo == "glpi_seguimiento":
            ticket = Ticket.objects.get(pk=datos["ticket_id"])
            if not sync_followup_to_glpi(ticket, datos["texto"]):
                raise RuntimeError("GLPI no confirmó el seguimiento")
        else:
            raise ValueError("Tipo de tarea desconocido")
    except Exception as exc:
        # Una excepción de red no prueba que el destino no haya recibido el
        # mensaje. Requiere reconciliación antes de cualquier reintento.
        tarea.estado = TareaDiferida.Estado.REVISAR
        tarea.ultimo_error = type(exc).__name__[:120]
        tarea.save(update_fields=["estado", "ultimo_error", "actualizado_en"])
        logger.error("Tarea diferida %s requiere revisión (%s)", pk, type(exc).__name__)
    else:
        tarea.estado = TareaDiferida.Estado.COMPLETADA
        tarea.datos = ""  # Eliminar del registro códigos y contenido ya entregado.
        tarea.ultimo_error = ""
        tarea.save(update_fields=["estado", "datos", "ultimo_error", "actualizado_en"])
    return pk


def tareas_estancadas(minutos=10):
    """Solo identifica tareas reservadas: no presupone si fueron entregadas."""
    limite = timezone.now() - timedelta(minutes=minutos)
    return TareaDiferida.objects.filter(estado=TareaDiferida.Estado.PROCESANDO, reservado_en__lt=limite)
