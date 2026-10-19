"""Correos de Dogger con diseño: alta de usuario, ticket recibido y cierre.

Cada función devuelve el HTML y el texto plano para que el envío no dependa
de que el cliente de correo soporte HTML (igual que el correo de código de
restablecimiento que ya existía).
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)

BASE = "notificaciones/emails/"


def _absoluta(path):
    return f"{settings.SITE_URL.rstrip('/')}{path}" if getattr(settings, "SITE_URL", "") else path


def _enviar(asunto, texto, html, destinatarios):
    """Envía el correo si hay destinatarios y SMTP configurado."""
    destinatarios = [d for d in dict.fromkeys(destinatarios or []) if d]
    if not destinatarios:
        return False
    if not settings.EMAIL_HOST_USER:
        logger.warning("SMTP sin configurar (EMAIL_USER vacío). No se envió: %s", asunto)
        return False
    try:
        from apps.tickets.services.fondo import en_fondo

        return en_fondo(
            send_mail,
            asunto,
            texto,
            settings.DEFAULT_FROM_EMAIL,
            destinatarios,
            html_message=html,
            fail_silently=True,
        )
    except Exception as exc:  # pragma: no cover - red
        logger.error("Error enviando correo '%s': %s", asunto, exc)
        return False


def _render(nombre, ctx):
    ctx = dict(ctx)
    ctx.setdefault("logo_url", "")
    ctx.setdefault("anio", timezone.now().year)
    return render_to_string(BASE + nombre, ctx)


# ------------------------------------------------------------------ alta
def correo_bienvenida(usuario):
    """Mensaje de bienvenida al registrarse, personalizado con su nombre."""
    url_panel = _absoluta(reverse("tickets:mi_panel"))
    html = _render(
        "bienvenida.html",
        {
            "usuario": usuario,
            "rol": usuario.get_rol_display(),
            "ubicacion": usuario.ubicacion,
            "url_panel": url_panel,
            "url_consulta": _absoluta(reverse("tickets:consultar")),
        },
    )
    texto = (
        f"Hola {usuario.nombre},\n\n"
        f"Tu cuenta en Dogger · Mesa de Ayuda TI ya está creada.\n"
        f"Rol: {usuario.get_rol_display()}\n\n"
        "Desde el panel puedes reportar una incidencia, seguir el estado de tus "
        "tickets con el código HD y consultar los tiempos de atención (ANS).\n\n"
        f"Panel: {url_panel}\n"
        f"Consulta de tickets: {_absoluta(reverse('tickets:consultar'))}\n\n"
        "Dogger · Premium Quality"
    )
    return _enviar(
        "Dogger HelpDesk — ¡Bienvenido a tu mesa de ayuda!",
        texto,
        html,
        [usuario.email],
    )


# ------------------------------------------------------- ticket recibido
def correo_ticket_tecnico(ticket, tecnico, url_detalle=""):
    """Aviso al técnico de que le llegó un ticket."""
    html = _render(
        "ticket_recibido_tecnico.html",
        {
            "ticket": ticket,
            "tecnico": tecnico,
            "url_detalle": _absoluta(url_detalle or reverse("tickets:detalle", args=[ticket.pk])),
            "sla": getattr(ticket, "fecha_limite_ans", None),
        },
    )
    texto = (
        f"Hola {getattr(tecnico, 'nombre', '')},"
        f"\n\nSe creó el ticket {ticket.codigo} y está asignado a ti.\n"
        f"Título: {ticket.titulo}\n"
        f"Prioridad: {ticket.get_prioridad_display()}\n"
        f"Solicitante: {ticket.solicitante_nombre} ({ticket.solicitante_email})\n\n"
        f"Detalle: {_absoluta(reverse('tickets:detalle', args=[ticket.pk]))}"
    )
    return _enviar(
        f"[Dogger] Nuevo ticket {ticket.codigo} · {ticket.get_prioridad_display()}",
        texto,
        html,
        [tecnico.email],
    )


def correo_ticket_bandeja(ticket, tecnicos):
    """Aviso al personal cuando el ticket llega sin técnico asignado."""
    correos = [t.email for t in tecnicos if getattr(t, "email", None)]
    if not correos:
        return False
    html = _render(
        "ticket_recibido_tecnico.html",
        {
            "ticket": ticket,
            "tecnico": None,
            "sin_asignar": True,
            "url_detalle": _absoluta(reverse("tickets:sin_asignar")),
            "sla": getattr(ticket, "fecha_limite_ans", None),
        },
    )
    texto = (
        f"Nuevo ticket sin asignar: {ticket.codigo}\n"
        f"Título: {ticket.titulo}\n"
        f"Prioridad: {ticket.get_prioridad_display()}\n"
        f"Solicitante: {ticket.solicitante_nombre} ({ticket.solicitante_email})\n\n"
        f"Bandeja: {_absoluta(reverse('tickets:sin_asignar'))}"
    )
    return _enviar(
        f"[Dogger] Ticket sin asignar {ticket.codigo} · {ticket.get_prioridad_display()}",
        texto,
        html,
        correos,
    )


def correo_ticket_usuario(ticket):
    """Confirmación al usuario: su ticket quedó registrado."""
    es_registrado = bool(ticket.solicitante_email)
    if not es_registrado:
        return False
    html = _render(
        "ticket_recibido_usuario.html",
        {
            "ticket": ticket,
            "url_detalle": _absoluta(reverse("tickets:mi_ticket", args=[ticket.pk])),
            "sla": getattr(ticket, "fecha_limite_ans", None),
        },
    )
    texto = (
        f"Hola {ticket.solicitante_nombre},\n\n"
        f"Registramos tu solicitud {ticket.codigo}: {ticket.titulo}\n"
        f"Prioridad: {ticket.get_prioridad_display()}\n"
        f"Estado: {ticket.get_estado_display()}\n\n"
        f"Puedes seguir el avance con el código {ticket.codigo}:\n"
        f"{_absoluta(reverse('tickets:consultar'))}\n\n"
        "Dogger · Premium Quality"
    )
    return _enviar(
        f"Dogger HelpDesk — Registramos tu ticket {ticket.codigo}",
        texto,
        html,
        [ticket.solicitante_email],
    )


# --------------------------------------------------------- ticket cerrado
def correo_ticket_cerrado(ticket, url_detalle=""):
    """Aviso de cierre al solicitante (y al técnico si es el caso)."""
    destinatarios = []
    if ticket.solicitante_email:
        destinatarios.append(ticket.solicitante_email)
    if ticket.tecnico_asignado_id and ticket.tecnico_asignado.email:
        destinatarios.append(ticket.tecnico_asignado.email)
    if not destinatarios:
        return False

    cierre_texto = ""
    if ticket.fecha_cierre:
        cierre_texto = timezone.localtime(ticket.fecha_cierre).strftime("%d/%m/%Y a las %H:%M")

    html = _render(
        "ticket_cerrado.html",
        {
            "ticket": ticket,
            "fecha_cierre": cierre_texto,
            "url_detalle": _absoluta(url_detalle or reverse("tickets:mi_ticket", args=[ticket.pk])),
        },
    )
    cierre = ""
    if ticket.fecha_cierre:
        cierre = (
            "\nCerrado: "
            + timezone.localtime(ticket.fecha_cierre).strftime("%d/%m/%Y %H:%M")
            + " (hora de Bogotá)"
        )
    texto = (
        f"Hola {ticket.solicitante_nombre},\n\n"
        f"Tu ticket {ticket.codigo} ({ticket.titulo}) quedó en estado "
        f"{ticket.get_estado_display()}.{cierre}\n"
        "\nSi la solución no era la esperada, responde este correo o vuelve a "
        f"reportar el caso:\n{_absoluta(reverse('tickets:mi_panel'))}\n\n"
        "Dogger · Premium Quality"
    )
    return _enviar(
        f"Dogger HelpDesk — Tu ticket {ticket.codigo} fue cerrado",
        texto,
        html,
        destinatarios,
    )


# ------------------------------------------------------ ANS por vencer
def _ans_texto_y_color(ticket, restante):
    """(vencido?, línea de tiempo, hora límite) según el ANS del ticket.

    Un solo sitio para que el correo del técnico y el del usuario digan lo
    mismo: si restante ya es negativo, el ticket venció y el tono cambia.
    """
    from apps.tickets.sla import formatear_duracion

    limite = getattr(ticket, "fecha_limite_ans", None)
    vencido = restante is not None and restante.total_seconds() <= 0
    if vencido:
        linea = f"Venció hace {formatear_duracion(-restante)}"
    else:
        linea = f"Faltan {formatear_duracion(restante)}"
    hora = (
        timezone.localtime(limite).strftime("%d/%m/%Y %H:%M") if limite else ""
    )
    return vencido, linea, hora


def correo_ans_por_vencer_tecnico(ticket, restante):
    """Aviso al técnico: su ticket se está pasando del ANS."""
    tecnico = ticket.tecnico_asignado
    if not tecnico or not getattr(tecnico, "email", None):
        return False
    vencido, linea, hora = _ans_texto_y_color(ticket, restante)
    html = _render(
        "ans_por_vencer_tecnico.html",
        {
            "ticket": ticket,
            "tecnico": tecnico,
            "vencido": vencido,
            "linea_tiempo": linea,
            "hora_limite": hora,
            "url_detalle": _absoluta(
                reverse("tickets:detalle", args=[ticket.pk])
            ),
        },
    )
    texto = (
        f"Hola {getattr(tecnico, 'nombre', '')},\n\n"
        f"Tu ticket {ticket.codigo} {linea.lower()} para resolverlo.\n"
        f"Título: {ticket.titulo}\n"
        f"Prioridad: {ticket.get_prioridad_display()}\n"
        f"ANS: {ticket.ans_horas} h"
        + (f" · límite {hora}" if hora else "")
        + "\n"
        f"Solicitante: {ticket.solicitante_nombre} ({ticket.solicitante_email})\n\n"
        "La supervisión ya está mirando este caso.\n\n"
        f"Detalle: {_absoluta(reverse('tickets:detalle', args=[ticket.pk]))}\n\n"
        "Dogger · Premium Quality"
    )
    return _enviar(
        f"[Dogger] {'Vencido' if vencido else 'Por vencer'} "
        f"{ticket.codigo} · {ticket.get_prioridad_display()}",
        texto,
        html,
        [tecnico.email],
    )


def correo_ans_por_vencer_usuario(ticket, restante):
    """Aviso a la persona que abrió el ticket: su caso va por el límite."""
    correo = (ticket.solicitante_email or "").strip()
    if not correo:
        return False
    vencido, linea, hora = _ans_texto_y_color(ticket, restante)
    html = _render(
        "ans_por_vencer_usuario.html",
        {
            "ticket": ticket,
            "vencido": vencido,
            "linea_tiempo": linea,
            "hora_limite": hora,
            "url_consulta": _absoluta(reverse("tickets:consultar")),
        },
    )
    texto = (
        f"Hola {ticket.solicitante_nombre},\n\n"
        f"Tu solicitud {ticket.codigo} {linea.lower()} dentro del tiempo "
        "comprometido de atención (ANS).\n"
        f"Título: {ticket.titulo}\n"
        f"Estado actual: {ticket.get_estado_display()}\n\n"
        "El caso ya está en manos de soporte y la supervisión está haciendo "
        "seguimiento para resolverlo a tiempo. Puedes consultar el avance con "
        f"tu código en:\n{_absoluta(reverse('tickets:consultar'))}\n\n"
        "Dogger · Premium Quality"
    )
    return _enviar(
        f"Dogger HelpDesk — Tu solicitud {ticket.codigo} va por el límite "
        "de atención",
        texto,
        html,
        [correo],
    )
