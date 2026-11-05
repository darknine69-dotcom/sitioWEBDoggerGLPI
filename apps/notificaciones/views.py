"""Endpoints de la campana de notificaciones (solo el usuario dueño)."""

import logging

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.cache import cache
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import services
from .models import AlertaOperativa, HistorialAlerta, Notificacion

logger = logging.getLogger(__name__)
ANS_SCAN_CACHE_KEY = "notificaciones:ans_por_vencer:ultima_revision"


def _alertas_visibles(usuario):
    alertas = AlertaOperativa.objects.select_related("ticket", "responsable", "ticket__tecnico_asignado")
    if usuario.rol == "admin":
        return alertas
    if usuario.rol == "tecnico":
        return alertas.filter(ticket__tecnico_asignado=usuario)
    if usuario.rol == "observador":
        from apps.tickets.ans_avisos import tickets_del_observador
        return alertas.filter(ticket__in=tickets_del_observador(usuario, alertas=True))
    return alertas.none()


@login_required
def alertas_operativas(request):
    from datetime import timedelta
    from apps.tickets.sla import formatear_duracion
    if request.user.rol not in ("admin", "tecnico", "observador"):
        raise PermissionDenied
    alertas = _alertas_visibles(request.user).prefetch_related("historial__actor").order_by("-creada_en", "-pk")
    alerta_id = request.GET.get("alerta", "")
    if alerta_id.isdecimal():
        alertas = alertas.filter(pk=int(alerta_id))
    estado = request.GET.get("estado", "activas")
    if estado not in ("activas", "todas", *AlertaOperativa.Estado.values):
        estado = "activas"
    if estado == "activas":
        alertas = alertas.exclude(estado=AlertaOperativa.Estado.RESUELTA)
    elif estado in AlertaOperativa.Estado.values:
        alertas = alertas.filter(estado=estado)
    pagina = Paginator(alertas, 20).get_page(request.GET.get("page"))
    for alerta in pagina:
        if alerta.inactividad_segundos is not None:
            alerta.inactividad_legible = formatear_duracion(timedelta(seconds=alerta.inactividad_segundos))
    return render(request, "notificaciones/alertas.html", {"pagina_alertas": pagina, "estado": estado})


@login_required
@require_POST
def accion_alerta(request, pk):
    from apps.tickets.models import Ticket
    if request.user.rol not in ("admin", "tecnico"):
        raise PermissionDenied
    with transaction.atomic():
        alerta = get_object_or_404(AlertaOperativa.objects.select_for_update().filter(pk__in=_alertas_visibles(request.user).values("pk")), pk=pk)
        accion = request.POST.get("accion")
        if accion == "seguimiento" and alerta.estado != AlertaOperativa.Estado.RESUELTA:
            detalle = request.POST.get("detalle", "").strip()
            if not detalle or len(detalle) > 500:
                messages.error(request, "El seguimiento debe tener entre 1 y 500 caracteres.")
            else:
                HistorialAlerta.objects.create(alerta=alerta, actor=request.user, accion="seguimiento", detalle=detalle)
                messages.success(request, "Seguimiento registrado en la alerta.")
        elif accion == "reconocer" and alerta.estado == AlertaOperativa.Estado.ABIERTA:
            alerta.estado = AlertaOperativa.Estado.RECONOCIDA
            alerta.reconocida_en = timezone.now()
            alerta.save(update_fields=["estado", "reconocida_en"])
            HistorialAlerta.objects.create(alerta=alerta, actor=request.user, accion="reconocida")
            messages.success(request, "Alerta reconocida. El ticket continúa sin cambios.")
        elif accion == "resolver" and alerta.estado != AlertaOperativa.Estado.RESUELTA and (
            alerta.tipo != "ans_vencido" or not alerta.ticket_id
            or alerta.ticket.estado not in (Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO)
        ):
            alerta.estado = AlertaOperativa.Estado.RESUELTA
            alerta.resuelta_en = timezone.now()
            alerta.save(update_fields=["estado", "resuelta_en"])
            HistorialAlerta.objects.create(alerta=alerta, actor=request.user, accion="resuelta")
            messages.success(request, "Alerta cerrada correctamente. El ticket no se modificó.")
        elif accion == "resolver" and alerta.tipo == "ans_vencido" and alerta.estado != AlertaOperativa.Estado.RESUELTA:
            messages.warning(request, "No se puede cerrar esta alerta ANS mientras el ticket siga abierto o en progreso.")
    return redirect("notificaciones:alertas_operativas")


