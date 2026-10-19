"""Endpoints de la campana de notificaciones (solo el usuario dueño)."""

import logging

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import services
from .models import Notificacion

logger = logging.getLogger(__name__)
ANS_SCAN_CACHE_KEY = "notificaciones:ans_por_vencer:ultima_revision"


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
        usuario=request.user, leida=False
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
    """La ventana emergente ya saltó: no vuelve a mostrarse.

    Los recordatorios del día se agrupan: al descartar la emergente se
    marca el lote completo como visto para no encadenar una tras otra.
    """
    notificacion = get_object_or_404(Notificacion, pk=pk, usuario=request.user)
    mostradas = timezone.now()
    Notificacion.objects.filter(usuario=request.user, mostrada_en__isnull=True).update(
        mostrada_en=mostradas, leida=True, leida_en=mostradas
    )
    return JsonResponse({"ok": True, "pendientes": services.no_leidas(request.user)})


@login_required
@require_POST
def descartar_todas(request):
    total, _ = Notificacion.objects.filter(usuario=request.user).delete()
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
