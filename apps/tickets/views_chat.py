"""Chat de soporte con dos modos.

Soporte (técnico ↔ usuario): ventana flotante estilo Tidio disponible
para todos los roles; el hilo es el de un ticket (sus comentarios no
internos y sus adjuntos) y escribir usa las mismas reglas de cada rol
—el dueño responde, el staff gestiona y el observador participa en lo
de sus zonas— con aviso al otro lado.

Corporativo (staff ↔ staff): una sola sala compartida entre técnicos,
admins y observadores para coordinarse (pasar un caso, avisar una
caída). Sin ticket, sin adjuntos y sin GLPI; el usuario final no la ve.
"""
import logging

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.tickets.models import (
    ElementoMiLista,
    MensajeCorporativo,
    Ticket,
    TicketAdjunto,
    TicketComentario,
)
from apps.tickets.notifications import notificar_comentario
from apps.tickets.services.glpi_client import GlpiError, sync_followup_to_glpi

logger = logging.getLogger(__name__)

TIPOS_PERMITIDOS = (
    "image/png", "image/jpeg", "image/gif", "image/webp",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
)
MAX_ADJUNTO_BYTES = 8 * 1024 * 1024


def _puntos_de(usuario):
    from apps.tickets.views_observador import puntos_del_observador

    if getattr(usuario, "rol", None) != "observador":
        return []
    return puntos_del_observador(usuario)


ROLES_CORPORATIVO = ("tecnico", "admin", "observador")


def _es_corporativo(usuario):
    """Quién entra a la sala corporativa: staff activo, sin usuarios."""
    if not getattr(usuario, "is_authenticated", False):
        return False
    if getattr(usuario, "rol", None) not in ROLES_CORPORATIVO:
        return False
    return bool(getattr(usuario, "is_active", False))


def _puede_ver_hilo(usuario, ticket):
    """Dueño, staff u observador con el ticket en su alcance."""
    if not getattr(usuario, "is_authenticated", False):
        return False
    rol = getattr(usuario, "rol", None)
    if rol == "usuario":
        return (ticket.solicitante_email or "").lower() == (usuario.email or "").lower()
    if getattr(usuario, "es_staff_helpdesk", False):
        return True
    if rol == "observador":
        if (ticket.solicitante_punto or "") in _puntos_de(usuario):
            return True
        return bool(
            ticket.solicitante_email
            and ElementoMiLista.objects.filter(
                observador=usuario, usuario_email__iexact=ticket.solicitante_email
            ).exists()
        )
    return False


def _avatar_url(usuario):
    try:
        if usuario and getattr(usuario, "avatar", None):
            return usuario.avatar.url
    except Exception:  # noqa: BLE001 - sin foto no se rompe el hilo
        pass
    return ""


def _insignia(usuario):
    if not usuario:
        return "Mesa de ayuda"
    return {"usuario": "Usuario", "observador": "Observador",
            "tecnico": "Técnico", "admin": "Admin"}.get(
                getattr(usuario, "rol", ""), "Soporte")


def _tickets_del_rol(usuario, limite=20):
    rol = getattr(usuario, "rol", None)
    qs = Ticket.objects.all().order_by("-fecha_creacion")
    if rol == "usuario":
        qs = qs.filter(solicitante_email__iexact=usuario.email or "")
    elif rol == "tecnico":
        qs = qs.filter(
            Q(tecnico_asignado_id=usuario.pk)
            | Q(estado__in=[Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO],
                tecnico_asignado__isnull=True)
        )
    elif rol == "observador":
        puntos = _puntos_de(usuario)
        correos = list(
            ElementoMiLista.objects.filter(observador=usuario)
            .exclude(usuario_email="")
            .values_list("usuario_email", flat=True)[:200]
        )
        filtro = Q()
        if puntos:
            filtro |= Q(solicitante_punto__in=puntos)
        if correos:
            filtro |= Q(solicitante_email__in=correos)
        qs = qs.filter(filtro) if filtro else qs.none()
    return qs[:limite]


@login_required
@require_GET
def chat_tickets(request):
    """Tickets con los que puede chatear quien pregunta."""
    tickets = _tickets_del_rol(request.user)
    return JsonResponse({
        "ok": True,
        "tickets": [
            {"pk": t.pk, "codigo": t.codigo, "titulo": t.titulo,
             "estado": t.estado, "estado_display": t.get_estado_display()}
            for t in tickets
        ],
    })


@login_required
@require_GET
def chat_hilo(request, pk):
    """Hilo del ticket: mensajes no internos + adjuntos + foto de perfil."""
    ticket = get_object_or_404(Ticket, pk=pk)
    if not _puede_ver_hilo(request.user, ticket):
        return JsonResponse({"ok": False, "error": "Sin acceso."}, status=403)
    try:
        desde = int(request.GET.get("desde") or 0)
    except (TypeError, ValueError):
        desde = 0
    comentarios = (
        ticket.comentarios.filter(es_interno=False)
        .select_related("usuario")
        .order_by("fecha", "id")
    )
    if desde:
        comentarios = comentarios.filter(pk__gt=desde)
    mensajes = []
    for c in comentarios[:200]:
        mensajes.append({
            "id": c.pk,
            "autor": _nombre_autor(c.autor_nombre, c.usuario) or "Mesa de ayuda",
            "insignia": _insignia(c.usuario) if c.usuario_id else "Mesa de ayuda",
            "avatar": _avatar_url(c.usuario),
            "texto": c.comentario,
            "fecha": timezone.localtime(c.fecha).strftime("%d/%m/%Y %H:%M"),
            "propio": bool(c.usuario_id and request.user.pk and c.usuario_id == request.user.pk),
        })
    adjuntos = [
        {"id": a.pk, "nombre": a.nombre_original,
         "url": a.archivo.url if a.archivo else "",
         "es_imagen": a.es_imagen,
         "fecha": timezone.localtime(a.fecha_subida).strftime("%d/%m/%Y %H:%M")}
        for a in ticket.adjuntos.all().order_by("fecha_subida", "id")[:20]
    ]
    return JsonResponse({
        "ok": True, "mensajes": mensajes, "adjuntos": adjuntos,
        "ticket": {"pk": ticket.pk, "codigo": ticket.codigo, "titulo": ticket.titulo},
    })


@login_required
@require_POST
def chat_responder(request, pk):
    """Escribe en el hilo con las reglas del rol y avisa al otro lado."""
    ticket = get_object_or_404(Ticket, pk=pk)
    if not _puede_ver_hilo(request.user, ticket):
        return JsonResponse({"ok": False, "error": "Sin acceso."}, status=403)
    u = request.user
    if getattr(u, "rol", None) not in ("usuario", "tecnico", "admin", "observador"):
        return JsonResponse({"ok": False, "error": "Sin acceso."}, status=403)
    if getattr(u, "rol", None) != "admin" and not getattr(
        u, "puede_responder_chat", False
    ):
        return JsonResponse(
            {"ok": False, "error": "El administrador no te permite chatear."},
            status=403,
        )
    texto = (request.POST.get("mensaje") or "").strip()
    if not texto:
        return JsonResponse({"ok": False, "error": "Escribe tu mensaje."}, status=400)
    if len(texto) > 2000:
        return JsonResponse({"ok": False, "error": "Máximo 2000 caracteres."}, status=400)
    comentario = TicketComentario.objects.create(
        ticket=ticket, usuario=u, autor_nombre=u.nombre,
        comentario=texto, es_interno=False,
    )
    notificar_comentario(ticket, u.nombre, texto, actor=u)
    if ticket.glpi_id:
        try:
            sync_followup_to_glpi(ticket, texto)
        except GlpiError:
            logger.warning("Chat sin GLPI en %s", ticket.codigo)
    return JsonResponse({
        "ok": True,
        "mensaje": {
            "id": comentario.pk, "autor": u.nombre, "insignia": _insignia(u),
            "avatar": _avatar_url(u), "texto": texto,
            "fecha": timezone.localtime(comentario.fecha).strftime("%d/%m/%Y %H:%M"),
            "propio": True,
        },
    })


@login_required
@require_POST
def chat_adjuntar(request, pk):
    """Sube imagen, PDF o documento al hilo (máx. 8 MB)."""
    ticket = get_object_or_404(Ticket, pk=pk)
    if not _puede_ver_hilo(request.user, ticket):
        return JsonResponse({"ok": False, "error": "Sin acceso."}, status=403)
    archivo = request.FILES.get("archivo")
    if not archivo:
        return JsonResponse({"ok": False, "error": "Sin archivo."}, status=400)
    if (archivo.content_type or "") not in TIPOS_PERMITIDOS:
        return JsonResponse(
            {"ok": False, "error": "Solo imágenes, PDF o documentos."}, status=400)
    if archivo.size > MAX_ADJUNTO_BYTES:
        return JsonResponse(
            {"ok": False, "error": "Máximo 8 MB por archivo."}, status=400)
    adjunto = TicketAdjunto.objects.create(
        ticket=ticket, nombre_original=archivo.name[:255], archivo=archivo,
        mime_type=archivo.content_type or "application/octet-stream",
        tamano_bytes=archivo.size, subido_por=request.user.email,
    )
    return JsonResponse({
        "ok": True,
        "adjunto": {
            "id": adjunto.pk, "nombre": adjunto.nombre_original,
            "url": adjunto.archivo.url if adjunto.archivo else "",
            "es_imagen": adjunto.es_imagen,
            "fecha": timezone.localtime(adjunto.fecha_subida).strftime("%d/%m/%Y %H:%M"),
        },
    })


def _nombre_autor(autor_nombre, usuario):
    """Quién escribió, siempre identificable: nombre o, en su defecto, correo."""
    if (autor_nombre or "").strip():
        return autor_nombre.strip()
    if usuario is not None:
        return (usuario.nombre or "").strip() or (usuario.email or "").strip()
    return ""


def _mensaje_corp_json(m, lector):
    return {
        "id": m.pk,
        "autor": _nombre_autor(m.autor_nombre, m.usuario) or "Mesa de ayuda",
        "insignia": _insignia(m.usuario) if m.usuario_id else "Mesa de ayuda",
        "avatar": _avatar_url(m.usuario),
        "texto": m.texto,
        "fecha": timezone.localtime(m.fecha).strftime("%d/%m/%Y %H:%M"),
        "propio": bool(m.usuario_id and lector.pk and m.usuario_id == lector.pk),
    }


def _colega_corporativo(usuario, para):
    """Valida el destinatario del directo: staff activo, distinto de uno."""
    from apps.accounts.models import Usuario

    if not para:
        return None
    try:
        colega = Usuario.objects.filter(pk=int(para)).first()
    except (TypeError, ValueError):
        return None
    if (
        colega is None
        or colega.pk == usuario.pk
        or not getattr(colega, "is_active", False)
        or getattr(colega, "rol", None) not in ROLES_CORPORATIVO
    ):
        return None
    return colega


@login_required
@require_GET
def chat_colegas(request):
    """Gente del staff con la que se puede hablar en directo."""
    if not _es_corporativo(request.user):
        return JsonResponse({"ok": False, "error": "Sin acceso."}, status=403)
    from apps.accounts.models import Usuario

    colegas = (
        Usuario.objects.filter(rol__in=ROLES_CORPORATIVO, is_active=True)
        .exclude(pk=request.user.pk)
        .order_by("nombre")[:200]
    )
    return JsonResponse({
        "ok": True,
        "colegas": [
            {"pk": c.pk, "nombre": c.nombre or c.email,
             "insignia": _insignia(c),
             "en_linea": bool(getattr(c, "en_linea", False))}
            for c in colegas
        ],
    })


@login_required
@require_GET
def chat_novedades(request):
    """Cuántos mensajes corporativos no ha visto el staff.

    Recibe lo ya visto (`?sala=` y `?dm=pk:id,pk:id`) y devuelve los
    conteos de la sala y de cada directo, para pintar el contador de la
    burbuja aunque el chat esté cerrado o en otro hilo.
    """
    from django.db.models import Count, Max

    if not _es_corporativo(request.user):
        return JsonResponse({"ok": False, "error": "Sin acceso."}, status=403)
    try:
        visto_sala = int(request.GET.get("sala") or 0)
    except (TypeError, ValueError):
        visto_sala = 0
    vistos_dm = {}
    for par in (request.GET.get("dm") or "").split(","):
        try:
            pk, visto = par.split(":")
            vistos_dm[int(pk)] = int(visto)
        except (TypeError, ValueError):
            continue
    sala = MensajeCorporativo.objects.filter(
        destinatario__isnull=True
    ).exclude(usuario=request.user).aggregate(
        ultimo=Max("pk"), nuevos=Count("pk", filter=Q(pk__gt=visto_sala))
    )
    de_partners = set(
        MensajeCorporativo.objects.filter(destinatario=request.user)
        .exclude(usuario__isnull=True)
        .values_list("usuario_id", flat=True)[:200]
    )
    a_partners = set(
        MensajeCorporativo.objects.filter(usuario=request.user)
        .exclude(destinatario__isnull=True)
        .values_list("destinatario_id", flat=True)[:200]
    )
    dms = {}
    total = sala["nuevos"] or 0
    for otro in sorted(de_partners | a_partners)[:50]:
        hilo = MensajeCorporativo.objects.filter(
            Q(usuario=request.user, destinatario_id=otro)
            | Q(usuario_id=otro, destinatario=request.user)
        ).exclude(usuario=request.user).aggregate(
            ultimo=Max("pk"),
            nuevos=Count("pk", filter=Q(pk__gt=vistos_dm.get(otro, 0))),
        )
        dms[otro] = {"ultimo": hilo["ultimo"] or 0, "nuevos": hilo["nuevos"] or 0}
        total += hilo["nuevos"] or 0
    return JsonResponse({
        "ok": True,
        "sala": {"ultimo": sala["ultimo"] or 0, "nuevos": sala["nuevos"] or 0},
        "dms": dms,
        "total": total,
    })


@login_required
@require_GET
def chat_estado(request):
    """Diagnóstico del chat: tablas y migraciones aplicadas (solo staff).

    Para ubicar un 500 sin entrar al servidor: abre /chat/api/estado/
    en el navegador y pega lo que salga.
    """
    if not (
        getattr(request.user, "es_staff_helpdesk", False)
        or getattr(request.user, "es_observador", False)
    ):
        return JsonResponse({"ok": False, "error": "Sin acceso."}, status=403)
    from django.db import connection

    info = {"ok": True, "tablas": {}, "migraciones_tickets": []}
    for tabla in ("ChatCorporativo", "TicketComentarios"):
        try:
            with connection.cursor() as cur:
                cur.execute(f'SELECT COUNT(*) FROM "{tabla}"')
                info["tablas"][tabla] = cur.fetchone()[0]
        except Exception as exc:  # noqa: BLE001 - el error ES el diagnóstico
            info["tablas"][tabla] = f"ERROR: {exc.__class__.__name__}: {exc}"
    try:
        from django.db.migrations.recorder import MigrationRecorder

        aplicadas = MigrationRecorder.Migration.objects.filter(
            app="tickets"
        ).values_list("name", flat=True)
        info["migraciones_tickets"] = sorted(aplicadas)[-8:]
    except Exception as exc:  # noqa: BLE001
        info["migraciones_tickets"] = f"ERROR: {exc.__class__.__name__}: {exc}"
    return JsonResponse(info)


@login_required
@require_GET
def chat_corporativo(request):
    """Sala o directo del staff (`?desde=` para el vivo, `?para=` directo)."""
    if not _es_corporativo(request.user):
        return JsonResponse({"ok": False, "error": "Sin acceso."}, status=403)
    para = request.GET.get("para") or ""
    if para and _colega_corporativo(request.user, para) is None:
        return JsonResponse({"ok": False, "error": "Colega no válido."}, status=404)
    try:
        desde = int(request.GET.get("desde") or 0)
    except (TypeError, ValueError):
        desde = 0
    qs = MensajeCorporativo.objects.select_related("usuario").order_by("fecha", "id")
    if para:
        qs = qs.filter(
            Q(usuario=request.user, destinatario_id=int(para))
            | Q(usuario_id=int(para), destinatario=request.user)
        )
    else:
        qs = qs.filter(destinatario__isnull=True)
    if desde:
        qs = qs.filter(pk__gt=desde)
    mensajes = [_mensaje_corp_json(m, request.user) for m in qs[:200]]
    return JsonResponse({"ok": True, "mensajes": mensajes})


@login_required
@require_POST
def chat_corporativo_enviar(request):
    """Escribe en la sala o al colega, con las reglas de chateo del rol."""
    if not _es_corporativo(request.user):
        return JsonResponse({"ok": False, "error": "Sin acceso."}, status=403)
    u = request.user
    if getattr(u, "rol", None) != "admin" and not getattr(
        u, "puede_responder_chat", False
    ):
        return JsonResponse(
            {"ok": False, "error": "El administrador no te permite chatear."},
            status=403,
        )
    para = request.POST.get("para") or ""
    colega = None
    if para:
        colega = _colega_corporativo(u, para)
        if colega is None:
            return JsonResponse({"ok": False, "error": "Colega no válido."}, status=404)
    texto = (request.POST.get("mensaje") or "").strip()
    if not texto:
        return JsonResponse({"ok": False, "error": "Escribe tu mensaje."}, status=400)
    if len(texto) > 2000:
        return JsonResponse({"ok": False, "error": "Máximo 2000 caracteres."}, status=400)
    mensaje = MensajeCorporativo.objects.create(
        usuario=u, autor_nombre=u.nombre, texto=texto, destinatario=colega,
    )
    if colega is not None:
        # El destinatario se entera por la campana (la sala no avisa a nadie).
        try:
            from apps.accounts.routing import landing_por_rol
            from apps.notificaciones import services as avisos

            avisos.crear(
                colega,
                "sistema",
                f"Mensaje corporativo de {u.nombre or u.email}",
                texto,
                url=f"{landing_por_rol(colega)}#chat-corp-dm-{u.pk}",
                icono="i-message",
                actor=u.nombre or u.email,
                actor_rol=u.get_rol_display(),
            )
        except Exception:  # noqa: BLE001 - sin campana igual se publica
            logger.warning("Sin campana corporativa para %s", colega)
    return JsonResponse({"ok": True, "mensaje": _mensaje_corp_json(mensaje, u)})