@login_required
def centro(request):
    base = Notificacion.objects.filter(usuario=request.user)
    filtro = request.GET.get("filtro", "todas")
    avisos = base.filter(archivada_en__isnull=(filtro != "archivadas"))
    busqueda = request.GET.get("q", "").strip()[:100]
    if filtro == "no_leidas":
        avisos = avisos.filter(leida=False)
    elif filtro == "ans":
        avisos = avisos.filter(clave__startswith="ans-")
    elif filtro == "tickets":
        avisos = avisos.filter(tipo__in=[Notificacion.Tipo.TICKET_NUEVO, Notificacion.Tipo.TICKET_EDITADO, Notificacion.Tipo.TICKET_CERRADO, Notificacion.Tipo.TICKET_RECORDATORIO])
    elif filtro == "eventos":
        avisos = avisos.filter(tipo=Notificacion.Tipo.EVENTO)
    elif filtro == "sistema":
        avisos = avisos.filter(tipo=Notificacion.Tipo.SISTEMA)
    elif filtro == "seguimiento":
        avisos = avisos.filter(Q(clave__icontains=":presion:") | Q(titulo__icontains="seguimiento"))
    if busqueda:
        avisos = avisos.filter(Q(titulo__icontains=busqueda) | Q(mensaje__icontains=busqueda) | Q(actor__icontains=busqueda))
    pagina = Paginator(avisos.order_by("-creada_en", "-id"), 20).get_page(request.GET.get("page"))
    hoy = timezone.localdate()
    for aviso in pagina:
        dias = (hoy - timezone.localtime(aviso.creada_en).date()).days
        aviso.grupo_fecha = "Hoy" if dias <= 0 else "Ayer" if dias == 1 else "Últimos 7 días" if dias <= 7 else "Anteriores"
    activos = base.filter(archivada_en__isnull=True)
    return render(request, "notificaciones/centro.html", {"pagina_avisos": pagina, "filtro": filtro, "busqueda": busqueda, "total_avisos": activos.count(), "sin_leer": services.no_leidas(request.user), "total_archivados": base.filter(archivada_en__isnull=False).count()})


@login_required
@require_POST
def accion_centro(request, pk):
    aviso = get_object_or_404(Notificacion, pk=pk, usuario=request.user)
    accion = request.POST.get("accion")
    if accion == "leer":
        aviso.marcar_leida()
    elif accion == "no_leida":
        Notificacion.objects.filter(pk=aviso.pk, usuario=request.user).update(leida=False, leida_en=None)
    elif accion == "archivar":
        Notificacion.objects.filter(pk=aviso.pk, usuario=request.user).update(archivada_en=timezone.now())
        messages.success(request, "Notificación guardada en Archivadas.")
        return redirect(reverse("notificaciones:centro") + "?filtro=archivadas")
    elif accion == "restaurar":
        Notificacion.objects.filter(pk=aviso.pk, usuario=request.user).update(archivada_en=None)
    elif accion == "abrir":
        destino = aviso.url
        if destino and url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            ahora = timezone.now()
            Notificacion.objects.filter(pk=aviso.pk, usuario=request.user).update(leida=True, leida_en=aviso.leida_en or ahora, mostrada_en=aviso.mostrada_en or ahora)
            return redirect(destino)
    return redirect("notificaciones:centro")


@login_required
@require_POST
def leer_todas_centro(request):
    Notificacion.objects.filter(usuario=request.user, leida=False, archivada_en__isnull=True).update(leida=True, leida_en=timezone.now())
    return redirect("notificaciones:centro")


