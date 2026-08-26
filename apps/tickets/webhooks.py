import json
import logging

from django.conf import settings
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import GlpiEvento, Ticket, TicketComentario
from .services.glpi_client import GLPI_STATUS_TO_STATE, GLPI_STATUS_NAMES

logger = logging.getLogger(__name__)


def _find_first_value(data, *keys):
    if not isinstance(data, (dict, list)):
        return None
    if isinstance(data, dict):
        for key in keys:
            if key in data and data.get(key) not in (None, "", "unknown"):
                return data.get(key)
        for value in data.values():
            found = _find_first_value(value, *keys)
            if found is not None:
                return found
    else:
        for item in data:
            found = _find_first_value(item, *keys)
            if found is not None:
                return found
    return None


def _extract_ticket_id(data):
    value = _find_first_value(
        data,
        "glpi_id",
        "glpi_ticket_id",
        "ticket_id",
        "tickets_id",
        "items_id",
        "item_id",
        "id",
    )
    if value in (None, "", "unknown"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_status_id(data):
    value = _find_first_value(
        data,
        "status_id",
        "status",
        "new_status",
        "new_status_id",
        "state",
        "state_id",
    )
    if value in (None, "", "unknown"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_followup_content(data):
    value = _find_first_value(
        data,
        "solution",
        "solution_text",
        "content",
        "message",
        "followup",
        "comment",
        "text",
    )
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("text", "content", "message", "solution", "comment"):
            inner = value.get(key)
            if isinstance(inner, str) and inner.strip():
                return inner.strip()
    if isinstance(value, list):
        joined = []
        for item in value:
            if isinstance(item, str) and item.strip():
                joined.append(item.strip())
        if joined:
            return "\n".join(joined)
    return str(value).strip()


def _normalize_event_name(data):
    value = data.get("event") if isinstance(data, dict) else ""
    event = str(value or "").strip().lower()
    if not event:
        event = str(data.get("action") or "").strip().lower() if isinstance(data, dict) else ""
    if not event:
        if "status" in str(data).lower() or _extract_status_id(data) is not None:
            return "ticket_update"
        if _extract_followup_content(data):
            return "followup_created"
        return ""
    return event


@csrf_exempt
@require_POST
def glpi_webhook(request):
    """
    Receptor de eventos GLPI (webhooks nativos de GLPI 11).
    Espera el header X-Dogger-Secret coincidiendo con GLPI_WEBHOOK_SECRET.
    Si no hay secret configurado, acepta peticiones locales para pruebas.
    """
    secret_esperado = getattr(settings, "GLPI_WEBHOOK_SECRET", "").strip()
    secret_recibido = request.headers.get("X-Dogger-Secret", "").strip()
    if secret_esperado and secret_recibido != secret_esperado:
        logger.warning("Webhook GLPI rechazado: secret inválido")
        return HttpResponseForbidden("Secret inválido")

    try:
        data = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "JSON inválido"}, status=400)

    evento = _normalize_event_name(data)
    status_id = _extract_status_id(data)
    contenido = _extract_followup_content(data).strip()

    handled = False

    if evento in {"ticket_update", "ticket_updated", "ticket_status_updated", "update", "updated"} or (
        status_id is not None and evento not in {"followup_created", "followup", "new_followup", "ticket_followup", "solution_approved", "ticket_solved"}
    ):
        glpi_id = _extract_ticket_id(data)
        ticket = None
        if glpi_id is not None:
            try:
                ticket = Ticket.objects.get(glpi_id=glpi_id)
            except Ticket.DoesNotExist:
                ticket = None

        if ticket is None:
            GlpiEvento.objects.create(
                tipo=GlpiEvento.Tipo.OTRO,
                descripcion=f"Evento GLPI recibido sin ticket local asociado (glpi_id={glpi_id})",
                payload_bruto=data,
            )
            return JsonResponse({"ok": True, "event": evento, "status": "ignored"})

        nuevo_estado = GLPI_STATUS_TO_STATE.get(status_id) if status_id is not None else None
        estado_nombre = GLPI_STATUS_NAMES.get(status_id, "desconocido")

        update_fields = []
        if glpi_id is not None and ticket.glpi_id is None:
            ticket.glpi_id = glpi_id
            update_fields.append("glpi_id")

        if nuevo_estado and nuevo_estado != ticket.estado:
            ticket.estado = nuevo_estado
            update_fields.append("estado")
            logger.info("Ticket %s actualizado desde GLPI a %s", ticket.codigo, nuevo_estado)

        titulo_nuevo = None
        for key in ("title", "name"):
            value = _find_first_value(data, key)
            if value and str(value) != str(ticket.titulo):
                titulo_nuevo = str(value)
                break
        if titulo_nuevo:
            ticket.titulo = titulo_nuevo
            update_fields.append("titulo")

        if update_fields:
            update_fields.append("fecha_actualizacion")
            ticket.save(update_fields=update_fields)

        GlpiEvento.objects.create(
            ticket=ticket,
            tipo=GlpiEvento.Tipo.CAMBIO_ESTADO,
            descripcion=f"{ticket.codigo}: estado cambiado a '{estado_nombre}' desde GLPI",
            payload_bruto=data,
        )
        handled = True

    if evento in {"followup_created", "followup", "new_followup", "ticket_followup", "solution_approved", "ticket_solved"} or (
        contenido and ("followup" in evento or "solution" in evento or "comment" in evento or "approved" in evento or "solved" in evento)
    ):
        glpi_ticket_id = _extract_ticket_id(data)
        contenido = contenido or _extract_followup_content(data).strip()
        if not glpi_ticket_id:
            return JsonResponse({"ok": True, "event": evento, "status": "ignored"})

        try:
            ticket = Ticket.objects.get(glpi_id=glpi_ticket_id)
        except Ticket.DoesNotExist:
            GlpiEvento.objects.create(
                tipo=GlpiEvento.Tipo.OTRO,
                descripcion=f"Seguimiento GLPI recibido sin ticket local asociado (glpi_id={glpi_ticket_id})",
                payload_bruto=data,
            )
            return JsonResponse({"ok": True, "event": evento, "status": "ignored"})

        if contenido:
            TicketComentario.objects.create(
                ticket=ticket,
                autor_nombre="Soporte (GLPI)",
                comentario=contenido,
                es_interno=False,
            )

        preview = contenido[:120] + ("..." if len(contenido) > 120 else "")
        GlpiEvento.objects.create(
            ticket=ticket,
            tipo=GlpiEvento.Tipo.SEGUIMIENTO,
            descripcion=f"{ticket.codigo}: {preview}",
            payload_bruto=data,
        )
        logger.info("Nuevo seguimiento agregado a %s desde GLPI", ticket.codigo)
        handled = True

    if not handled:
        GlpiEvento.objects.create(
            tipo=GlpiEvento.Tipo.OTRO,
            descripcion=f"Evento GLPI no reconocido: {evento or 'sin-evento'}",
            payload_bruto=data,
        )

    return JsonResponse({"ok": True, "event": evento})