def _revisar_ans_por_vencer():
    """Revisa ANS desde la campana sin escanear tickets en cada consulta."""
    if not cache.add(ANS_SCAN_CACHE_KEY, True, timeout=60):
        return
    try:
        from apps.tickets.ans_avisos import (
            completar_campanas_pendientes,
            revisar_y_avisar,
        )

        completar_campanas_pendientes()
        revisar_y_avisar()
    except Exception:
        cache.delete(ANS_SCAN_CACHE_KEY)
        logger.exception("No se pudo revisar las alertas tempranas de ANS")


@login_required
@require_POST
def marcar_todas(request):
    """Al abrir la lista, todo lo que ya se vio pasa a leído."""
    actualizadas = Notificacion.objects.filter(
        usuario=request.user, leida=False, archivada_en__isnull=True
    ).update(leida=True, leida_en=timezone.now())
    return JsonResponse({"ok": True, "marcadas": actualizadas, "pendientes": 0})


@login_required
@require_POST
def descartar(request, pk):
    """La "x" quita el aviso de la lista (solo del usuario que lo ve)."""
    notificacion = get_object_or_404(Notificacion, pk=pk, usuario=request.user)
    notificacion.delete()
    return JsonResponse(
        {"ok": True, "pendientes": services.no_leidas(request.user)}
    )


@login_required
@require_POST
def marcar_mostrada(request, pk):
    """Registra solamente la presentación de este aviso."""
    notificacion = get_object_or_404(Notificacion, pk=pk, usuario=request.user)
    notificacion.marcar_mostrada()
    return JsonResponse({"ok": True, "pendientes": services.no_leidas(request.user)})


@login_required
@require_POST
def marcar_leida(request, pk):
    """Marca únicamente el aviso abierto y evita presentar su emergente."""
    notificacion = get_object_or_404(Notificacion, pk=pk, usuario=request.user)
    ahora = timezone.now()
    Notificacion.objects.filter(pk=notificacion.pk, usuario=request.user).update(
        leida=True, leida_en=notificacion.leida_en or ahora,
        mostrada_en=notificacion.mostrada_en or ahora,
    )
    return JsonResponse({"ok": True, "pendientes": services.no_leidas(request.user)})


@login_required
@require_POST
def descartar_todas(request):
    total, _ = Notificacion.objects.filter(usuario=request.user, archivada_en__isnull=True).delete()
    return JsonResponse({"ok": True, "borradas": total, "pendientes": 0})


@login_required
def api(request):
    """Estado de la campana en JSON, para refrescarla sin recargar la página.

    El navegador la consulta periódicamente: así el contador, la lista y la
    ventana emergente se actualizan solos después de cualquier evento
    (creación, edición, respuesta del técnico, cambio de verificación, etc.).

    También sincroniza los recordatorios, de modo que el número siempre es el
    real aunque el ticket se haya cerrado o asignado en otro equipo.
    """
    # Sin cache: es la fuente de verdad en vivo del contador.
    _revisar_ans_por_vencer()
    services.recordatorios(request.user)

    pendientes = services.pendientes_de_emergente(request.user, limite=5)
    return JsonResponse(
        {
            "ok": True,
            "no_leidas": services.no_leidas(request.user),
            "avisos": [
                {
                    "id": n.pk,
                    "tipo": n.tipo,
                    "titulo": n.titulo,
                    "mensaje": n.mensaje,
                    "icono": n.icono or "i-bell",
                    "url": n.url or "",
                    "nueva": not n.leida,
                    "sin_mostrar": n.mostrada_en is None,
                    "actor": n.actor or "",
                    "actor_rol": n.actor_rol or "",
                    "fecha": timezone.localtime(n.creada_en).strftime("%d/%m/%Y %H:%M"),
                }
                for n in services.lista(request.user, limite=15)
            ],
            "emergentes": [
                {
                    "id": n.pk,
                    "tipo": n.tipo,
                    "titulo": n.titulo,
                    "mensaje": n.mensaje,
                    "icono": n.icono or "i-bell",
                    "url": n.url or "",
                    "actor": n.actor or "",
                    "actor_rol": n.actor_rol or "",
                }
                for n in pendientes
            ],
        },
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )
