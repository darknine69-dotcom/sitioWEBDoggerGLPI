import json
import secrets
import string
from collections import Counter
from datetime import date, datetime, timedelta
import logging
import re

from django.contrib import messages
from django.contrib.auth import get_user_model, login as auth_login
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Prefetch, Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.utils import timezone
from django.utils.dateformat import DateFormat
from django.views.decorators.http import require_POST

PRESETS_MIS = [
    ("abiertas", "Mis solicitudes abiertas"),
    ("todas", "Todas las solicitudes"),
    ("completadas", "Mis solicitudes completadas"),
    ("espera", "Mis solicitudes en espera"),
    ("no-asignadas", "Solicitudes no asignadas"),
    ("vencen-hoy", "Solicitudes que vencen hoy"),
    ("vencidas", "Solicitudes vencidas"),
    ("creadas-hoy", "Solicitudes creadas hoy"),
]
RANGOS_MIS = [
    ("7", "Últimos 7 días"),
    ("15", "Últimos 15 días"),
    ("30", "Los 30 últimos días"),
    ("60", "Últimos 60 días"),
    ("90", "Últimos 90 días"),
    ("180", "Últimos 180 días"),
    ("365", "Últimos 365 días"),
    ("", "Todo el tiempo"),
]

from .decorators import admin_required, staff_required, user_required
from .exports import generar_excel_reportes, generar_excel_tickets
from .forms import (
    AsignarTecnicoForm,
    CategoriaForm,
    ComentarioForm,
    ConsultaTicketForm,
    TicketEdicionForm,
    TicketForm,
    UsuarioPanelForm,
)
from .models import Categoria, GlpiEvento, Ticket, TicketAdjunto, TicketComentario, TicketVinculo
from .notifications import notificar_comentario, notificar_ticket_actualizado, notificar_ticket_creado
from .sla import horas_por_prioridad, orden_prioridad_annotation
from .services.glpi_client import (
    GlpiClient,
    GlpiError,
    sync_adjuntos_to_glpi,
    sync_asignacion_to_glpi,
    sync_edicion_to_glpi,
    sync_estado_to_glpi,
    sync_followup_to_glpi,
    sync_ticket_to_glpi,
)
from .sugerencia_categoria import claves_para_json

logger = logging.getLogger(__name__)
User = get_user_model()

COLORES_ESTADO = {
    "abierto": "#D62B1F",
    "en-progreso": "#F2A900",
    "resuelto": "#2F7D4F",
    "cerrado": "#6B6259",
}
COLORES_PRIORIDAD = {
    "urgente": "#D62B1F",
    "alta": "#F26522",
    "media": "#F2A900",
    "baja": "#6B9E78",
}


def _cargas_activas(usuarios_ids):
    """Carga de trabajo por técnico: tickets abiertos o en progreso asignados."""
    filas = (
        Ticket.objects.filter(
            tecnico_asignado_id__in=list(usuarios_ids),
            estado__in=(Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO),
        )
        .values("tecnico_asignado_id")
        .annotate(carga=Count("id"))
    )
    return {r["tecnico_asignado_id"]: r["carga"] for r in filas}


def _auto_asignar_tecnico(ticket) -> bool:
    """
    Asignación automática por categoría, prioridad y disponibilidad:
      - Candidatos: técnicos/administradores activos del sistema.
      - Urgente/Alta: se elige al técnico con MENOR carga activa (disponibilidad);
        en caso de empate, gana el técnico por defecto de la categoría.
      - Media/Baja: se respeta primero el técnico por defecto de la categoría
        y, si no existe, se elige al de menor carga activa.
    """
    if ticket.tecnico_asignado_id or not ticket.categoria_id:
        return False
    categoria = Categoria.objects.filter(pk=ticket.categoria_id).select_related("tecnico_default").first()
    if not categoria:
        return False
    Usuario = get_user_model()
    candidatos = list(
        Usuario.objects.filter(
            activo=True,
            is_active=True,
            rol__in=(Usuario.Rol.TECNICO, Usuario.Rol.ADMIN),
        ).order_by("pk")
    )
    if not candidatos:
        return False
    cargas = _cargas_activas([c.pk for c in candidatos])
    default = categoria.tecnico_default

    def clave(c):
        carga = cargas.get(c.pk, 0)
        es_default = bool(default and c.pk == default.pk)
        if ticket.prioridad in (Ticket.Prioridad.URGENTE, Ticket.Prioridad.ALTA):
            # Prioridad alta/urgente: importa la disponibilidad.
            return (carga, not es_default, c.pk)
        # Media/Baja: primero el técnico por defecto, luego el de menor carga.
        return (not es_default, carga, c.pk)

    elegido = min(candidatos, key=clave)
    if not elegido:
        return False
    ticket.tecnico_asignado = elegido
    ticket.asignacion_automatica = True
    return True


@require_POST
def descartar_ticket_aviso(request):
    """El usuario cerró la ventana de 'Ticket creado': limpiar el aviso de sesión."""
    request.session.pop("ticket_creado_info", None)
    return JsonResponse({"ok": True})


def _sincronizar_ticket_nuevo(request, ticket, files):
    """
    Sincroniza un ticket recién creado hacia GLPI y sube sus adjuntos.
    Informa al usuario el resultado sin bloquear el flujo local.
    """
    try:
        glpi_id = sync_ticket_to_glpi(ticket)
    except GlpiError as exc:
        messages.warning(
            request,
            f"El ticket {ticket.codigo} quedó guardado, pero no se pudo registrar "
            f"en GLPI: {exc}. Se reintentará con 'sync_glpi_pendientes'.",
        )
        return
    if not glpi_id:
        return

    messages.info(request, f"También registrado en GLPI #{glpi_id}")
    if files:
        try:
            n = sync_adjuntos_to_glpi(ticket)
            if n:
                messages.info(request, f"{n} adjunto(s) subido(s) a GLPI.")
        except GlpiError as exc:
            messages.warning(request, f"No se pudieron subir los adjuntos a GLPI: {exc}")


def _build_chart_context(tickets):
    """Gráficas y ANS a partir de una iterable de tickets (sin eventos GLPI)."""
    pri_counts = Counter(t.prioridad for t in tickets)
    total = max(len(tickets), 1)
    priority_labels = ("urgente", "alta", "media", "baja")
    max_priority_count = max((pri_counts.get(k, 0) for k in priority_labels), default=0)
    priority_bars = [
        {
            "label": k,
            "count": pri_counts.get(k, 0),
            "pct": round(pri_counts.get(k, 0) / total * 100),
            "fill_pct": 0 if max_priority_count == 0 else round((pri_counts.get(k, 0) / max_priority_count) * 100),
            "color": COLORES_PRIORIDAD.get(k, "#F2A900"),
        }
        for k in priority_labels
    ]
    cat_counts = Counter(
        (t.categoria.nombre if t.categoria else "Sin categoria") for t in tickets
    )
    max_category_count = max(cat_counts.values(), default=0)
    category_bars = [
        {
            "label": k,
            "count": v,
            "pct": round(v / total * 100),
            "fill_pct": 0 if max_category_count == 0 else round((v / max_category_count) * 100),
        }
        for k, v in cat_counts.most_common(8)
    ]

    estado_labels = ("abierto", "en-progreso", "resuelto", "cerrado")
    estado_display = dict(Ticket.Estado.choices)
    estado_counts = Counter(t.estado for t in tickets)
    total_estados = max(sum(estado_counts.values()), 1)
    max_estado_count = max((estado_counts.get(k, 0) for k in estado_labels), default=0)
    estado_bars = [
        {
            "label": estado_display.get(k, k),
            "slug": k,
            "count": estado_counts.get(k, 0),
            "pct": round(estado_counts.get(k, 0) / total_estados * 100),
            "fill_pct": 0 if max_estado_count == 0 else round((estado_counts.get(k, 0) / max_estado_count) * 100),
            "color": COLORES_ESTADO.get(k, "#6B6259"),
        }
        for k in estado_labels
    ]
    donut_segments = [
        {"v": estado_counts.get(k, 0), "c": COLORES_ESTADO.get(k, "#6B6259")}
        for k in estado_labels
        if estado_counts.get(k, 0) > 0
    ]

    tecnico_counts = Counter(
        (t.tecnico_asignado.nombre if t.tecnico_asignado else "Sin asignar") for t in tickets
    )
    max_tecnico_count = max(tecnico_counts.values(), default=0)
    tecnico_bars = [
        {
            "label": k,
            "count": v,
            "fill_pct": 0 if max_tecnico_count == 0 else round(v / max_tecnico_count * 100),
        }
        for k, v in tecnico_counts.most_common(8)
    ]

    # Tickets por solicitante (para gráfico de usuarios)
    user_counts = Counter(
        (t.solicitante_nombre or t.solicitante_email or "Anónimo") for t in tickets
    )
    max_user_count = max(user_counts.values(), default=0)
    user_bars = [
        {
            "label": k,
            "count": v,
            "fill_pct": 0 if max_user_count == 0 else round((v / max_user_count) * 100),
        }
        for k, v in user_counts.most_common(10)
    ]

    # Cumplimiento ANS entre los tickets abiertos/en progreso
    ans_vencidos = ans_por_vencer = ans_ok = 0
    for t in tickets:
        estado = t.info_ans[0]
        if estado == "vencido":
            ans_vencidos += 1
        elif estado == "por-vencer":
            ans_por_vencer += 1
        elif estado == "ok":
            ans_ok += 1
    ans_total = max(ans_vencidos + ans_por_vencer + ans_ok, 1)
    ans_stats = {
        "vencidos": ans_vencidos,
        "por_vencer": ans_por_vencer,
        "ok": ans_ok,
        "pct_ok": round(ans_ok / ans_total * 100),
        "bar_vencidos": round(ans_vencidos / ans_total * 100),
        "bar_por_vencer": round(ans_por_vencer / ans_total * 100),
        "bar_ok": round(ans_ok / ans_total * 100),
    }

    return {
        "priority_bars": priority_bars,
        "category_bars": category_bars,
        "estado_bars": estado_bars,
        "tecnico_bars": tecnico_bars,
        "user_bars": user_bars,
        "ans_stats": ans_stats,
        "donut_segments": json.dumps(donut_segments),
    }


# ---------------------------------------------------------------------------
# Dashboard global del Panel Técnico (6 widgets)
# ---------------------------------------------------------------------------

COLORES_MODO = {
    "web": "#2A6FDB",
    "email": "#2F7D4F",
    "telefono": "#B7791F",
    "no-asignado": "#8A8A86",
}

COLORES_SERIE = {
    "entrante": "#2563EB",
    "completado": "#2F7D4F",
    "vencido": "#D62B1F",
    "riesgo": "#F2A900",
}

_LABEL_MODO = {
    "web": "Web Form",
    "email": "E-Mail",
    "telefono": "Phone Call",
}


_DIAS_SEMANA = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")


def _serie_dias(inicio, fin, con_dia=False):
    """Lista de etiquetas por día entre dos fechas (día de semana + día o d/m)."""
    dias = []
    for i in range((fin - inicio).days + 1):
        d = inicio + timedelta(days=i)
        if con_dia:
            dias.append(f"{d.day}/{d.month:02d}")
        else:
            dias.append(f"{_DIAS_SEMANA[d.weekday()]} {d.day}")
    return dias


def _agrupar_vencidos(tickets, dimension):
    """Cuenta tickets abiertos por dimensión según estado ANS (vencido / por vencer).

    Cada vencimiento se trata como una SANCIÓN: vencidos es el número de
    infracciones y riesgo las advertencias por vencerse pronto.
    """
    agg = {}
    for t in tickets:
        clave, label = dimension(t)
        if t.estado not in (Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO):
            continue
        estado_ans = t.info_ans[0]
        if estado_ans not in ("vencido", "por-vencer"):
            continue
        if clave not in agg:
            agg[clave] = {"label": label, "vencidos": 0, "riesgo": 0}
        agg[clave][("por-vencer" if estado_ans == "por-vencer" else "vencidos")] += 1
    return [v for v in agg.values()]


def _build_tecnico_dashboard(tecnico_id=None):
    """
    Datos JSON para el rediseño del Panel Técnico.

    Incluye: tabla dinámica pivote, gráficos modales (modo/prioridad, con
    cambio de tipo), serie de solicitudes por rango, SLA por dimensión y
    comparativos de los últimos 20 días.

    Si se indica un técnico, el dashboard se limita a SUS solicitudes.
    """
    qs = Ticket.objects.select_related("categoria", "tecnico_asignado")
    if tecnico_id:
        qs = qs.filter(tecnico_asignado_id=tecnico_id)
    tickets = list(qs.order_by("fecha_creacion"))
    abiertos = [
        t
        for t in tickets
        if t.estado in (Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO)
    ]
    hoy = timezone.now().date()

    # --- Tabla dinámica pivote -------------------------------------------
    def _pivot(dimension, sort_key=None, limite=40):
        rows = {}
        for t in tickets:
            clave, label = dimension(t)
            fila = rows.setdefault(
                clave, {"label": label, "abrir": 0, "espera": 0, "vencido": 0, "riesgo": 0, "cerrado": 0, "resueltos": 0, "total": 0, "categorias": [], "_cats": set(), "tickets": []}
            )
            fila["total"] += 1
            if t.estado == Ticket.Estado.ABIERTO:
                fila["abrir"] += 1
            elif t.estado == Ticket.Estado.EN_PROGRESO:
                fila["espera"] += 1
            elif t.estado == Ticket.Estado.RESUELTO:
                fila["resueltos"] += 1
            elif t.estado == Ticket.Estado.CERRADO:
                fila["cerrado"] += 1
            ans = t.info_ans[0]
            if t.estado in (Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO):
                if ans == "vencido":
                    fila["vencido"] += 1
                elif ans == "por-vencer":
                    fila["riesgo"] += 1
                cat = "Sin categoría"
                if t.categoria_id:
                    cat = f"{t.categoria.grupo or ''} › {t.categoria.nombre or ''}".strip(" ›") or "Sin categoría"
                if cat not in fila["_cats"] and len(fila["_cats"]) < 8:
                    fila["_cats"].add(cat)
            if len(fila["tickets"]) < limite:
                fila["tickets"].append(
                    {
                        "id": t.pk,
                        "codigo": t.codigo,
                        "titulo": t.titulo,
                        "estado": t.estado,
                        "vencido": ans == "vencido"
                        and t.estado in (Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO),
                    }
                )
        lista = list(rows.values())
        for r in lista:
            r["categorias"] = sorted(r.pop("_cats"))
            r["tickets"] = sorted(r["tickets"], key=lambda x: -x["id"])
        if sort_key:
            lista.sort(key=sort_key)
        return lista

    def dim_tecnico(t):
        if t.tecnico_asignado_id:
            return (t.tecnico_asignado_id, t.tecnico_asignado.nombre)
        return ("__sin", "No asignado")

    def dim_prioridad(t):
        return (t.prioridad, t.get_prioridad_display())

    def dim_modo(t):
        modo = "no-asignado"
        if t.modo in _LABEL_MODO:
            modo = t.modo
        return (modo, _LABEL_MODO.get(modo, "No asignado"))

    def dim_grupo(t):
        if t.categoria_id:
            return (t.categoria.grupo, t.categoria.grupo)
        return ("__sin", "Sin categoría")

    def dim_categoria(t):
        if t.categoria_id:
            grupo = t.categoria.grupo or ""
            nombre = t.categoria.nombre or ""
            return (t.categoria_id, f"{grupo} › {nombre}".strip(" ›"))
        return ("__sin", "Sin categoría")

    pivot = {
        "dimensiones": {
            "tecnico": {
                "label": "Técnico",
                "rows": sorted(_pivot(dim_tecnico), key=lambda r: r["label"].lower()),
            },
            "prioridad": {
                "label": "Prioridad",
                "rows": sorted(
                    _pivot(dim_prioridad),
                    key=lambda r: ("urgente", "alta", "media", "baja").index(r["label"].lower())
                    if r["label"].lower() in ("urgente", "alta", "media", "baja")
                    else 99,
                ),
            },
            "modo": {
                "label": "Modo de ingreso",
                "rows": sorted(
                    _pivot(dim_modo),
                    key=lambda r: ("web form", "e-mail", "phone call", "no asignado").index(r["label"].lower())
                    if r["label"].lower() in ("web form", "e-mail", "phone call", "no asignado")
                    else 99,
                ),
            },
            "grupo": {
                "label": "Grupo",
                "rows": _pivot(dim_grupo, sort_key=lambda r: r["label"].lower()),
            },
            "categoria": {
                "label": "Categoría",
                "rows": _pivot(dim_categoria, sort_key=lambda r: r["label"].lower()),
            },
        },
        "columnas": ["abrir", "espera", "vencido", "cerrado", "resueltos"],
    }

    # --- Pie: modo / prioridad (solo abiertos) ---------------------------
    def _pie(acc, colores, etiquetas):
        return [
            {"label": etiquetas.get(k, k), "value": v, "color": colores.get(k, "#8A8A86")}
            for k, v in acc.items()
            if v > 0
        ]

    etiquetas_modo = dict(_LABEL_MODO, **{"no-asignado": "No asignado"})
    modo_counts = Counter(dim_modo(t)[0] for t in abiertos)
    pie_modo = _pie(  # orden fijo: web, email, telefono, no asignado
        {k: modo_counts.get(k, 0) for k in ("web", "email", "telefono", "no-asignado")},
        COLORES_MODO,
        etiquetas_modo,
    )
    etiquetas_prioridad = dict(Ticket.Prioridad.choices)
    pri_counts = Counter(t.prioridad for t in abiertos)
    pie_prioridad = _pie(
        {k: pri_counts.get(k, 0) for k in ("urgente", "alta", "media", "baja")},
        COLORES_PRIORIDAD,
        etiquetas_prioridad,
    )

    # --- Pie: abiertas por categoría -------------------------------------
    _PAL_CAT = ["#2563EB", "#2F7D4F", "#F2A900", "#B7791F", "#8A8A86", "#6B6259", "#D62B1F", "#7C4DFF"]
    cat_abiertas = {}
    for t in abiertos:
        cid, clabel = dim_categoria(t)
        fila = cat_abiertas.setdefault(cid, {"label": clabel, "n": 0})
        fila["n"] += 1
    cat_items = sorted(cat_abiertas.values(), key=lambda r: (-r["n"], r["label"].lower()))
    pie_categoria = [
        {"label": it["label"], "value": it["n"], "color": _PAL_CAT[i % len(_PAL_CAT)]}
        for i, it in enumerate(cat_items)
    ]

    # --- Serie de solicitudes por rango ----------------------------------
    def _rango(rango):
        if rango == "ultima_semana":
            inicio, fin = hoy - timedelta(days=6), hoy
        elif rango == "esta_semana":
            inicio, fin = hoy - timedelta(days=hoy.weekday()), hoy
        elif rango == "este_mes":
            inicio, fin = hoy.replace(day=1), hoy
        else:  # ultimo_mes
            fin = hoy.replace(day=1) - timedelta(days=1)
            inicio = fin.replace(day=1)

        con_dia = rango in ("este_mes", "ultimo_mes")
        etiquetas = _serie_dias(inicio, fin, con_dia=con_dia)

        dias = {}
        d = inicio
        while d <= fin:
            dias[d] = {"entrante": 0, "completado": 0, "vencido": 0}
            d += timedelta(days=1)

        for t in tickets:
            d = _key_fecha(t.fecha_creacion)
            if d in dias:
                dias[d]["entrante"] += 1
            if t.estado in (Ticket.Estado.RESUELTO, Ticket.Estado.CERRADO) and t.fecha_cierre:
                dc = _key_fecha(t.fecha_cierre)
                if dc in dias:
                    dias[dc]["completado"] += 1
            if d in dias and t.info_ans[0] == "vencido":
                dias[d]["vencido"] += 1

        ordenadas = sorted(dias)
        return {
            "labels": etiquetas,
            "entrante": [dias[k]["entrante"] for k in ordenadas],
            "completado": [dias[k]["completado"] for k in ordenadas],
            "vencido": [dias[k]["vencido"] for k in ordenadas],
        }

    linea = {
        k: _rango(k)
        for k in ("ultima_semana", "esta_semana", "este_mes", "ultimo_mes")
    }

    # --- SLA por dimensión ------------------------------------------------
    sla = {
        "por_tecnico": _agrupar_vencidos(tickets, dim_tecnico),
        "por_prioridad": _agrupar_vencidos(tickets, dim_prioridad),
        "por_categoria": _agrupar_vencidos(tickets, dim_categoria),
        "por_grupo": _agrupar_vencidos(tickets, dim_grupo),
    }

    # --- Comparativos últimos 20 días -------------------------------------
    def _comparativo(fecha_t):  # recibe lista (t, flag brecha)
        inicio = hoy - timedelta(days=19)
        etiquetas = []
        ok, brecha = [], []
        for i in range(20):
            d = inicio + timedelta(days=i)
            etiquetas.append(DateFormat(d).format("d/m"))
            ok.append(0)
            brecha.append(0)
        for d, es_brecha in fecha_t:
            if inicio <= d <= hoy:
                i = (d - inicio).days
                (brecha if es_brecha else ok)[i] += 1
        return {"labels": etiquetas, "ok": ok, "brecha": brecha}

    recibidas = []
    for t in tickets:
        if t.fecha_creacion:
            recibidas.append((_key_fecha(t.fecha_creacion), t.info_ans[0] == "vencido"))

    completadas = []
    for t in tickets:
        if t.estado in (Ticket.Estado.RESUELTO, Ticket.Estado.CERRADO) and t.fecha_cierre:
            duracion = t.fecha_cierre - t.fecha_creacion
            es_brecha = duracion > timedelta(hours=t.ans_horas)
            completadas.append((_key_fecha(t.fecha_cierre), es_brecha))

    comparativo = {
        "recibidas": _comparativo(recibidas),
        "completadas": _comparativo(completadas),
    }

    return json.dumps(
        {
            "pivot": pivot,
            "pie_modo": pie_modo,
            "pie_prioridad": pie_prioridad,
            "pie_categoria": pie_categoria,
            "linea": linea,
            "colores_serie": COLORES_SERIE,
            "sla": sla,
            "comparativo": comparativo,
        },
        ensure_ascii=False,
    )


def _key_fecha(fecha):
    return fecha.date() if hasattr(fecha, "date") else fecha


def _build_dashboard_context(request, tickets):
    chart_context = _build_chart_context(tickets)
    eventos_qs = GlpiEvento.objects.select_related("ticket").order_by("-fecha")
    pp_glpi = _resolve_per_page(request, "per_page_glpi", 5)
    page_number = request.GET.get("page_glpi", 1)
    paginator = Paginator(eventos_qs, pp_glpi)
    eventos_glpi_page = paginator.get_page(page_number)
    chart_context.update({
        "eventos_glpi": eventos_glpi_page.object_list,
        "eventos_glpi_page": eventos_glpi_page,
        "per_page_glpi": pp_glpi,
        "querystring_glpi": _params_sin_page(request, "page_glpi"),
    })
    return chart_context


def paginate_recent_tickets(request, queryset, page_param="page_recientes", per_page=5, per_page_param="per_page_recientes"):
    pp = _resolve_per_page(request, per_page_param, per_page)
    if pp == 0:
        pp = queryset.count() or 1
    paginator = Paginator(
        queryset.annotate(
            _prioridad_orden=orden_prioridad_annotation()
        ).order_by("_prioridad_orden", "-fecha_creacion"),
        pp,
    )
    page_number = request.GET.get(page_param, 1)
    page_obj = paginator.get_page(page_number)
    return page_obj


def _parse_fecha_reporte(valor):
    if not valor:
        return None
    try:
        return date.fromisoformat(valor)
    except (ValueError, TypeError):
        return None


def _reportes_filtros(request):
    """Aplica los filtros del panel corporativo y retorna (f, qs)."""
    qs = Ticket.objects.select_related("categoria", "tecnico_asignado")
    desde = _parse_fecha_reporte(request.GET.get("desde"))
    hasta = _parse_fecha_reporte(request.GET.get("hasta"))
    categoria = request.GET.get("categoria", "").strip()
    prioridad = request.GET.get("prioridad", "").strip()
    tecnico = request.GET.get("tecnico", "").strip()
    usuario = request.GET.get("usuario", "").strip()

    if desde:
        qs = qs.filter(fecha_creacion__date__gte=desde)
    if hasta:
        qs = qs.filter(fecha_creacion__date__lte=hasta)
    if categoria.isdigit():
        qs = qs.filter(categoria_id=categoria)
    if prioridad in dict(Ticket.Prioridad.choices):
        qs = qs.filter(prioridad=prioridad)
    if tecnico.isdigit():
        qs = qs.filter(tecnico_asignado_id=tecnico)
    if usuario:
        qs = qs.filter(
            Q(solicitante_email__icontains=usuario) | Q(solicitante_nombre__icontains=usuario)
        )

    trozos = []
    if desde:
        trozos.append(f"desde {desde:%d/%m/%Y}")
    if hasta:
        trozos.append(f"hasta {hasta:%d/%m/%Y}")
    if categoria.isdigit():
        cat = Categoria.objects.filter(pk=categoria).values_list("nombre", flat=True).first()
        if cat:
            trozos.append(f"categoría {cat}")
    if prioridad in dict(Ticket.Prioridad.choices):
        trozos.append(f"prioridad {prioridad}")
    if tecnico.isdigit():
        nombre_tec = User.objects.filter(pk=tecnico).values_list("nombre", flat=True).first()
        if nombre_tec:
            trozos.append(f"técnico {nombre_tec}")
    if usuario:
        trozos.append(f"usuario «{usuario}»")

    return {
        "desde": desde,
        "hasta": hasta,
        "categoria": categoria,
        "prioridad": prioridad,
        "tecnico": tecnico,
        "usuario": usuario,
        "filtros_txt": ", ".join(trozos) or "Sin filtros",
    }, qs


def _reportes_metricas_kpis(tickets):
    abiertos = en_progreso = resueltos = cerrados = 0
    vencidos = sla_ok = sla_no = 0
    for t in tickets:
        if t.estado == Ticket.Estado.ABIERTO:
            abiertos += 1
        elif t.estado == Ticket.Estado.EN_PROGRESO:
            en_progreso += 1
        elif t.estado == Ticket.Estado.RESUELTO:
            resueltos += 1
        elif t.estado == Ticket.Estado.CERRADO:
            cerrados += 1
        estado_ans = t.info_ans[0] if t.info_ans else None
        if estado_ans == "vencido":
            vencidos += 1
            sla_no += 1
        elif estado_ans == "ok":
            sla_ok += 1
    total = abiertos + en_progreso + resueltos + cerrados
    base_sla = sla_ok + sla_no
    return {
        "total": total,
        "abiertos": abiertos,
        "en_progreso": en_progreso,
        "resueltos": resueltos,
        "cerrados": cerrados,
        "vencidos": vencidos,
        "sla_ok": sla_ok,
        "sla_no": sla_no,
        "pct_sla": round(sla_ok / base_sla * 100) if base_sla else 0,
    }


def _reportes_metricas_tecnicos(tickets):
    abiertos_estados = (Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO)
    grupos = {}
    for t in tickets:
        nombre = t.tecnico_asignado.nombre if t.tecnico_asignado else "Sin asignar"
        g = grupos.setdefault(
            nombre,
            {"asignados": 0, "resueltos": 0, "en_curso": 0, "horas": 0.0, "n_cerrados": 0},
        )
        g["asignados"] += 1
        if t.estado in abiertos_estados:
            g["en_curso"] += 1
        if t.estado in (Ticket.Estado.RESUELTO, Ticket.Estado.CERRADO):
            g["resueltos"] += 1
        if t.fecha_cierre and t.fecha_creacion:
            horas = (t.fecha_cierre - t.fecha_creacion).total_seconds() / 3600.0
            if horas >= 0:
                g["horas"] += horas
                g["n_cerrados"] += 1
    filas = []
    for nombre, g in grupos.items():
        filas.append(
            {
                "nombre": nombre,
                "asignados": g["asignados"],
                "resueltos": g["resueltos"],
                "en_curso": g["en_curso"],
                "prom_h": round(g["horas"] / g["n_cerrados"], 2) if g["n_cerrados"] else None,
                "pct_resueltos": round(g["resueltos"] / g["asignados"] * 100) if g["asignados"] else 0,
            }
        )
    filas.sort(key=lambda r: r["asignados"], reverse=True)
    return filas


def _reportes_metricas_usuarios(tickets):
    grupos = {}
    for t in tickets:
        nombre = t.solicitante_nombre or t.solicitante_email or "Anónimo"
        g = grupos.setdefault(
            nombre,
            {
                "nombre": nombre,
                "email": t.solicitante_email or "",
                "creados": 0,
                "abiertos": 0,
                "resueltos": 0,
                "cerrados": 0,
                "horas": 0.0,
                "n_cerrados": 0,
                "ultimo_estado": "",
                "ultimo_fecha": None,
            },
        )
        g["creados"] += 1
        if t.estado == Ticket.Estado.ABIERTO:
            g["abiertos"] += 1
        elif t.estado == Ticket.Estado.RESUELTO:
            g["resueltos"] += 1
        elif t.estado == Ticket.Estado.CERRADO:
            g["cerrados"] += 1
        if not g["ultimo_fecha"] or (t.fecha_creacion and t.fecha_creacion > g["ultimo_fecha"]):
            g["ultimo_fecha"] = t.fecha_creacion
            g["ultimo_estado"] = t.get_estado_display()
        if t.fecha_cierre and t.fecha_creacion:
            horas = (t.fecha_cierre - t.fecha_creacion).total_seconds() / 3600.0
            if horas >= 0:
                g["horas"] += horas
                g["n_cerrados"] += 1
    filas = sorted(grupos.values(), key=lambda g: g["creados"], reverse=True)
    for g in filas:
        g["prom_h"] = round(g["horas"] / g["n_cerrados"], 2) if g["n_cerrados"] else None
    return filas


@admin_required
def reportes(request):
    f, qs = _reportes_filtros(request)
    tickets = list(qs.order_by("-fecha_creacion")[:2000])

    kpis = _reportes_metricas_kpis(tickets)
    tecnicos = _reportes_metricas_tecnicos(tickets)
    usuarios = _reportes_metricas_usuarios(tickets)

    cat_counts = Counter(
        (t.categoria.nombre if t.categoria else "Sin categoría") for t in tickets
    )
    colores_cat = ["#D62B1F", "#F26522", "#F2A900", "#2F7D4F", "#2A6FDB", "#7B5CD6", "#B7791F", "#3E7B9E"]
    categorias_pie = {
        "labels": [k for k, _ in cat_counts.most_common(8)],
        "data": [v for _, v in cat_counts.most_common(8)],
        "colores": colores_cat[: len(cat_counts)],
    }
    tec_chart = {
        "labels": [r["nombre"] for r in tecnicos],
        "asignados": [r["asignados"] for r in tecnicos],
        "resueltos": [r["resueltos"] for r in tecnicos],
    }

    filtros_tecnicos = (
        User.objects.filter(activo=True, rol__in=["admin", "tecnico"])
        .order_by("nombre")
        .values("id", "nombre")
    )
    usuarios_unicos = (
        Ticket.objects.values("solicitante_nombre", "solicitante_email")
        .distinct()
        .order_by("solicitante_nombre")[:400]
    )

    return render(
        request,
        "tickets/reportes.html",
        {
            "kpis": kpis,
            "tecnicos": tecnicos,
            "usuarios": usuarios,
            "tec_chart_json": json.dumps(tec_chart),
            "categorias_pie_json": json.dumps(categorias_pie),
            "f": f,
            "filtros_txt": f["filtros_txt"],
            "filtros_categorias": Categoria.objects.filter(activo=True).order_by("grupo", "nombre"),
            "filtros_tecnicos": filtros_tecnicos,
            "filtros_usuarios": usuarios_unicos,
            "prioridad_choices": Ticket.Prioridad.choices,
            "querystring": request.GET.urlencode(),
        },
    )


@admin_required
def exportar_reportes(request):
    f, qs = _reportes_filtros(request)
    tickets = list(qs.order_by("fecha_creacion")[:5000])
    kpis = _reportes_metricas_kpis(tickets)
    tecnicos = _reportes_metricas_tecnicos(tickets)
    usuarios = _reportes_metricas_usuarios(tickets)

    kpi_rows = [
        ("Tickets en el reporte", kpis["total"]),
        ("Abiertos", kpis["abiertos"]),
        ("En progreso", kpis["en_progreso"]),
        ("Resueltos", kpis["resueltos"]),
        ("Cerrados", kpis["cerrados"]),
        ("Vencidos (ANS)", kpis["vencidos"]),
        ("SLA cumplidos", kpis["sla_ok"]),
        ("SLA incumplidos", kpis["sla_no"]),
    ]
    tec_rows = [
        (
            r["nombre"],
            r["asignados"],
            r["resueltos"],
            r["en_curso"],
            r["prom_h"] if r["prom_h"] is not None else "",
            f"{r['pct_resueltos']}%",
        )
        for r in tecnicos
    ]
    usu_rows = [
        (
            r["nombre"],
            r["email"],
            r["creados"],
            r["abiertos"],
            r["resueltos"],
            r["cerrados"],
            r["ultimo_estado"],
            r["prom_h"] if r["prom_h"] is not None else "",
        )
        for r in usuarios
    ]
    return generar_excel_reportes(kpi_rows, tec_rows, usu_rows, tickets, f["filtros_txt"])


@staff_required
def exportar_tickets_admin(request):
    qs = Ticket.objects.select_related("categoria", "tecnico_asignado")
    estado = request.GET.get("estado")
    prioridad = request.GET.get("prioridad")
    categoria = request.GET.get("categoria")
    tecnico = request.GET.get("tecnico")
    if estado:
        qs = qs.filter(estado=estado)
    if prioridad:
        qs = qs.filter(prioridad=prioridad)
    if categoria:
        qs = qs.filter(categoria_id=categoria)
    if tecnico:
        qs = qs.filter(tecnico_asignado_id=tecnico)
    tickets = qs.order_by("-fecha_creacion")
    return generar_excel_tickets(tickets, titulo="Dogger Helpdesk · Reporte de Tickets")


@staff_required
def categorias_arbol(request):
    return render(
        request,
        "tickets/categorias.html",
        {
            "arbol": Categoria.arbol(),
            "inactivos": Categoria.objects.filter(activo=False).order_by("grupo", "nombre"),
            "grupos_existentes": (
                Categoria.objects.order_by("grupo")
                .values_list("grupo", flat=True).distinct()
            ),
            "form": CategoriaForm(),
            "prioridad_choices": Ticket.Prioridad.choices,
            "tecnicos": User.objects.filter(
                activo=True, rol__in=["admin", "tecnico"]
            ).order_by("nombre"),
        },
    )


@staff_required
@require_POST
def categoria_crear(request):
    form = CategoriaForm(request.POST)
    if form.is_valid():
        categoria = form.save(commit=False)
        categoria.activo = True
        try:
            categoria.save()
            messages.success(request, f"Categoría '{categoria}' creada.")
        except Exception:
            messages.error(request, "Ya existe esa subcategoría en el grupo.")
    else:
        errores = " ".join("; ".join(e) for e in form.errors.values())
        messages.error(request, f"Revisa los datos: {errores}")
    return redirect("tickets:categorias_arbol")


@staff_required
@require_POST
def categoria_toggle(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)
    categoria.activo = not categoria.activo
    categoria.save(update_fields=["activo"])
    estado_txt = "activada" if categoria.activo else "desactivada (oculta en el portal)"
    messages.success(request, f"Categoría '{categoria.nombre}' {estado_txt}.")
    return redirect("tickets:categorias_arbol")


@staff_required
@require_POST
def categoria_actualizar(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)
    nombre = request.POST.get("nombre", "").strip()
    grupo = request.POST.get("grupo", "").strip()
    glpi_id = request.POST.get("glpi_category_id", "").strip()
    tecnico_id = request.POST.get("tecnico_default", "").strip()
    if not nombre or not grupo:
        messages.error(request, "Grupo y nombre son obligatorios.")
        return redirect("tickets:categorias_arbol")
    duplicada = Categoria.objects.filter(grupo__iexact=grupo, nombre__iexact=nombre).exclude(pk=pk).exists()
    if duplicada:
        messages.error(request, f"Ya existe '{nombre}' en el grupo '{grupo}'.")
        return redirect("tickets:categorias_arbol")
    categoria.nombre = nombre
    categoria.grupo = grupo
    categoria.glpi_category_id = int(glpi_id) if glpi_id.isdigit() else None
    categoria.tecnico_default_id = int(tecnico_id) if tecnico_id.isdigit() else None
    prioridad = request.POST.get("prioridad_default", "").strip()
    if prioridad in dict(Ticket.Prioridad.choices):
        categoria.prioridad_default = prioridad
    ans_horas = request.POST.get("ans_horas", "").strip()
    if ans_horas.isdigit() and int(ans_horas) > 0:
        categoria.ans_horas = int(ans_horas)
    try:
        categoria.save()
        messages.success(request, f"Categoría actualizada: {categoria}.")
    except Exception:
        messages.error(request, "No se pudo actualizar la categoría.")
    return redirect("tickets:categorias_arbol")


@staff_required
@require_POST
def categoria_eliminar(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)
    n_tickets = categoria.tickets.count()
    if n_tickets:
        messages.error(
            request,
            f"No se puede eliminar '{categoria.nombre}': tiene {n_tickets} ticket(s) "
            f"asociado(s). Desactívala para ocultarla del portal.",
        )
        return redirect("tickets:categorias_arbol")
    nombre = categoria.nombre
    categoria.delete()
    messages.success(request, f"Categoría '{nombre}' eliminada.")
    return redirect("tickets:categorias_arbol")


# ---------------------------------------------------------------------------
# Administración de cuentas (solo administrador)
# ---------------------------------------------------------------------------
@admin_required
def usuarios_lista(request):
    import time
    from django.conf import settings as dj_settings

    q = request.GET.get("q", "").strip()
    tab = request.GET.get("rol", "").strip()

    # Auto-sincronización con GLPI al abrir el panel (sin pulsar botones).
    # Máximo una consulta cada 45 s salvo ?force_glpi=1.
    if dj_settings.GLPI.get("enabled"):
        forzado = request.GET.get("force_glpi") == "1"
        ahora = time.time()
        ultima = request.session.get("_glpi_usuarios_sync", 0)
        if forzado or (ahora - ultima) > 45:
            request.session["_glpi_usuarios_sync"] = ahora
            try:
                conteos, error = _glpi_sincronizar_cuentas()
            except Exception as exc:  # nunca romper la carga del panel
                conteos, error = None, f"error inesperado: {exc}"
            if conteos and (conteos["creados"] or conteos["sincronizados"]):
                messages.info(
                    request,
                    "GLPI sincronizado automáticamente: "
                    f"{conteos['creados']} cuenta(s) nueva(s), "
                    f"{conteos['sincronizados']} estado(s) actualizado(s).",
                )

    usuarios = (
        User.objects.all()
        .annotate(n_tickets=Count("tickets_asignados"))
        .order_by("rol", "nombre")
    )
    if tab == "usuario":
        usuarios = usuarios.filter(rol="usuario")
    elif tab == "tecnico":
        usuarios = usuarios.filter(rol__in=["tecnico", "admin"])
    if q:
        # Búsqueda por palabras separadas: cada término debe coincidir
        for palabra in q.split():
            usuarios = usuarios.filter(
                Q(nombre__icontains=palabra) | Q(email__icontains=palabra)
            )

    pp_us = _resolve_per_page(request, "per_page", 5)
    page_obj = _paginar(usuarios, request, per_page_default=pp_us)

    # ---- Ficha por usuario: estadísticas de tickets, ubicación, actividad,
    #      y (para técnicos) permisos, disponibilidad, tareas/eventos y alertas ----
    from apps.programador.models import CalendarioEvento, DisponibilidadTecnico

    def _tipo_label(v):
        return dict(CalendarioEvento.Tipo.choices).get(v, v)

    def _acceso_label(dt, ref):
        if not dt:
            return "Nunca"
        seg = (ref - dt).total_seconds()
        if seg < 60:
            return "recientemente"
        minutos = int(seg // 60)
        if minutos < 60:
            return f"hace {minutos} min"
        horas, m = divmod(minutos, 60)
        if seg < 86400:
            return f"hace {horas} h {m} min"
        return dt.strftime("%d/%m/%Y")

    hoy = date.today()
    ahora = timezone.now()
    hace_10min = ahora - timedelta(minutes=10)
    hace_7d = ahora - timedelta(days=7)
    fin_eventos = hoy + timedelta(days=14)

    en_pagina = [u.pk for u in page_obj.object_list]
    emails = [u.email.lower() for u in page_obj.object_list if u.email]
    stats_tickets = {}
    punto_mas_comun = {}
    if emails:
        stats_tickets = {
            r["solicitante_email"]: r
            for r in Ticket.objects.filter(solicitante_email__in=emails)
            .values("solicitante_email")
            .annotate(
                total=Count("pk"),
                abiertos=Count("pk", filter=Q(estado=Ticket.Estado.ABIERTO)),
                progreso=Count("pk", filter=Q(estado=Ticket.Estado.EN_PROGRESO)),
                resueltos=Count("pk", filter=Q(estado=Ticket.Estado.RESUELTO)),
                cerrados=Count("pk", filter=Q(estado=Ticket.Estado.CERRADO)),
            )
        }
        _puntos = {}
        for email, punto in Ticket.objects.filter(
            solicitante_email__in=emails
        ).exclude(solicitante_punto__in=[None, ""]).values_list("solicitante_email", "solicitante_punto"):
            _puntos.setdefault(email, Counter())[punto] += 1
        punto_mas_comun = {em: c.most_common(1)[0][0] for em, c in _puntos.items()}

    disp_por_tec = {}
    evts_por_tec = {}
    vencidos_por_tec = {}
    if tab == "tecnico" and en_pagina:
        for d in DisponibilidadTecnico.objects.filter(
            tecnico_id__in=en_pagina, fecha__gte=hoy
        ).order_by("fecha", "tecnico_id"):
            disp_por_tec.setdefault(d.tecnico_id, []).append(d)
        for e in CalendarioEvento.objects.filter(
            tecnico_id__in=en_pagina, fecha__gte=hoy, fecha__lte=fin_eventos
        ).order_by("fecha", "hora").select_related("ticket"):
            evts_por_tec.setdefault(e.tecnico_id, []).append(e)
        # Vencidos se calcula en Python porque fecha_limite_ans es propiedad
        for tk in (
            Ticket.objects.filter(
                tecnico_asignado_id__in=en_pagina,
                estado__in=[Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO],
            )
            .select_related("tecnico_asignado")
            .order_by("-fecha_creacion")[:300]
        ):
            if tk.fecha_limite_ans and tk.fecha_limite_ans < ahora:
                vencidos_por_tec.setdefault(tk.tecnico_asignado_id, []).append(tk)

    for u in page_obj.object_list:
        em = (u.email or "").lower()
        st = stats_tickets.get(em) or {}
        u.ficha = {
            "stats": st,
            "punto": punto_mas_comun.get(em, ""),
            "es_nuevo": bool(u.fecha_creacion and u.fecha_creacion >= hace_7d),
            "en_linea": bool(u.last_login and u.last_login >= hace_10min),
            "ultimo_acceso": u.last_login,
            "registrado": u.fecha_creacion,
            "permisos": {
                "es_staff": u.is_staff,
                "borrar_glpi": u.borrar_glpi_al_eliminar,
            },
            "disponibilidad": disp_por_tec.get(u.pk, []),
            "eventos": evts_por_tec.get(u.pk, [])[:6],
        }
        # Indicador junto al nombre: verde = activo con actividad reciente,
        # gris = activo sin actividad, rojo = inactivo, sin punto = nunca ingresó.
        ultimo_login = u.last_login
        if ultimo_login is None:
            u.ficha["dot"] = ""
            u.ficha["dot_puede"] = False
        elif not u.activo:
            u.ficha["dot"] = "red"
            u.ficha["dot_puede"] = False
        else:
            u.ficha["dot_puede"] = True
            u.ficha["dot"] = "green" if u.ficha["en_linea"] else "gray"
        u.ficha["acceso_label"] = _acceso_label(ultimo_login, ahora)
        if u.rol in ("tecnico", "admin"):
            alertas = [
                {
                    "tipo": "vencido",
                    "texto": f"Ticket {tk.codigo} vencido",
                    "url": reverse("tickets:detalle", args=[tk.pk]),
                }
                for tk in vencidos_por_tec.get(u.pk, [])
            ]
            tope_ausencia = hoy + timedelta(days=3)
            for d in u.ficha["disponibilidad"]:
                if d.tipo in ("ausencia", "falta") and d.fecha <= tope_ausencia:
                    alertas.append(
                        {
                            "tipo": "ausencia",
                            "texto": f"{d.get_tipo_display()} el {DateFormat(d.fecha).format('j M')}"
                            + (f" · {d.nota}" if d.nota else ""),
                        }
                    )
            u.ficha["alertas"] = alertas[:6]
        else:
            u.ficha["alertas"] = []

    # Búsqueda en vivo del perfil en GLPI (pestaña Técnicos con texto de búsqueda)
    perfiles_encontrados = 0
    if tab == "tecnico" and q and dj_settings.GLPI.get("enabled"):
        client = GlpiClient()
        if client.available:
            try:
                client.init_session()
                remotos = client.list_users()
            except Exception:
                remotos = []
            finally:
                client.kill_session()

            def _norm(txt):
                return (txt or "").strip().lower()

            for u in page_obj.object_list:
                u.correo_provisional = (u.email or "").endswith("@glpi.local")
                perfil = None
                for r in remotos:
                    coincide = (
                        (_norm(r["email"]) and _norm(r["email"]) == _norm(u.email))
                        or (_norm(r["login"]) and _norm(r["login"]) == _norm(u.email.split("@")[0]))
                        or (_norm(r["nombre_real"]) and _norm(r["nombre_real"]) in _norm(u.nombre))
                        or (_norm(r["nombre_real"]) and _norm(u.nombre) in _norm(r["nombre_real"]))
                    )
                    if coincide:
                        perfil = r
                        break
                if perfil:
                    u.glpi_perfil = perfil
                    perfiles_encontrados += 1
                    if not u.glpi_user_id and perfil["glpi_id"]:
                        u.glpi_user_id = perfil["glpi_id"]
                        u.save(update_fields=["glpi_user_id"])
                    # Confirmación de estado: lo que diga GLPI manda
                    if perfil["activo_glpi"] is not None and u.activo != perfil["activo_glpi"]:
                        u.activo = perfil["activo_glpi"]
                        u.is_active = perfil["activo_glpi"]
                        u.save(update_fields=["activo", "is_active"])
                        messages.warning(
                            request,
                            f"{u.nombre}: estado actualizado a "
                            f"{'Activo' if u.activo else 'Inactivo'} según su perfil en GLPI.",
                        )
            if perfiles_encontrados:
                messages.info(
                    request,
                    f"{perfiles_encontrados} perfil(es) traídos en vivo desde GLPI para «{q}».",
                )

    glpi_base = ""
    if dj_settings.GLPI.get("enabled"):
        glpi_base = dj_settings.GLPI["base_url"].split("/apirest.php")[0].rstrip("/")

    # Técnicos en GLPI que aún no están en el aplicativo:
    # en la pestaña Técnicos se muestran siempre (con búsqueda, solo coincidencias)
    # para poder importarlos / verlos junto a los internos.
    glpi_remotos = []
    glpi_error = ""
    if tab == "tecnico" and glpi_base:
        palabras = [p.lower() for p in q.split()] if q else None
        ids_locales = set(
            User.objects.exclude(glpi_user_id=None).values_list("glpi_user_id", flat=True)
        )
        correos_locales = set(User.objects.values_list("email", flat=True))
        try:
            client = GlpiClient()
            remotos = []
            if client.available:
                client.init_session()
                remotos = client.list_users()
                client.kill_session()
        except Exception as exc:
            remotos = []
            glpi_error = str(exc)[:200] or "GLPI no responde."
        for r in remotos:
            texto = f"{r['login']} {r['nombre_real']} {r['email']}".lower()
            if palabras and not all(p in texto for p in palabras):
                continue
            if r["glpi_id"] in ids_locales:
                continue
            correo_real = r["email"].lower() if "@" in r["email"] else ""
            if correo_real and correo_real in correos_locales:
                continue
            glpi_remotos.append(r)
            if not palabras and len(glpi_remotos) >= 12:
                break
        glpi_remotos = glpi_remotos[:12]

    return render(
        request,
        "tickets/usuarios.html",
        {
            "usuarios": page_obj.object_list,
            "page_obj": page_obj,
            "querystring": _params_sin_page(request),
            "q": q,
            "tab": tab,
            "total": User.objects.count(),
            "n_usuarios_finales": User.objects.filter(rol="usuario").count(),
            "n_tecnicos": User.objects.filter(rol__in=["tecnico", "admin"]).count(),
            "n_tecnicos_glpi": User.objects.filter(
                rol__in=["tecnico", "admin"], glpi_user_id__isnull=False
            ).count(),
            "glpi_base": glpi_base,
            "glpi_remotos": glpi_remotos,
            "glpi_error": glpi_error,
            "per_page": pp_us,
            "tipo_label": _tipo_label,
            "hoy": date.today(),
            "n_nuevos": User.objects.filter(fecha_creacion__gte=hace_7d).count(),
            "n_en_linea": User.objects.filter(last_login__gte=hace_10min).count(),
        },
    )


@staff_required
def usuarios_estado_api(request):
    """Estado 'en tiempo real' de las cuentas visibles: actividad y registro.

    El panel consulta este endpoint cada pocos segundos para refrescar
    los indicadores de usuarios nuevos y de quienes están usando la web.
    """
    ids = [int(x) for x in request.GET.get("ids", "").split(",") if x.strip().isdigit()]
    ahora = timezone.now()
    hace_10min = ahora - timedelta(minutes=10)
    hace_7d = ahora - timedelta(days=7)
    datos = {}
    for u in User.objects.filter(pk__in=ids):
        datos[str(u.pk)] = {
            "activo": u.activo,
            "es_staff": u.is_staff,
            "nuevo": bool(u.fecha_creacion and u.fecha_creacion >= hace_7d),
            "en_linea": bool(u.last_login and u.last_login >= hace_10min),
            "ultimo_acceso": u.last_login.isoformat() if u.last_login else None,
        }
    return JsonResponse({"ok": True, "usuarios": datos})


def _ficha_usuario(u):
    """Construye el dict `ficha` de una cuenta (mismos campos que en usuarios_lista).

    Se usa para servir la ficha dinámica (modal) de una fila concreta.
    """
    from apps.programador.models import CalendarioEvento, DisponibilidadTecnico

    ahora = timezone.now()
    hoy = date.today()
    hace_10min = ahora - timedelta(minutes=10)
    hace_7d = ahora - timedelta(days=7)
    fin_eventos = hoy + timedelta(days=14)
    email = (u.email or "").lower()

    def _acceso_label(dt, ref):
        if not dt:
            return "Nunca"
        seg = (ref - dt).total_seconds()
        if seg < 60:
            return "recientemente"
        minutos = int(seg // 60)
        if minutos < 60:
            return f"hace {minutos} min"
        horas, m = divmod(minutos, 60)
        if seg < 86400:
            return f"hace {horas} h {m} min"
        return dt.strftime("%d/%m/%Y")

    stats = {}
    punto = ""
    if u.rol in ("tecnico", "admin"):
        # Para técnicos la estadística son los tickets asignados a su carga.
        tk_qs = Ticket.objects.filter(tecnico_asignado_id=u.pk)
        stats = {
            r["tecnico_asignado_id"]: r
            for r in tk_qs.values("tecnico_asignado_id")
            .annotate(
                total=Count("pk"),
                abiertos=Count("pk", filter=Q(estado=Ticket.Estado.ABIERTO)),
                progreso=Count("pk", filter=Q(estado=Ticket.Estado.EN_PROGRESO)),
                resueltos=Count("pk", filter=Q(estado=Ticket.Estado.RESUELTO)),
                cerrados=Count("pk", filter=Q(estado=Ticket.Estado.CERRADO)),
            )
        }.get(u.pk) or {}
    elif email:
        tk_qs = Ticket.objects.filter(solicitante_email=email)
        stats = {
            r["solicitante_email"]: r
            for r in tk_qs.values("solicitante_email")
            .annotate(
                total=Count("pk"),
                abiertos=Count("pk", filter=Q(estado=Ticket.Estado.ABIERTO)),
                progreso=Count("pk", filter=Q(estado=Ticket.Estado.EN_PROGRESO)),
                resueltos=Count("pk", filter=Q(estado=Ticket.Estado.RESUELTO)),
                cerrados=Count("pk", filter=Q(estado=Ticket.Estado.CERRADO)),
            )
        }.get(email) or {}
        cuentas = Counter(
            tk_qs.exclude(solicitante_punto__in=[None, ""]).values_list("solicitante_punto", flat=True)
        )
        if cuentas:
            punto = cuentas.most_common(1)[0][0]

    ficha = {
        "stats": stats,
        "punto": punto,
        "es_nuevo": bool(u.fecha_creacion and u.fecha_creacion >= hace_7d),
        "en_linea": bool(u.last_login and u.last_login >= hace_10min),
        "ultimo_acceso": u.last_login,
        "registrado": u.fecha_creacion,
        "permisos": {
            "es_staff": u.is_staff,
            "borrar_glpi": u.borrar_glpi_al_eliminar,
        },
        "disponibilidad": [],
        "eventos": [],
        "alertas": [],
    }

    ultimo_login = u.last_login
    if ultimo_login is None:
        ficha["dot"] = ""
        ficha["dot_puede"] = False
    elif not u.activo:
        ficha["dot"] = "red"
        ficha["dot_puede"] = False
    else:
        ficha["dot_puede"] = True
        ficha["dot"] = "green" if ficha["en_linea"] else "gray"
    ficha["acceso_label"] = _acceso_label(ultimo_login, ahora)

    if u.rol in ("tecnico", "admin"):
        disp = list(
            DisponibilidadTecnico.objects.filter(tecnico_id=u.pk, fecha__gte=hoy).order_by("fecha")
        )
        evts = list(
            CalendarioEvento.objects.filter(tecnico_id=u.pk, fecha__gte=hoy, fecha__lte=fin_eventos)
            .order_by("fecha", "hora")
            .select_related("ticket")
        )
        vencidos = []
        for tk in (
            Ticket.objects.filter(
                tecnico_asignado_id=u.pk,
                estado__in=[Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO],
            )
            .select_related("tecnico_asignado")
            .order_by("-fecha_creacion")[:300]
        ):
            if tk.fecha_limite_ans and tk.fecha_limite_ans < ahora:
                vencidos.append(tk)
        alertas = [
            {
                "tipo": "vencido",
                "texto": f"Ticket {tk.codigo} vencido",
                "url": reverse("tickets:detalle", args=[tk.pk]),
            }
            for tk in vencidos
        ]
        tope_ausencia = hoy + timedelta(days=3)
        for d in disp:
            if d.tipo in ("ausencia", "falta") and d.fecha <= tope_ausencia:
                alertas.append(
                    {
                        "tipo": "ausencia",
                        "texto": f"{d.get_tipo_display()} el {DateFormat(d.fecha).format('j M')}"
                        + (f" a las {d.hora.strftime('%H:%M')}" if d.hora else "")
                        + (f" · {d.nota}" if d.nota else ""),
                    }
                )
        ficha["disponibilidad"] = disp
        ficha["eventos"] = evts[:6]
        ficha["alertas"] = alertas[:6]
    return ficha


@admin_required
def usuario_ficha_api(request, pk):
    """Ficha de una cuenta (AJAX): ID GLPI, estado, estadísticas y tareas asignadas."""
    u = get_object_or_404(User, pk=pk)
    u.ficha = _ficha_usuario(u)
    html = render(request, "tickets/_ficha_usuario.html", {"u": u}).content.decode("utf-8")
    return JsonResponse({"ok": True, "html": html})


@admin_required
@require_POST
def usuario_importar_uno(request, glpi_id):
    """
    Trae UN perfil concreto de GLPI y crea su cuenta local al instante.
    Reutiliza la sincronización completa (barata y mantiene el espejo de estados).
    """
    conteos, error = _glpi_sincronizar_cuentas()
    destino = None
    if not error:
        destino = User.objects.filter(glpi_user_id=glpi_id).first()
    if error:
        messages.error(request, f"No se pudo importar — {error}")
    elif destino is None:
        messages.warning(
            request,
            f"GLPI no expone un usuario con ID #{glpi_id} visible para el token API.",
        )
    else:
        messages.success(
            request,
            f"Perfil importado desde GLPI: {destino.nombre}"
            + (" — actívalo y define contraseña al editarlo ✏️." if not destino.activo else "."),
        )
    url = reverse("tickets:usuarios")
    qv = request.POST.get("q", "").strip()
    return redirect(f"{url}?rol=tecnico" + (f"&q={qv}" if qv else ""))


@admin_required
@require_POST
def usuario_crear_glpi(request, pk):
    """Publica en GLPI una cuenta técnica creada localmente."""
    usuario = get_object_or_404(User, pk=pk)
    if usuario.glpi_user_id:
        messages.info(request, f"'{usuario.nombre}' ya está vinculado a GLPI (#{usuario.glpi_user_id}).")
        return redirect("tickets:usuarios")
    client = GlpiClient()
    if not client.available:
        messages.error(request, "GLPI no está habilitado o falta configuración (.env).")
        return redirect("tickets:usuarios")
    try:
        client.init_session()
        glpi_id = client.create_user(usuario.nombre, usuario.email)
    except GlpiError as exc:
        messages.error(request, f"No se pudo crear en GLPI: {exc}")
        return redirect("tickets:usuarios")
    finally:
        client.kill_session()
    usuario.glpi_user_id = glpi_id
    usuario.save(update_fields=["glpi_user_id"])
    messages.success(request, f"'{usuario.nombre}' creado en GLPI con id #{glpi_id}.")
    return redirect("tickets:usuarios")


def _aplicar_usuario_panel(user, form, password):
    user.nombre = form.cleaned_data["nombre"]
    user.email = form.cleaned_data["email"]
    user.rol = form.cleaned_data["rol"]
    glpi_id = form.cleaned_data.get("glpi_user_id")
    user.glpi_user_id = glpi_id or None
    user.telefono = (form.cleaned_data.get("telefono") or "").strip()
    user.ubicacion = (form.cleaned_data.get("ubicacion") or "").strip()
    user.activo = form.cleaned_data.get("activo", False)
    user.is_active = user.activo
    if user.rol in ("admin", "tecnico"):
        user.is_staff = True
    else:
        user.is_staff = False
    if password:
        user.set_password(password)
    user.save()


@admin_required
@require_POST
def usuario_sync_glpi(request, pk):
    """
    Trae de GLPI los datos actuales del técnico vinculado
    (nombre, correo y estado activo/inactivo) y los aplica localmente.
    """
    usuario = get_object_or_404(User, pk=pk)
    if not usuario.glpi_user_id:
        messages.warning(request, f"{usuario.nombre} no tiene ID de GLPI vinculado.")
        return redirect("tickets:usuarios")

    client = GlpiClient()
    if not client.available:
        messages.error(request, "GLPI no está habilitado o falta configuración (.env).")
        return redirect("tickets:usuarios")
    try:
        client.init_session()
        remotos = client.list_users()
    except GlpiError as exc:
        messages.error(request, f"No se pudo consultar GLPI: {exc}")
        return redirect("tickets:usuarios")
    finally:
        client.kill_session()

    perfil = next((r for r in remotos if r["glpi_id"] == usuario.glpi_user_id), None)
    if not perfil:
        messages.error(
            request,
            f"El ID GLPI #{usuario.glpi_user_id} de {usuario.nombre} ya no existe o "
            f"no es visible para el token API.",
        )
        return redirect("tickets:usuarios")

    cambios = []
    if perfil["nombre_real"] and perfil["nombre_real"] != usuario.nombre:
        usuario.nombre = perfil["nombre_real"]
        cambios.append(f"nombre → {perfil['nombre_real']}")
    if perfil["email"] and "@" in perfil["email"] and perfil["email"].lower() != usuario.email.lower():
        usuario.email = perfil["email"].lower()
        cambios.append(f"correo → {usuario.email}")
    if perfil["activo_glpi"] is not None and usuario.activo != perfil["activo_glpi"]:
        usuario.activo = perfil["activo_glpi"]
        usuario.is_active = perfil["activo_glpi"]
        cambios.append(f"estado → {'Activo' if usuario.activo else 'Inactivo'} (según GLPI)")
    if cambios:
        usuario.save()
        messages.success(
            request,
            f"{usuario.nombre}: se actualizaron {len(cambios)} campo(s) desde GLPI — " + "; ".join(cambios) + ".",
        )
    else:
        messages.info(request, f"{usuario.nombre}: ya estaba igual que en GLPI.")
    return redirect("tickets:usuarios")


@admin_required
@require_POST
def usuario_guardar(request):
    pk = request.POST.get("pk") or None
    instancia = User.objects.filter(pk=pk).first() if pk else None
    form = UsuarioPanelForm(request.POST)
    if not form.is_valid():
        errores = " ".join("; ".join(e) for e in form.errors.values())
        messages.error(request, f"Revisa los datos del usuario: {errores}")
        return redirect("tickets:usuarios")

    email = form.cleaned_data["email"]
    existente_email = User.objects.filter(email__iexact=email).exclude(pk=instancia.pk if instancia else None).first()
    if existente_email:
        messages.error(request, f"El correo {email} ya está en uso por otra cuenta.")
        return redirect("tickets:usuarios")

    password = form.cleaned_data.get("password1") or ""
    if instancia is None:
        if not password:
            messages.error(request, "Para una cuenta nueva la contraseña es obligatoria.")
            return redirect("tickets:usuarios")
        try:
            user = User.objects.create_user(
                email=email,
                nombre=form.cleaned_data["nombre"],
                password=password,
                rol=form.cleaned_data["rol"],
                activo=form.cleaned_data.get("activo", True),
            )
        except Exception as exc:
            messages.error(request, f"No se pudo crear la cuenta: {exc}")
            return redirect("tickets:usuarios")
        _aplicar_usuario_panel(user, form, password=None)
        messages.success(request, f"Cuenta '{user.nombre}' creada ({user.get_rol_display()}).")
    else:
        _aplicar_usuario_panel(instancia, form, password=password or None)
        messages.success(request, f"Cuenta '{instancia.nombre}' actualizada.")
    return redirect("tickets:usuarios")


@admin_required
@require_POST
def usuario_toggle(request, pk):
    usuario = get_object_or_404(User, pk=pk)
    if usuario.pk == request.user.pk:
        messages.error(request, "No puedes desactivar tu propia cuenta.")
        return redirect("tickets:usuarios")
    usuario.activo = not usuario.activo
    usuario.is_active = usuario.activo
    usuario.save(update_fields=["activo", "is_active"])
    estado_txt = "activada" if usuario.activo else "desactivada"
    messages.success(request, f"Cuenta '{usuario.nombre}' {estado_txt}.")
    return redirect("tickets:usuarios")


@admin_required
@require_POST
def usuario_eliminar(request, pk):
    """Elimina definitivamente una cuenta. Los tickets asignados quedan sin técnico."""
    usuario = get_object_or_404(User, pk=pk)
    if usuario.pk == request.user.pk:
        messages.error(request, "No puedes eliminar tu propia cuenta.")
        return redirect("tickets:usuarios")
    if usuario.rol == "admin" and User.objects.filter(rol="admin", activo=True).exclude(pk=pk).count() == 0:
        messages.error(request, "No puedes eliminar al único administrador activo.")
        return redirect("tickets:usuarios")
    nombre = usuario.nombre
    n_asignados = usuario.tickets_asignados.count()
    usuario.delete()
    detalle = f" · {n_asignados} ticket(s) quedaron sin técnico" if n_asignados else ""
    messages.success(request, f"Cuenta '{nombre}' eliminada{detalle}.")
    return redirect("tickets:usuarios")


def _glpi_sincronizar_cuentas():
    """
    Refleja los técnicos visibles en GLPI como cuentas locales.
    Retorna ({conteos}, None) o (None, mensaje_de_error).
    """
    client = GlpiClient()
    if not client.available:
        return None, "GLPI no está habilitado o falta configuración (.env)."
    try:
        client.init_session()
        remotos = client.list_users()
    except GlpiError as exc:
        return None, (
            f"No se pudo consultar GLPI: {exc} "
            f"(revisa que el usuario API tenga permiso de lectura sobre Usuarios)"
        )
    except Exception as exc:
        # Nunca pantalla amarilla: explicar la causa exacta en el panel
        import traceback

        detalle = traceback.format_exc().strip().splitlines()[-3:]
        logger.exception("Error sincronizando cuentas desde GLPI")
        return None, (
            f"Error interno consultando GLPI → {type(exc).__name__}: {exc} · "
            f"{' | '.join(d.strip() for d in detalle)}"
        )
    finally:
        client.kill_session()

    if not remotos:
        return None, (
            "GLPI no devolvió ningún usuario visible para el token API configurado. "
            "Verifica en GLPI que los técnicos existan en la entidad raíz y que el "
            "perfil del usuario API pueda verlos (Administración → Usuarios)."
        )

    actualizados = creados = sin_correo = sincronizados = 0
    for remoto in remotos:
        try:
            glpi_id = int(remoto["glpi_id"])
            login = str(remoto.get("login") or "").strip()
            correo_remoto = str(remoto.get("email") or "").strip()
            nombre = (
                str(remoto.get("nombre_real") or "").strip()
                or login
                or f"Usuario GLPI {glpi_id}"
            )
        except (TypeError, ValueError, KeyError) as exc:
            logger.warning("Fila GLPI inválida descartada: %r (%s)", remoto, exc)
            continue

        if correo_remoto and "@" in correo_remoto:
            email = correo_remoto.lower()
        else:
            # Sin correo en GLPI: correo provisional para poder crear la cuenta.
            email = f"{login or f'glpi{glpi_id}'}@glpi.local"
            sin_correo += 1

        usuario = User.objects.filter(email__iexact=email).first()
        if not usuario:
            usuario = User.objects.filter(glpi_user_id=glpi_id).first()
        if usuario:
            cambios = []
            if usuario.glpi_user_id != glpi_id:
                usuario.glpi_user_id = glpi_id
                cambios.append("glpi_user_id")
            # Espejo del estado de la cuenta en GLPI ("Activo: Sí/No")
            if remoto.get("activo_glpi") is not None and bool(usuario.activo) != bool(
                remoto["activo_glpi"]
            ):
                usuario.activo = bool(remoto["activo_glpi"])
                usuario.is_active = bool(remoto["activo_glpi"])
                cambios.extend(["activo", "is_active"])
                sincronizados += 1
            # Nombre/correo vacíos localmente: completar desde GLPI
            if not (usuario.nombre or "").strip() and nombre:
                usuario.nombre = nombre
                cambios.append("nombre")
            if not (usuario.email or "") or usuario.email.endswith("@glpi.local"):
                if correo_remoto and "@" in correo_remoto:
                    usuario.email = correo_remoto.lower()
                    cambios.append("email")
            if cambios:
                usuario.save(update_fields=list(dict.fromkeys(cambios)))
            actualizados += 1
        else:
            User.objects.create_user(
                email=email,
                nombre=nombre,
                # Django 5 eliminó make_random_password: contraseña provisional aleatoria
                password="".join(
                    secrets.choice(string.ascii_letters + string.digits) for _ in range(12)
                ),
                rol="tecnico",
                activo=(remoto.get("activo_glpi") is not False),
                glpi_user_id=glpi_id,
            )
            creados += 1

    return {
        "creados": creados,
        "actualizados": actualizados,
        "sincronizados": sincronizados,
        "sin_correo": sin_correo,
        "total_glpi": len(remotos),
    }, None


@admin_required
def usuarios_importar_glpi(request):
    """Sincronización manual (enlace ↻ GLPI); el panel también lo hace automático."""
    conteos, error = _glpi_sincronizar_cuentas()
    if error:
        messages.error(request, f"Importación cancelada — {error}")
        return redirect("tickets:usuarios")
    resumen = (
        f"{conteos['creados']} cuenta(s) nueva(s) · "
        f"{conteos['actualizados']} vinculada(s)"
    )
    if conteos["sincronizados"]:
        resumen += f" · {conteos['sincronizados']} estado(s) actualizado(s) según GLPI"
    if conteos["sin_correo"]:
        resumen += (
            f" · {conteos['sin_correo']} sin correo en GLPI (correo provisional "
            f"@glpi.local: completa su correo y contraseña al editarlos)"
        )
    messages.success(request, f"Sincronización con GLPI lista: {resumen}.")
    return redirect("tickets:usuarios")


def faq(request):
    return render(request, "tickets/faq.html")


def politica_privacidad(request):
    return render(request, "tickets/politica_privacidad.html")


def portal(request):
    if request.method == "POST":
        form = TicketForm(request.POST, request.FILES)
        if form.is_valid():
            ticket = form.save()
            _auto_asignar_tecnico(ticket)
            if ticket.asignacion_automatica:
                ticket.save(update_fields=["tecnico_asignado", "asignacion_automatica"])
            files = form.cleaned_data.get("adjuntos") or []
            for f in files:
                TicketAdjunto.objects.create(
                    ticket=ticket,
                    nombre_original=f.name,
                    archivo=f,
                    mime_type=f.content_type or "application/octet-stream",
                    tamano_bytes=f.size,
                    subido_por=ticket.solicitante_nombre,
                )
            # Sync opcional a GLPI (no bloquea si falla)
            _sincronizar_ticket_nuevo(request, ticket, files)

            notificar_ticket_creado(ticket)

            n = len(files)
            msg = f"Ticket creado: {ticket.codigo}"
            if n:
                msg += f" · {n} archivo(s) adjunto(s)"
            messages.success(request, msg)
            return redirect("tickets:portal")
    else:
        form = TicketForm()

    context = {"form": form}
    return render(request, "tickets/portal.html", context)


def consultar_ticket(request):
    """Consulta publica por codigo HD-XXXX (sin datos internos)."""
    ticket = None
    form = ConsultaTicketForm(request.GET or None)
    if form.is_valid():
        codigo = form.cleaned_data["codigo"].strip().upper()
        ticket = (
            Ticket.objects.filter(codigo=codigo)
            .prefetch_related(
                Prefetch(
                    "comentarios",
                    queryset=TicketComentario.objects.filter(es_interno=False),
                )
            )
            .first()
        )
        if not ticket:
            messages.warning(request, f"No se encontro el ticket {codigo}")
    return render(
        request,
        "tickets/consultar.html",
        {"form": form, "ticket": ticket},
    )


@user_required
def mi_panel(request):
    initial = {
        "solicitante_nombre": request.user.nombre,
        "solicitante_email": request.user.email,
    }
    form = TicketForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        ticket = form.save(commit=False)
        ticket.solicitante_email = request.user.email
        ticket.solicitante_nombre = request.user.nombre or ticket.solicitante_nombre
        _auto_asignar_tecnico(ticket)
        ticket.save()
        if ticket.asignacion_automatica:
            messages.info(
                request,
                f"Asignado automáticamente a {ticket.tecnico_asignado.nombre} "
                f"según la categoría del problema.",
            )
        files = form.cleaned_data.get("adjuntos") or []
        for f in files:
            TicketAdjunto.objects.create(
                ticket=ticket,
                nombre_original=f.name,
                archivo=f,
                mime_type=f.content_type or "application/octet-stream",
                tamano_bytes=f.size,
                subido_por=ticket.solicitante_nombre,
            )
        _sincronizar_ticket_nuevo(request, ticket, files)
        notificar_ticket_creado(ticket)
        messages.success(request, f"Ticket creado: {ticket.codigo}")
        return redirect("tickets:mi_panel")

    tickets_qs = Ticket.objects.select_related("categoria", "tecnico_asignado").filter(
        solicitante_email=request.user.email
    )
    total_qs = tickets_qs.count()
    estado_filtro = request.GET.get("estado", "").strip()
    q_filtro = request.GET.get("q", "").strip()
    if estado_filtro:
        tickets_qs = tickets_qs.filter(estado=estado_filtro)
    if q_filtro:
        tickets_qs = tickets_qs.filter(
            Q(codigo__iexact=q_filtro.upper())
            | Q(titulo__icontains=q_filtro)
        )

    stats = {
        "total": total_qs,
        "abiertos": Ticket.objects.filter(solicitante_email=request.user.email, estado=Ticket.Estado.ABIERTO).count(),
        "en_progreso": Ticket.objects.filter(solicitante_email=request.user.email, estado=Ticket.Estado.EN_PROGRESO).count(),
        "resueltos": Ticket.objects.filter(
            solicitante_email=request.user.email,
            estado__in=[Ticket.Estado.RESUELTO, Ticket.Estado.CERRADO],
        ).count(),
    }
    pp_mp = _resolve_per_page(request, "per_page", 5)
    page_obj = _paginar(
        tickets_qs.annotate(_prioridad_orden=orden_prioridad_annotation()).order_by(
            "_prioridad_orden", "-fecha_creacion"
        ),
        request,
        per_page_default=pp_mp,
    )
    dashboard_context = _build_dashboard_context(request, list(page_obj.object_list))
    return render(
        request,
        "tickets/mi_panel.html",
        {
            "usuario": request.user,
            "saludo": "Bienvenida" if request.user.genero == "femenino" else "Bienvenido",
            "tickets": page_obj.object_list,
            "page_obj": page_obj,
            "querystring": _params_sin_page(request),
            "filtro_estado": estado_filtro,
            "q": q_filtro,
            "estados": Ticket.Estado.choices,
            "stats": stats,
            "form": form,
            "per_page": pp_mp,
            "cat_sugerencias_json": json.dumps(claves_para_json(), ensure_ascii=False),
            **dashboard_context,
        },
    )


@login_required
def crear_ticket(request):
    """
    Levantar un ticket con sesión iniciada (usuarios y staff).
    El staff puede crear en nombre de otro solicitante indicando sus datos.
    """
    es_usuario_final = request.user.rol == "usuario"
    initial = {
        "solicitante_nombre": request.user.nombre,
        "solicitante_email": request.user.email,
    }
    form = TicketForm(request.POST or None, request.FILES or None, initial=initial, permitir_modo=not es_usuario_final)
    if request.method == "POST" and form.is_valid():
        ticket = form.save(commit=False)
        if es_usuario_final:
            ticket.solicitante_email = request.user.email
            ticket.solicitante_nombre = request.user.nombre or ticket.solicitante_nombre
        _auto_asignar_tecnico(ticket)
        ticket.save()
        if ticket.asignacion_automatica:
            messages.info(
                request,
                f"Asignado automáticamente a {ticket.tecnico_asignado.nombre} "
                f"según categoría, prioridad y disponibilidad.",
            )
        files = form.cleaned_data.get("adjuntos") or []
        for f in files:
            TicketAdjunto.objects.create(
                ticket=ticket,
                nombre_original=f.name,
                archivo=f,
                mime_type=f.content_type or "application/octet-stream",
                tamano_bytes=f.size,
                subido_por=ticket.solicitante_nombre,
            )
        _sincronizar_ticket_nuevo(request, ticket, files)
        notificar_ticket_creado(ticket)
        request.session["ticket_creado_info"] = {
            "codigo": ticket.codigo,
            "titulo": ticket.titulo,
            "categoria": str(ticket.categoria) if ticket.categoria_id else "Sin categoría",
            "prioridad": ticket.prioridad,
            "prioridad_label": ticket.get_prioridad_display(),
            "tecnico_nombre": ticket.tecnico_asignado.nombre if ticket.tecnico_asignado_id else "",
            "tecnico_iniciales": ticket.tecnico_asignado.initials if ticket.tecnico_asignado_id else "",
        }
        messages.success(request, f"Ticket creado: {ticket.codigo}")
        return redirect("tickets:crear_ticket")

    return render(
        request,
        "tickets/crear_ticket.html",
        {
            "form": form,
            "es_usuario_final": es_usuario_final,
            "cat_sugerencias_json": json.dumps(claves_para_json(), ensure_ascii=False),
            "ans_categorias_json": json.dumps(
                [
                    {
                        "id": c.pk,
                        "prioridad": c.prioridad_default,
                        "ans": c.ans_horas or horas_por_prioridad(c.prioridad_default),
                    }
                    for c in Categoria.objects.filter(activo=True)
                ],
                ensure_ascii=False,
            ),
        },
    )


@user_required
def exportar_mis_tickets(request):
    tickets = Ticket.objects.select_related("categoria", "tecnico_asignado").filter(
        solicitante_email=request.user.email
    ).order_by("-fecha_creacion")
    return generar_excel_tickets(tickets, titulo=f"Mis tickets · {request.user.nombre}")


def _timeline_ticket(ticket, include_internos=False):
    """Feed cronológico unificado (chat): seguimientos públicos + eventos GLPI."""
    items = []
    for c in ticket.comentarios.all():
        if c.es_interno:
            if not include_internos:
                continue
            items.append(
                {
                    "tipo": "interno",
                    "fecha": c.fecha,
                    "autor": c.autor_nombre or (c.usuario.nombre if c.usuario_id else "Staff"),
                    "texto": c.comentario,
                }
            )
            continue
        es_usuario = bool(c.usuario_id and getattr(c.usuario, "rol", None) == "usuario")
        autor = c.autor_nombre or (c.usuario.nombre if c.usuario_id else "Mesa de ayuda")
        items.append(
            {
                "tipo": "usuario" if es_usuario else "soporte",
                "fecha": c.fecha,
                "autor": autor,
                "texto": c.comentario,
            }
        )
    for ev in ticket.eventos_glpi.all():
        items.append(
            {
                "tipo": "sistema",
                "fecha": ev.fecha,
                "autor": "GLPI",
                "texto": ev.descripcion,
                "evento": ev.tipo,
                "etiqueta": ev.get_tipo_display(),
            }
        )
    items.sort(key=lambda i: i["fecha"])
    return items


@user_required
def mi_ticket(request, pk):
    ticket = get_object_or_404(
        Ticket.objects.select_related("categoria").prefetch_related(
            "comentarios",
            "eventos_glpi",
            "adjuntos",
        ),
        pk=pk,
        solicitante_email=request.user.email,
    )
    timeline = _timeline_ticket(ticket)
    return render(
        request,
        "tickets/mi_ticket.html",
        {
            "ticket": ticket,
            "timeline": timeline,
            "eventos_count": sum(1 for i in timeline if i["tipo"] == "sistema"),
            "comentario_form": ComentarioForm(),
            "usuario": request.user,
            "share_text": f"Ticket {ticket.codigo} — {ticket.titulo} ({ticket.get_estado_display()})",
        },
    )


@user_required
@require_POST
def responder_ticket(request, pk):
    ticket = get_object_or_404(
        Ticket.objects.select_related("categoria"),
        pk=pk,
        solicitante_email=request.user.email,
    )
    comentario = request.POST.get("comentario", "").strip()
    if not comentario:
        messages.error(request, "Debes escribir un mensaje para responder.")
        return redirect("tickets:mi_ticket", pk=pk)

    instancia = TicketComentario.objects.create(
        ticket=ticket,
        usuario=request.user,
        autor_nombre=request.user.nombre,
        comentario=comentario,
        es_interno=False,
    )

    notificar_comentario(ticket, request.user.nombre, comentario)

    if ticket.glpi_id:
        try:
            sync_followup_to_glpi(ticket, comentario)
            messages.success(request, "Tu respuesta se envió a GLPI.")
        except GlpiError:
            messages.warning(request, "Se guardó localmente, pero no fue posible notificar a GLPI.")
    else:
        messages.success(request, "Tu respuesta quedó registrada en el ticket.")

    GlpiEvento.objects.create(
        ticket=ticket,
        tipo=GlpiEvento.Tipo.SEGUIMIENTO,
        descripcion=f"{ticket.codigo}: respuesta del solicitante registrada",
        payload_bruto={"usuario": request.user.email, "comentario": comentario},
    )
    return redirect("tickets:mi_ticket", pk=pk)


def _puede_gestionar_ticket(user, ticket) -> bool:
    """Dueño del ticket o personal de mesa de ayuda."""
    es_dueno = (
        user.is_authenticated
        and getattr(user, "rol", None) == "usuario"
        and ticket.solicitante_email == user.email
    )
    return bool(es_dueno or getattr(user, "es_staff_helpdesk", False))


@login_required
@require_POST
def reenviar_glpi(request, pk):
    """
    Reintenta la sincronización con GLPI de un ticket existente:
    lo crea en GLPI si falta, sube adjuntos pendientes y refleja cambios.
    Disponible para el dueño del ticket y para el personal.
    """
    ticket = get_object_or_404(Ticket.objects.select_related("categoria", "tecnico_asignado"), pk=pk)
    if not _puede_gestionar_ticket(request.user, ticket):
        raise PermissionDenied("No puedes gestionar este ticket.")

    try:
        if not ticket.glpi_id:
            glpi_id = sync_ticket_to_glpi(ticket)
            if not glpi_id:
                messages.warning(
                    request,
                    "GLPI no está habilitado o no tiene tokens configurados (.env).",
                )
                return redirect(_url_vuelta(request.user, ticket))
            messages.success(request, f"Ticket {ticket.codigo} registrado en GLPI #{glpi_id}.")
        else:
            sync_edicion_to_glpi(ticket)
            messages.success(request, f"Contenido de {ticket.codigo} actualizado en GLPI #{ticket.glpi_id}.")

        if ticket.tecnico_asignado_id:
            try:
                if sync_asignacion_to_glpi(ticket):
                    messages.info(request, "Técnico asignado también actualizado en GLPI.")
            except GlpiError as exc:
                messages.warning(request, f"No se pudo reflejar el técnico en GLPI: {exc}")

        n = 0
        try:
            n = sync_adjuntos_to_glpi(ticket)
        except GlpiError as exc:
            messages.warning(request, f"Adjuntos pendientes sin subir a GLPI: {exc}")
        if n:
            messages.info(request, f"{n} adjunto(s) subido(s) a GLPI.")
    except GlpiError as exc:
        messages.error(
            request,
            f"No se pudo sincronizar con GLPI: {exc}. Verifica que GLPI esté encendido "
            f"y vuelve a intentarlo.",
        )
    return redirect(_url_vuelta(request.user, ticket))


def _url_vuelta(user, ticket) -> str:
    if getattr(user, "es_staff_helpdesk", False):
        return reverse("tickets:detalle", args=[ticket.pk])
    return reverse("tickets:mi_ticket", args=[ticket.pk])


@login_required
def editar_mi_ticket(request, pk):
    """El solicitante puede editar su ticket mientras siga abierto."""
    ticket = get_object_or_404(
        Ticket.objects.select_related("categoria", "tecnico_asignado"),
        pk=pk,
        solicitante_email=request.user.email,
    )
    if request.user.rol != "usuario":
        return redirect("tickets:detalle", pk=pk)
    if ticket.estado != Ticket.Estado.ABIERTO:
        messages.warning(
            request,
            "El ticket ya está siendo atendido; solo se puede editar mientras está abierto.",
        )
        return redirect("tickets:mi_ticket", pk=pk)

    form = TicketEdicionForm(request.POST or None, instance=ticket)
    if request.method == "POST" and form.is_valid():
        antes_categoria = Ticket.objects.get(pk=ticket.pk).categoria_id
        ticket = form.save()
        reasignar = (
            not ticket.tecnico_asignado_id
            or (ticket.categoria_id != antes_categoria and ticket.asignacion_automatica)
        )
        if reasignar and _auto_asignar_tecnico(ticket):
            ticket.save(update_fields=["tecnico_asignado", "asignacion_automatica"])
            messages.info(
                request,
                f"Reasignado automáticamente a {ticket.tecnico_asignado.nombre} según la nueva categoría.",
            )
        if ticket.glpi_id:
            try:
                sync_edicion_to_glpi(ticket)
                messages.success(request, "Cambios reflejados en GLPI.")
            except GlpiError as exc:
                messages.warning(
                    request,
                    f"Cambios guardados localmente, pero no se pudieron reflejar en GLPI: {exc}",
                )
        messages.success(request, f"Ticket {ticket.codigo} actualizado.")
        return redirect("tickets:mi_ticket", pk=pk)

    return render(
        request,
        "tickets/mi_ticket_editar.html",
        {"form": form, "ticket": ticket},
    )


@admin_required
def dashboard(request):
    stats = Ticket.estadisticas()
    tickets_qs = (
        Ticket.objects.select_related("categoria", "tecnico_asignado")
        .filter(estado__in=[Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO])
    )
    tickets = list(
        tickets_qs.annotate(
            _prioridad_orden=orden_prioridad_annotation()
        ).order_by("_prioridad_orden", "-fecha_creacion")[:200]
    )
    pp_recientes = _resolve_per_page(request, "per_page_recientes", 5)
    recientes_page = paginate_recent_tickets(request, tickets_qs, per_page=pp_recientes)
    dashboard_context = _build_dashboard_context(request, tickets)
    recientes = _adjuntar_solicitantes(recientes_page.object_list)
    n_tecnicos = User.objects.filter(activo=True, rol__in=[User.Rol.TECNICO, User.Rol.ADMIN]).count()
    n_usuarios = User.objects.filter(activo=True, rol=User.Rol.USUARIO).count()
    return render(
        request,
        "tickets/dashboard.html",
        {
            "stats": stats,
            "recientes": recientes,
            "recientes_page": recientes_page,
            "per_page_recientes": pp_recientes,
            "querystring": _params_sin_page(request, "page_recientes"),
            "dash_json": _build_tecnico_dashboard(None),
            "tecnicos_stats": _tecnicos_resumen(),
            "n_tecnicos": n_tecnicos,
            "n_usuarios": n_usuarios,
            **dashboard_context,
        },
    )


def _paginar(qs, request, param="page", per_page_param="per_page", per_page_default=5):
    allowed = {5, 10, 20, 50, 0}
    try:
        pp = int(request.GET.get(per_page_param, per_page_default))
    except (ValueError, TypeError):
        pp = per_page_default
    if pp not in allowed:
        pp = per_page_default
    if pp == 0:
        pp = qs.count() or 1
    paginator = Paginator(qs, pp)
    numero = request.GET.get(param) or 1
    return paginator.get_page(numero)


def _resolve_per_page(request, param="per_page", default=5):
    allowed = {5, 10, 20, 50, 0}
    try:
        pp = int(request.GET.get(param, default))
    except (ValueError, TypeError):
        pp = default
    return pp if pp in allowed else default


def _params_sin_page(request, param="page"):
    params = request.GET.copy()
    params.pop(param, None)
    return params.urlencode()


def _adjuntar_solicitantes(tickets):
    """Adjunta a cada ticket su Usuario (para mostrar avatar/initials) según el correo del solicitante."""
    emails = {t.solicitante_email.lower() for t in tickets if t.solicitante_email}
    if not emails:
        return tickets
    usuarios = {
        u.email.lower(): u
        for u in get_user_model().objects.filter(email__in=list(emails))
    }
    for t in tickets:
        t.solicitante_usuario = usuarios.get((t.solicitante_email or "").lower())
    return tickets


def _tecnicos_resumen():
    """Resumen por técnico/admin activo: carga, ANS (vencidos/por vencer) y categorías.

    Permite al dashboard del administrador seguir el historial de cada técnico:
    cuántos tickets tiene a cargo, si están vencidos o por vencer, los resueltos/
    cerrados y qué categorías maneja.
    """
    tecnicos = {
        u.id: u
        for u in User.objects.filter(activo=True, rol__in=["tecnico", "admin"]).order_by("nombre")
    }
    agg = {
        uid: {
            "id": uid,
            "nombre": u.nombre or u.email,
            "email": u.email,
            "abrir": 0,
            "espera": 0,
            "vencido": 0,
            "riesgo": 0,
            "resueltos": 0,
            "cerrado": 0,
            "categorias": set(),
        }
        for uid, u in tecnicos.items()
    }
    for t in Ticket.objects.select_related("categoria", "tecnico_asignado").iterator(chunk_size=500):
        tid = t.tecnico_asignado_id
        if not tid or tid not in agg:
            continue
        r = agg[tid]
        if t.estado == Ticket.Estado.ABIERTO:
            r["abrir"] += 1
        elif t.estado == Ticket.Estado.EN_PROGRESO:
            r["espera"] += 1
        elif t.estado == Ticket.Estado.RESUELTO:
            r["resueltos"] += 1
        elif t.estado == Ticket.Estado.CERRADO:
            r["cerrado"] += 1
        if t.estado in (Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO):
            ans = t.info_ans[0]
            if ans == "vencido":
                r["vencido"] += 1
            elif ans == "por-vencer":
                r["riesgo"] += 1
            if t.categoria_id:
                r["categorias"].add(
                    f"{t.categoria.grupo or ''} › {t.categoria.nombre or ''}".strip(" ›") or "Sin categoría"
                )
            else:
                r["categorias"].add("Sin categoría")
    resumen = []
    for r in agg.values():
        r["categorias"] = sorted(r["categorias"])
        resumen.append(r)
    return resumen


def _cat_label(t):
    if t.categoria_id:
        return f"{t.categoria.grupo or ''} › {t.categoria.nombre or ''}".strip(" ›") or "Sin categoría"
    return "Sin categoría"


@admin_required
def tec_tickets_api(request, pk):
    """Tickets asignados a un técnico, para la tarjeta 'Técnicos' del panel admin."""
    tec = get_object_or_404(User, pk=pk)
    qs = (
        Ticket.objects.filter(tecnico_asignado=tec)
        .select_related("categoria")
        .order_by("-fecha_creacion")
    )
    tickets = []
    for t in qs:
        ans = t.info_ans[0]
        tickets.append(
            {
                "id": t.pk,
                "codigo": t.codigo,
                "titulo": t.titulo,
                "prioridad": t.get_prioridad_display(),
                "estado": t.estado,
                "estado_label": t.get_estado_display(),
                "categoria": _cat_label(t),
                "ans": ans,
                "solicitante": (t.solicitante_nombre or t.solicitante_email or "Sin datos"),
                "detalle_url": reverse("tickets:detalle", args=[t.pk]),
            }
        )
    return JsonResponse(
        {
            "nombre": tec.nombre or tec.email,
            "email": tec.email,
            "total": qs.count(),
            "tickets": tickets,
        }
    )


@staff_required
def sin_asignar(request):
    """Bandeja de solicitudes sin técnico asignado.

    El administrador asigna cada solicitud a un técnico; el técnico puede
    'tomar' las que queden disponibles (auto-asignación).
    """
    es_admin = request.user.rol == "admin"
    abiertos = [Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO]
    base = (
        Ticket.objects.select_related("categoria", "tecnico_asignado")
        .filter(estado__in=abiertos, tecnico_asignado__isnull=True)
        .order_by("-fecha_creacion")
    )
    tecnicos = (
        get_user_model()
        .objects.filter(activo=True, is_active=True, rol__in=["admin", "tecnico"])
        .order_by("nombre", "pk")
    )

    if request.method == "POST":
        pk_raw = request.POST.get("ticket_id", "")
        try:
            ticket = base.get(pk=int(pk_raw))
        except (TypeError, ValueError, Ticket.DoesNotExist):
            messages.error(request, "No se encontró la solicitud indicada.")
            return redirect("tickets:sin_asignar")
        accion = request.POST.get("action", "").strip()
        if accion == "asignar" and es_admin:
            valor = request.POST.get("tecnico", "").strip()
            if valor.isdigit():
                tec = tecnicos.filter(pk=int(valor)).first()
                if not tec:
                    messages.error(request, "El técnico seleccionado no es válido.")
                    return redirect("tickets:sin_asignar")
            else:
                tec = None
            ticket.tecnico_asignado = tec
            ticket.asignacion_automatica = False
            ticket.save(
                update_fields=["tecnico_asignado", "asignacion_automatica", "fecha_actualizacion"]
            )
            if tec:
                try:
                    if sync_asignacion_to_glpi(ticket):
                        messages.success(request, f"{ticket.codigo} asignado a {tec.nombre} (también en GLPI).")
                    else:
                        messages.success(request, f"{ticket.codigo} asignado a {tec.nombre}.")
                except GlpiError as exc:
                    messages.warning(request, f"{ticket.codigo} asignado a {tec.nombre}; no se reflejó en GLPI: {exc}")
            else:
                messages.success(request, f"{ticket.codigo} quedó sin técnico (por si otro lo toma).")
            return redirect("tickets:sin_asignar")
        if accion == "tomar":
            ticket.tecnico_asignado = request.user
            ticket.asignacion_automatica = False
            ticket.save(
                update_fields=["tecnico_asignado", "asignacion_automatica", "fecha_actualizacion"]
            )
            if request.user.glpi_user_id:
                try:
                    if sync_asignacion_to_glpi(ticket):
                        messages.success(request, f"Ticket {ticket.codigo} tomado (también en GLPI).")
                    else:
                        messages.success(request, f"Ticket {ticket.codigo} tomado.")
                except GlpiError as exc:
                    messages.warning(request, f"Ticket {ticket.codigo} tomado localmente; no se reflejó en GLPI: {exc}")
            else:
                messages.success(request, f"Ticket {ticket.codigo} tomado. Configura tu 'ID usuario GLPI' en Admin para reflejarlo allá.")
            return redirect("tickets:sin_asignar")
        messages.error(request, "Acción no permitida.")
        return redirect("tickets:sin_asignar")

    pp_mp = _resolve_per_page(request, "per_page", 15)
    page_obj = _paginar(base, request, param="page", per_page_default=pp_mp)
    return render(
        request,
        "tickets/sin_asignar.html",
        {
            "es_admin": es_admin,
            "tickets": page_obj.object_list,
            "page_obj": page_obj,
            "tecnicos": tecnicos,
            "per_page": pp_mp,
            "querystring": _params_sin_page(request),
            "pendientes": base.count(),
        },
    )


@staff_required
def lista_tickets(request):
    """Lista unificada de tickets: el admin ve todos, el técnico solo los suyos."""
    es_admin = request.user.rol == "admin"
    qs = Ticket.objects.select_related("categoria", "tecnico_asignado").annotate(
        adjuntos_count=Count("adjuntos")
    )
    if not es_admin:
        qs = qs.filter(tecnico_asignado=request.user)

    scope_qs = Ticket.objects.all() if es_admin else qs
    stats = scope_qs.aggregate(
        abiertas=Count("pk", filter=Q(estado=Ticket.Estado.ABIERTO)),
        progreso=Count("pk", filter=Q(estado=Ticket.Estado.EN_PROGRESO)),
        resueltas=Count("pk", filter=Q(estado=Ticket.Estado.RESUELTO)),
        cerradas=Count("pk", filter=Q(estado=Ticket.Estado.CERRADO)),
    )
    stats["sin_asignar"] = (
        Ticket.objects.filter(
            estado__in=[Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO],
            tecnico_asignado__isnull=True,
        ).count()
    )

    estado = request.GET.get("estado", "").strip()
    prioridad = request.GET.get("prioridad", "").strip()
    categoria = request.GET.get("categoria", "").strip()
    tecnico = request.GET.get("tecnico", "").strip() if es_admin else ""
    q = request.GET.get("q", "").strip()
    solicitante_email = request.GET.get("solicitante_email", "").strip()
    presets_mis = list(PRESETS_MIS)
    presets_mis_map = dict(presets_mis)
    sv = request.GET.get("sv", "todas").strip()
    if sv not in presets_mis_map:
        sv = "todas"
    rangos_mis = list(RANGOS_MIS)
    rango = request.GET.get("rango", "").strip()
    if rango not in dict(rangos_mis):
        rango = ""
    mias = request.GET.get("mias", "") in ("1", "true", "on")

    abiertos = [Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO]
    if sv == "completadas":
        qs = qs.filter(estado__in=[Ticket.Estado.RESUELTO, Ticket.Estado.CERRADO])
    elif sv == "abiertas":
        qs = qs.filter(estado=Ticket.Estado.ABIERTO)
    elif sv == "espera":
        qs = qs.filter(estado=Ticket.Estado.ABIERTO)
    elif sv == "no-asignadas":
        qs = qs.filter(estado__in=abiertos, tecnico_asignado__isnull=True)
    elif sv == "creadas-hoy":
        inicio_hoy = timezone.localtime(timezone.now()).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        qs = qs.filter(fecha_creacion__gte=inicio_hoy)
    elif sv in ("vencen-hoy", "vencidas"):
        qs = qs.filter(estado__in=abiertos)
    elif sv == "abiertas":
        qs = qs.filter(estado__in=abiertos)

    if rango:
        try:
            qs = qs.filter(
                fecha_creacion__gte=timezone.now() - timedelta(days=int(rango))
            )
        except (TypeError, ValueError):
            pass
    if mias:
        qs = qs.filter(tecnico_asignado=request.user)

    if estado:
        qs = qs.filter(estado=estado)
    if prioridad:
        qs = qs.filter(prioridad=prioridad)
    if categoria:
        qs = qs.filter(categoria_id=categoria)
    if tecnico:
        qs = qs.filter(tecnico_asignado_id=tecnico)
    if solicitante_email:
        qs = qs.filter(solicitante_email__iexact=solicitante_email)
    if q:
        match_codigo = re.match(r"^HD-(\d+)$", q.upper())
        condicion = (
            Q(codigo__iexact=q.upper())
            | Q(titulo__icontains=q)
            | Q(solicitante_nombre__icontains=q)
            | Q(solicitante_email__icontains=q)
        )
        if match_codigo:
            condicion = Q(codigo__iexact=q.upper()) | Q(titulo__icontains=q) | Q(solicitante_nombre__icontains=q)
        qs = qs.filter(condicion)

    pp_lista = _resolve_per_page(request, "per_page", 5)
    if q or sv in ("vencen-hoy", "vencidas"):
        pp_lista = 0
    page_obj = _paginar(
        qs.annotate(_prioridad_orden=orden_prioridad_annotation()).order_by(
            "_prioridad_orden", "-fecha_creacion"
        ),
        request,
        per_page_default=pp_lista,
    )

    filtros_activos = any([estado, prioridad, categoria, tecnico, q, solicitante_email, sv != "todas", rango, mias])
    tickets = _adjuntar_solicitantes(page_obj.object_list)
    if sv == "vencen-hoy":
        ahora = timezone.now()
        inicio_hoy = timezone.localtime(ahora).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        fin_hoy = inicio_hoy + timedelta(days=1)
        tickets = [
            t
            for t in tickets
            if t.estado in abiertos
            and t.fecha_limite_ans
            and inicio_hoy <= t.fecha_limite_ans < fin_hoy
        ]
    elif sv == "vencidas":
        tickets = [
            t
            for t in tickets
            if t.estado in abiertos
            and t.fecha_limite_ans
            and t.fecha_limite_ans < timezone.now()
        ]
    return render(
        request,
        "tickets/lista.html",
        {
            "tickets": tickets,
            "page_obj": page_obj,
            "querystring": _params_sin_page(request),
            "filtros_activos": filtros_activos,
            "filtro_estado": estado,
            "filtro_prioridad": prioridad,
            "filtro_categoria": categoria,
            "filtro_tecnico": tecnico,
            "q": q,
            "estados": Ticket.Estado.choices,
            "prioridades": Ticket.Prioridad.choices,
            "categorias": Categoria.objects.filter(activo=True).order_by("grupo", "nombre"),
            "tecnicos": User.objects.filter(
                activo=True, rol__in=["admin", "tecnico"]
            ).order_by("nombre"),
            "presets_mis": presets_mis,
            "sv": sv,
            "rangos_mis": rangos_mis,
            "rango": rango,
            "mias": mias,
            "stats": stats,
            "total_resultados": (
                len(tickets) if sv in ("vencen-hoy", "vencidas") else page_obj.paginator.count
            ),
            "es_admin": es_admin,
            "per_page": pp_lista,
        },
    )


@staff_required
def detalle_ticket(request, pk):
    ticket = get_object_or_404(
        Ticket.objects.select_related("categoria", "tecnico_asignado").prefetch_related(
            "adjuntos", "comentarios", "comentarios__usuario"
        ),
        pk=pk,
    )
    comentario_form = ComentarioForm()
    asignar_form = AsignarTecnicoForm(initial={"tecnico": ticket.tecnico_asignado_id})

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "comentario":
            comentario_form = ComentarioForm(request.POST)
            if comentario_form.is_valid():
                c = comentario_form.save(commit=False)
                c.ticket = ticket
                c.usuario = request.user
                c.autor_nombre = request.user.nombre
                c.save()
                notificar_comentario(ticket, request.user.nombre, c.comentario, c.es_interno)
                messages.success(request, "Seguimiento agregado")
                return redirect("tickets:detalle", pk=pk)
        elif action == "asignar":
            asignar_form = AsignarTecnicoForm(request.POST)
            if asignar_form.is_valid():
                ticket.tecnico_asignado = asignar_form.cleaned_data["tecnico"]
                ticket.asignacion_automatica = False
                ticket.save(
                    update_fields=["tecnico_asignado", "asignacion_automatica", "fecha_actualizacion"]
                )
                if ticket.tecnico_asignado_id:
                    try:
                        if sync_asignacion_to_glpi(ticket):
                            messages.success(request, "Tecnico actualizado (también en GLPI)")
                        else:
                            messages.success(
                                request,
                                "Tecnico actualizado"
                                + (
                                    ""
                                    if ticket.tecnico_asignado.glpi_user_id
                                    else " · configura su 'ID usuario GLPI' en Admin para reflejarlo en GLPI"
                                ),
                            )
                    except GlpiError as exc:
                        messages.warning(
                            request, f"Técnico guardado localmente, pero no se reflejó en GLPI: {exc}"
                        )
                else:
                    messages.success(request, "Tecnico actualizado")
                return redirect("tickets:detalle", pk=pk)

    timeline_data_ = _timeline_ticket(ticket, include_internos=True)
    vinculo_principal = (
        TicketVinculo.objects.filter(ticket_secundario=ticket)
        .select_related("ticket_principal", "ticket_principal__categoria", "creado_por")
        .first()
    )
    vinculos_secundarios = list(
        TicketVinculo.objects.filter(ticket_principal=ticket)
        .select_related("ticket_secundario", "ticket_secundario__categoria", "creado_por")
        .order_by("fecha")
    )
    return render(
        request,
        "tickets/detalle.html",
        {
            "ticket": ticket,
            "timeline": timeline_data_,
            "eventos_count": sum(1 for i in timeline_data_ if i["tipo"] == "sistema"),
            "comentario_form": comentario_form,
            "asignar_form": asignar_form,
            "vinculo_principal": vinculo_principal,
            "vinculos_secundarios": vinculos_secundarios,
            "share_text": f"Ticket {ticket.codigo} — {ticket.titulo} ({ticket.get_estado_display()})",
        },
    )


@staff_required
def ticket_estado_ajax(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    return JsonResponse({"ok": True, "estado": ticket.estado})


@staff_required
@require_POST
def cambiar_estado(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    nuevo = request.POST.get("estado")
    validos = {c[0] for c in Ticket.Estado.choices}
    if nuevo not in validos:
        messages.error(request, "Estado no valido.")
    else:
        ticket.estado = nuevo
        ticket.save()
        notificar_ticket_actualizado(ticket, f"cambiado a {ticket.get_estado_display()}")
        try:
            sync_estado_to_glpi(ticket)
        except GlpiError as exc:
            messages.warning(request, f"No se pudo actualizar el estado en GLPI: {exc}")
            logger.warning("GLPI estado sync: %s", exc)
        messages.success(request, f"{ticket.codigo} → {ticket.get_estado_display()}")
    next_url = request.POST.get("next") or "tickets:lista"
    if next_url.startswith("/"):
        return redirect(next_url)
    return redirect(next_url)


@staff_required
@require_POST
def eliminar_ticket(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    codigo = ticket.codigo
    glpi_id = ticket.glpi_id
    borrar_en_glpi = bool(getattr(request.user, "borrar_glpi_al_eliminar", False))
    aviso_glpi = None
    if borrar_en_glpi and glpi_id:
        client = GlpiClient()
        if client.available:
            try:
                client.init_session()
                client.delete_ticket(glpi_id)
            except GlpiError as exc:
                aviso_glpi = str(exc)
            except Exception as exc:
                aviso_glpi = f"error inesperado: {exc}"
            finally:
                client.kill_session()
    for adj in ticket.adjuntos.all():
        if adj.archivo:
            adj.archivo.delete(save=False)
    ticket.delete()
    mensaje = f"Ticket {codigo} eliminado."
    if borrar_en_glpi:
        if glpi_id:
            mensaje += " También se eliminó en GLPI." if not aviso_glpi else f" GLPI local (no se sincronizó: {aviso_glpi})."
        else:
            mensaje += " No tenía registro en GLPI."
    else:
        mensaje += " Se conservó en GLPI (configurado así en Ajustes)." if glpi_id else ""
    messages.success(request, mensaje)
    next_url = request.POST.get("next") or "tickets:lista"
    if next_url.startswith("/"):
        return redirect(next_url)
    return redirect(next_url)


@staff_required
def ver_adjunto(request, pk):
    adj = get_object_or_404(TicketAdjunto, pk=pk)
    try:
        return FileResponse(
            adj.archivo.open("rb"),
            content_type=adj.mime_type,
            as_attachment=False,
            filename=adj.nombre_original,
        )
    except FileNotFoundError:
        raise Http404("Archivo no encontrado en disco")


# ---------------------------------------------------------------------------
# Mi panel corporativo — endpoints AJAX (editar / ver respuestas / cerrar)
# ---------------------------------------------------------------------------
def _mi_ticket_del_usuario(request, pk):
    return get_object_or_404(
        Ticket.objects.select_related("categoria"),
        pk=pk,
        solicitante_email=request.user.email,
    )


def _respuestas_para(ticket, include_internos=False):
    """Historial de mensajes del ticket (comentarios de soporte + del usuario)."""
    items = []
    for c in ticket.comentarios.order_by("fecha"):
        if c.es_interno:
            if not include_internos:
                continue
            rol = "interno"
            autor = c.autor_nombre or (c.usuario.nombre if c.usuario_id else "Staff")
            items.append(
                {
                    "rol": rol,
                    "autor": autor,
                    "fecha": c.fecha.isoformat() if c.fecha else "",
                    "fecha_label": c.fecha.strftime("%d/%m/%Y %H:%M") if c.fecha else "",
                    "texto": c.comentario,
                }
            )
            continue
        rol = "soporte"
        autor = c.autor_nombre or (c.usuario.nombre if c.usuario_id else "Mesa de ayuda")
        if c.usuario_id and getattr(c.usuario, "rol", None) == "usuario":
            rol = "usuario"
        items.append(
            {
                "rol": rol,
                "autor": autor,
                "fecha": c.fecha.isoformat() if c.fecha else "",
                "fecha_label": c.fecha.strftime("%d/%m/%Y %H:%M") if c.fecha else "",
                "texto": c.comentario,
            }
        )
    for ev in ticket.eventos_glpi.order_by("fecha"):
        items.append(
            {
                "rol": "sistema",
                "autor": "GLPI",
                "fecha": ev.fecha.isoformat() if ev.fecha else "",
                "fecha_label": ev.fecha.strftime("%d/%m/%Y %H:%M") if ev.fecha else "",
                "texto": ev.descripcion,
            }
        )
    items.sort(key=lambda i: i["fecha"])
    return items


@user_required
def mi_ticket_info_ajax(request, pk):
    """Datos del ticket para editar y su historial de respuestas (JSON)."""
    ticket = _mi_ticket_del_usuario(request, pk)
    imagenes = [
        {
            "pk": a.pk,
            "url": a.archivo.url if a.archivo else "",
            "nombre": a.nombre_original,
        }
        for a in ticket.adjuntos.filter(mime_type__startswith="image/").order_by("fecha_subida")
    ]
    return JsonResponse(
        {
            "ok": True,
            "ticket": {
                "pk": ticket.pk,
                "codigo": ticket.codigo,
                "titulo": ticket.titulo,
                "descripcion": ticket.descripcion,
                "categoria_id": ticket.categoria_id,
                "categoria_nombre": ticket.categoria.nombre if ticket.categoria else "Sin categoría",
                "prioridad": ticket.prioridad,
                "prioridad_nombre": ticket.get_prioridad_display(),
                "solicitante_punto": ticket.solicitante_punto,
                "estado": ticket.estado,
                "estado_label": ticket.get_estado_display(),
                "fecha": ticket.fecha_creacion.strftime("%d/%m/%Y %H:%M") if ticket.fecha_creacion else "",
                "editable": ticket.estado == ticket.Estado.ABIERTO,
                "cerrable": ticket.estado in (ticket.Estado.ABIERTO, ticket.Estado.EN_PROGRESO),
            },
            "imagenes": imagenes,
            "categorias": [
                {"id": c.pk, "nombre": f"{c.grupo} · {c.nombre}"}
                for c in Categoria.objects.filter(activo=True).order_by("grupo", "nombre")
            ],
            "respuestas": _respuestas_para(ticket),
        }
    )


@user_required
@require_POST
def mi_ticket_editar_ajax(request, pk):
    """Guardar la edición del ticket sin recargar la página.

    El usuario solo puede cambiar el título, las observaciones (descripción) y
    adjuntar/eliminar una imagen. Prioridad y categoría NO se pueden editar.
    """
    ticket = _mi_ticket_del_usuario(request, pk)
    if ticket.estado != ticket.Estado.ABIERTO:
        return JsonResponse(
            {"ok": False, "error": "Solo puedes editar tu ticket mientras está abierto."},
            status=400,
        )

    titulo = (request.POST.get("titulo") or "").strip()
    descripcion = (request.POST.get("descripcion") or "").strip()
    if not titulo:
        return JsonResponse({"ok": False, "error": "Debes escribir el nombre del ticket."}, status=400)

    # Actualizar SOLO título y descripción (prioridad/categoría se conservan)
    ticket.titulo = titulo
    ticket.descripcion = descripcion
    ticket.save(update_fields=["titulo", "descripcion"])

    # Adjuntar imagen pequeña (si viene un archivo de imagen)
    archivo = request.FILES.get("imagen")
    if archivo:
        if not (archivo.content_type or "").startswith("image/"):
            return JsonResponse(
                {"ok": False, "error": "Solo puedes adjuntar imágenes."},
                status=400,
            )
        if archivo.size > 5 * 1024 * 1024:
            return JsonResponse({"ok": False, "error": "La imagen no puede superar los 5 MB."}, status=400)
        if ticket.adjuntos.filter(mime_type__startswith="image/").count() >= 1:
            return JsonResponse({"ok": False, "error": "Solo se permite una imagen por ticket."}, status=400)
        TicketAdjunto.objects.create(
            ticket=ticket,
            nombre_original=archivo.name,
            archivo=archivo,
            mime_type=archivo.content_type or "image/png",
            tamano_bytes=archivo.size,
            subido_por=ticket.solicitante_email,
        )

    # Eliminar imagen existente (si se solicita)
    eliminar_pk = request.POST.get("eliminar_imagen")
    if eliminar_pk:
        adj = ticket.adjuntos.filter(mime_type__startswith="image/", pk=eliminar_pk).first()
        if adj:
            if adj.archivo:
                adj.archivo.delete(save=False)
            adj.delete()

    if ticket.glpi_id:
        try:
            sync_edicion_to_glpi(ticket)
        except GlpiError:
            pass

    return JsonResponse(
        {
            "ok": True,
            "ticket": {
                "pk": ticket.pk,
                "titulo": ticket.titulo,
                "descripcion": ticket.descripcion,
                "categoria_id": ticket.categoria_id,
            },
        }
    )


@user_required
@require_POST
def mi_ticket_cerrar_ajax(request, pk):
    """Cerrar el ticket del usuario sin recargar la página."""
    ticket = _mi_ticket_del_usuario(request, pk)
    if ticket.estado in (ticket.Estado.RESUELTO, ticket.Estado.CERRADO):
        return JsonResponse(
            {"ok": False, "error": "Este ticket ya está resuelto o cerrado."},
            status=400,
        )
    ticket.estado = ticket.Estado.CERRADO
    ticket.save()
    notificar_ticket_actualizado(ticket, "Cerrado", "El solicitante cerro el ticket.")
    try:
        sync_estado_to_glpi(ticket)
    except GlpiError:
        pass
    return JsonResponse({"ok": True, "estado": "cerrado", "estado_label": "Cerrado"})


@user_required
@require_POST
def mi_ticket_eliminar_ajax(request, pk):
    """Eliminar el propio ticket del usuario (solo mientras esté abierto)."""
    ticket = _mi_ticket_del_usuario(request, pk)
    if ticket.estado != ticket.Estado.ABIERTO:
        return JsonResponse(
            {"ok": False, "error": "Solo puedes eliminar tu solicitud mientras esté abierta."},
            status=400,
        )
    codigo = ticket.codigo
    for adj in ticket.adjuntos.all():
        if adj.archivo:
            adj.archivo.delete(save=False)
    ticket.delete()
    return JsonResponse({"ok": True, "codigo": codigo})


@user_required
@require_POST
def mi_responder_ajax(request, pk):
    """Responder a un ticket propio desde el mini chat (sincroniza con GLPI)."""
    ticket = _mi_ticket_del_usuario(request, pk)
    comentario = request.POST.get("comentario", "").strip()
    if not comentario:
        return JsonResponse({"ok": False, "error": "Escribe un mensaje para responder."}, status=400)

    TicketComentario.objects.create(
        ticket=ticket,
        usuario=request.user,
        autor_nombre=request.user.nombre,
        comentario=comentario,
        es_interno=False,
    )

    notificar_comentario(ticket, request.user.nombre, comentario)

    notificado = False
    if ticket.glpi_id:
        try:
            sync_followup_to_glpi(ticket, comentario)
            notificado = True
        except GlpiError:
            notificado = False
    else:
        notificado = False

    GlpiEvento.objects.create(
        ticket=ticket,
        tipo=GlpiEvento.Tipo.SEGUIMIENTO,
        descripcion=f"{ticket.codigo}: respuesta del solicitante registrada",
        payload_bruto={"usuario": request.user.email, "comentario": comentario},
    )

    return JsonResponse({
        "ok": True,
        "notificado": notificado,
        "mensaje": {
            "rol": "usuario",
            "autor": request.user.nombre,
            "fecha_label": DateFormat(timezone.now()).format("d/m/Y H:i"),
            "texto": comentario,
        },
    })


@staff_required
def panel_tecnico(request):
    """
    Panel del técnico: solicitudes asignadas a él/ella + chat para responderlas.
    """
    tecnico = request.user
    estado = request.GET.get("estado", "").strip()
    q = request.GET.get("q", "").strip()
    q_cola = request.GET.get("q_cola", "").strip()
    pp_mis = _resolve_per_page(request, "per_page", 5)
    pp_sol = _resolve_per_page(request, "per_page_sol", 5)
    if q:
        pp_mis = 0
    if q_cola:
        pp_sol = 0

    qs = (
        Ticket.objects.filter(tecnico_asignado=tecnico)
        .select_related("categoria", "tecnico_asignado")
        .prefetch_related("comentarios", "eventos_glpi")
    )
    if estado:
        qs = qs.filter(estado=estado)
    if q:
        match_codigo = re.match(r"^HD-(\d+)$", q.upper())
        condicion = (
            Q(codigo__iexact=q.upper())
            | Q(titulo__icontains=q)
            | Q(solicitante_nombre__icontains=q)
            | Q(solicitante_email__icontains=q)
            | Q(solicitante_punto__icontains=q)
        )
        if match_codigo:
            condicion = Q(codigo__iexact=q.upper()) | Q(titulo__icontains=q) | Q(solicitante_nombre__icontains=q)
        qs = qs.filter(condicion)

    # Dashboard del técnico: resumen completo de SUS tickets (sin filtros de búsqueda)
    base_qs = Ticket.objects.filter(tecnico_asignado=tecnico)
    stats = base_qs.aggregate(
        total=Count("id"),
        abiertos=Count("id", filter=Q(estado=Ticket.Estado.ABIERTO)),
        en_progreso=Count("id", filter=Q(estado=Ticket.Estado.EN_PROGRESO)),
        resueltos=Count("id", filter=Q(estado=Ticket.Estado.RESUELTO)),
        cerrados=Count("id", filter=Q(estado=Ticket.Estado.CERRADO)),
    )
    chart_context = _build_chart_context(
        list(base_qs.select_related("categoria", "tecnico_asignado"))
    )

    # Cola de solicitudes de usuarios: tickets sin cerrar que el técnico puede tomar
    cola_qs = (
        Ticket.objects.select_related("categoria", "tecnico_asignado")
        .exclude(estado=Ticket.Estado.CERRADO)
        .annotate(_prioridad_orden=orden_prioridad_annotation())
        .order_by("_prioridad_orden", "-fecha_creacion")
    )
    if q_cola:
        match_cola = re.match(r"^HD-(\d+)$", q_cola.upper())
        condicion_cola = (
            Q(codigo__iexact=q_cola.upper())
            | Q(titulo__icontains=q_cola)
            | Q(solicitante_nombre__icontains=q_cola)
            | Q(solicitante_email__icontains=q_cola)
            | Q(solicitante_punto__icontains=q_cola)
        )
        if match_cola:
            condicion_cola = Q(codigo__iexact=q_cola.upper()) | Q(titulo__icontains=q_cola) | Q(solicitante_nombre__icontains=q_cola)
        cola_qs = cola_qs.filter(condicion_cola)
    solicitudes_page = _paginar(
        cola_qs,
        request,
        per_page_param="per_page_sol",
        per_page_default=pp_sol,
        param="page_sol",
    )

    page_obj = _paginar(
        qs.annotate(_prioridad_orden=orden_prioridad_annotation()).order_by(
            "_prioridad_orden", "-fecha_creacion"
        ),
        request,
        per_page_default=pp_mis,
    )

    ticket = None
    timeline = []
    eventos_count = 0
    ticket_pk = request.GET.get("ticket")
    if ticket_pk:
        try:
            ticket = Ticket.objects.select_related(
                "categoria", "tecnico_asignado"
            ).prefetch_related(
                "comentarios", "comentarios__usuario", "eventos_glpi", "adjuntos"
            ).get(pk=ticket_pk, tecnico_asignado=tecnico)
            timeline = _timeline_ticket(ticket, include_internos=True)
            eventos_count = sum(1 for i in timeline if i["tipo"] == "sistema")
        except Ticket.DoesNotExist:
            ticket = None

    vista = request.GET.get("vista", "").strip() or ("mis" if ticket_pk else "panel")

    # Módulo corporativo "Mis solicitudes abiertas" (solo cuando no hay chat abierto)
    abiertas = []
    combinadas_map = {}
    sitios = []
    grupos = []
    tecnicos = []
    abiertas_count = 0
    if request.user.rol == "admin":
        mias = request.GET.get("mias", "") in ("1", "true", "on")
    else:
        mias = True  # el técnico solo ve sus solicitudes asignadas
    abiertos = [Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO]
    presets_mis = list(PRESETS_MIS)
    if request.user.rol != "admin":
        presets_mis = [
            p for p in presets_mis if p[0] not in ("no-asignadas", "todas")
        ]
    presets_mis_map = dict(presets_mis)
    sv = request.GET.get("sv", "abiertas").strip() or "abiertas"
    if sv not in presets_mis_map:
        sv = "abiertas"
    rangos_mis = list(RANGOS_MIS)
    rango = request.GET.get("rango", "30")
    if rango not in dict(rangos_mis):
        rango = "30"
    if vista == "mis" and not ticket_pk:
        secundarias_comb = set()
        combinadas_map = {}
        for v in TicketVinculo.objects.filter(
            tipo=TicketVinculo.Tipo.COMBINAR
        ).select_related("ticket_secundario"):
            secundarias_comb.add(v.ticket_secundario_id)
            combinadas_map.setdefault(v.ticket_principal_id, []).append(v.ticket_secundario)
        abiertas_qs = Ticket.objects.select_related("categoria", "tecnico_asignado")
        if secundarias_comb:
            abiertas_qs = abiertas_qs.exclude(pk__in=secundarias_comb)
        if sv == "completadas":
            abiertas_qs = abiertas_qs.filter(
                estado__in=[Ticket.Estado.RESUELTO, Ticket.Estado.CERRADO]
            )
        elif sv == "espera":
            abiertas_qs = abiertas_qs.filter(estado=Ticket.Estado.ABIERTO)
        elif sv == "no-asignadas":
            abiertas_qs = abiertas_qs.filter(
                estado__in=abiertos, tecnico_asignado__isnull=True
            )
        elif sv == "vencen-hoy":
            abiertas_qs = abiertas_qs.filter(estado__in=abiertos)
        elif sv == "vencidas":
            abiertas_qs = abiertas_qs.filter(estado__in=abiertos)
        elif sv == "creadas-hoy":
            inicio_hoy = timezone.localtime(timezone.now()).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            abiertas_qs = abiertas_qs.filter(fecha_creacion__gte=inicio_hoy)
        elif sv == "todas":
            pass
        else:
            abiertas_qs = abiertas_qs.filter(estado__in=abiertos)
        if rango:
            try:
                abiertas_qs = abiertas_qs.filter(
                    fecha_creacion__gte=timezone.now() - timedelta(days=int(rango))
                )
            except (TypeError, ValueError):
                pass
        if estado:
            abiertas_qs = abiertas_qs.filter(estado=estado)
        if q:
            match_codigo = re.match(r"^HD-(\d+)$", q.upper())
            condicion = (
                Q(codigo__iexact=q.upper())
                | Q(titulo__icontains=q)
                | Q(solicitante_nombre__icontains=q)
                | Q(solicitante_email__icontains=q)
                | Q(solicitante_punto__icontains=q)
            )
            if match_codigo:
                condicion = Q(codigo__iexact=q.upper()) | Q(titulo__icontains=q) | Q(solicitante_nombre__icontains=q)
            abiertas_qs = abiertas_qs.filter(condicion)
        if mias:
            abiertas_qs = abiertas_qs.filter(tecnico_asignado=tecnico)
        abiertas = list(
            abiertas_qs.annotate(_prioridad_orden=orden_prioridad_annotation()).order_by(
                "_prioridad_orden", "-fecha_creacion"
            )
        )
        abiertas = _adjuntar_solicitantes(abiertas)
        for t in abiertas:
            t.combinadas = combinadas_map.get(t.pk, [])
        if sv == "vencen-hoy":
            ahora = timezone.now()
            inicio_hoy = timezone.localtime(ahora).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            fin_hoy = inicio_hoy + timedelta(days=1)
            abiertas = [
                t
                for t in abiertas
                if t.estado in abiertos
                and t.fecha_limite_ans
                and inicio_hoy <= t.fecha_limite_ans < fin_hoy
            ]
        elif sv == "vencidas":
            abiertas = [
                t
                for t in abiertas
                if t.estado in abiertos
                and t.fecha_limite_ans
                and t.fecha_limite_ans < timezone.now()
            ]
        abiertas_count = len(abiertas)
        sitios = sorted(
            {t.solicitante_punto for t in abiertas if t.solicitante_punto},
            key=str.lower,
        )
        grupos = sorted(
            {t.categoria.grupo for t in abiertas if t.categoria_id and t.categoria.grupo},
            key=str.lower,
        )
        tecnicos = list(
            User.objects.filter(activo=True, rol__in=["admin", "tecnico"]).order_by("nombre")
        )

    dash_json = (
        _build_tecnico_dashboard(None)
        if request.user.rol == "admin"
        else _build_tecnico_dashboard(tecnico.id)
    ) if vista == "panel" else "{}"

    tickets = _adjuntar_solicitantes(page_obj.object_list)
    solicitudes = _adjuntar_solicitantes(solicitudes_page.object_list)

    return render(
        request,
        "tickets/panel_tecnico.html",
        {
            "tickets": tickets,
            "page_obj": page_obj,
            "solicitudes": solicitudes,
            "solicitudes_page": solicitudes_page,
            "cola_count": solicitudes_page.paginator.count,
            "vista": vista,
            "querystring": _params_sin_page(request),
            "querystring_cola": _params_sin_page(request, "page_sol"),
            "filtro_estado": estado,
            "q": q,
            "q_cola": q_cola,
            "estados": Ticket.Estado.choices,
            "total_resultados": page_obj.paginator.count,
            "ticket": ticket,
            "timeline": timeline,
            "eventos_count": eventos_count,
            "stats": stats,
            "per_page": pp_mis,
            "per_page_sol": pp_sol,
            "dash_json": dash_json,
            "abiertas": abiertas,
            "abiertas_count": abiertas_count,
            "sitios": sitios,
            "grupos": grupos,
            "tecnicos": tecnicos,
            "mias": mias,
            "sv": sv,
            "sv_label": presets_mis_map.get(sv, "Mis solicitudes abiertas"),
            "presets_mis": presets_mis,
            "rango": rango,
            "rangos_mis": rangos_mis,
            **chart_context,
        },
    )


@staff_required
@require_POST
def panel_tecnico_tomar(request, pk):
    """Asigna (toma) un ticket sin técnico a quien lo solicita."""
    ticket = get_object_or_404(
        Ticket.objects.select_related("tecnico_asignado"),
        pk=pk,
    )
    if ticket.tecnico_asignado_id:
        messages.warning(
            request,
            f"El ticket {ticket.codigo} ya está asignado a "
            f"{ticket.tecnico_asignado.nombre if ticket.tecnico_asignado else 'otro técnico'}.",
        )
        return redirect("tickets:panel_tecnico")

    ticket.tecnico_asignado = request.user
    ticket.asignacion_automatica = False
    ticket.save(update_fields=["tecnico_asignado", "asignacion_automatica", "fecha_actualizacion"])

    if request.user.glpi_user_id:
        try:
            if sync_asignacion_to_glpi(ticket):
                messages.success(request, f"Ticket {ticket.codigo} tomado (también en GLPI).")
            else:
                messages.success(request, f"Ticket {ticket.codigo} tomado.")
        except GlpiError as exc:
            messages.warning(request, f"Ticket {ticket.codigo} tomado localmente; no se reflejó en GLPI: {exc}")
    else:
        messages.success(
            request,
            f"Ticket {ticket.codigo} tomado. Configura tu 'ID usuario GLPI' en Admin para reflejarlo allá.",
        )
    return redirect("tickets:panel_tecnico")


@staff_required
@require_POST
def panel_tecnico_lote(request):
    """Acciones en lote del módulo 'Mis solicitudes abiertas' (selección múltiple)."""
    accion = request.POST.get("accion", "").strip()
    try:
        ids = [int(x) for x in request.POST.get("ids", "").split(",") if x.strip().isdigit()]
    except (TypeError, ValueError):
        ids = []
    if not ids:
        return JsonResponse({"ok": False, "error": "Selecciona al menos una solicitud."}, status=400)

    tickets = list(
        Ticket.objects.select_related("categoria", "tecnico_asignado").filter(pk__in=ids)
    )
    if not tickets:
        return JsonResponse({"ok": False, "error": "No se encontraron las solicitudes."}, status=404)

    if accion == "recoger":
        tomados, ya_asignados = 0, 0
        for t in tickets:
            if t.tecnico_asignado_id:
                ya_asignados += 1
                continue
            t.tecnico_asignado = request.user
            t.asignacion_automatica = False
            t.save(update_fields=["tecnico_asignado", "asignacion_automatica", "fecha_actualizacion"])
            tomados += 1
            if request.user.glpi_user_id:
                try:
                    sync_asignacion_to_glpi(t)
                except GlpiError:
                    pass
        msg = f"{tomados} solicitud(es) recogida(s)."
        if ya_asignados:
            msg += f" {ya_asignados} ya estaban asignadas y se omitieron."
        return JsonResponse({"ok": True, "mensaje": msg, "recogidas": tomados})

    if accion == "cerrar":
        cerrados = 0
        for t in tickets:
            if t.estado == Ticket.Estado.CERRADO:
                continue
            t.estado = Ticket.Estado.CERRADO
            t.save(update_fields=["estado", "fecha_cierre", "fecha_actualizacion"])
            notificar_ticket_actualizado(t, "cambiado a Cerrado")
            try:
                sync_estado_to_glpi(t)
            except GlpiError:
                pass
            cerrados += 1
        return JsonResponse({"ok": True, "mensaje": f"{cerrados} solicitud(es) cerrada(s).", "cerrados": cerrados})

    if accion == "eliminar":
        if not request.user.rol == "admin":
            return JsonResponse({"ok": False, "error": "Solo el administrador puede eliminar solicitudes en lote."}, status=403)
        borrar_en_glpi = bool(getattr(request.user, "borrar_glpi_al_eliminar", False))
        eliminados = 0
        for t in tickets:
            glpi_id = t.glpi_id
            if borrar_en_glpi and glpi_id:
                try:
                    client = GlpiClient()
                    if client.available:
                        client.init_session()
                        client.delete_ticket(glpi_id)
                        client.kill_session()
                except Exception:
                    pass
            for adj in t.adjuntos.all():
                if adj.archivo:
                    adj.archivo.delete(save=False)
            t.delete()
            eliminados += 1
        return JsonResponse({"ok": True, "mensaje": f"{eliminados} solicitud(es) eliminada(s).", "eliminados": eliminados})

    if accion == "asignar":
        sitio = request.POST.get("sitio", "").strip()
        grupo = request.POST.get("grupo", "").strip()
        tecnico_id = request.POST.get("tecnico", "").strip()
        if not any([sitio, grupo, tecnico_id]):
            return JsonResponse({"ok": False, "error": "Completa al menos un campo de asignación."}, status=400)

        tecnico = None
        if tecnico_id.isdigit():
            tecnico = User.objects.filter(pk=int(tecnico_id), activo=True,
                                          rol__in=["admin", "tecnico"]).first()
            if tecnico_id and not tecnico:
                return JsonResponse({"ok": False, "error": "El técnico seleccionado no existe."}, status=400)
        categoria = None
        if grupo:
            categoria = Categoria.objects.filter(activo=True, grupo=grupo).order_by("nombre").first()
            if not categoria:
                return JsonResponse({"ok": False, "error": f"No hay categorías activas en el grupo '{grupo}'."}, status=400)

        asignados = 0
        for t in tickets:
            if sitio and t.solicitante_punto != sitio:
                t.solicitante_punto = sitio
            if categoria and t.categoria_id != categoria.pk:
                t.categoria = categoria
            if tecnico_id:
                t.tecnico_asignado = tecnico
                t.asignacion_automatica = False
            t.save(update_fields=["solicitante_punto", "categoria", "tecnico_asignado", "asignacion_automatica", "fecha_actualizacion"])
            if tecnico and tecnico.glpi_user_id:
                try:
                    sync_asignacion_to_glpi(t)
                except GlpiError:
                    pass
            asignados += 1
        return JsonResponse({"ok": True, "mensaje": f"{asignados} solicitud(es) actualizada(s).", "asignados": asignados})

    if accion == "combinar":
        principal_id = request.POST.get("principal", "").strip()
        principal = next(
            (t for t in tickets if str(t.pk) == principal_id), None
        )
        if not principal:
            return JsonResponse(
                {"ok": False, "error": "Selecciona la solicitud principal para combinar."},
                status=400,
            )
        secundarios = [t for t in tickets if t.pk != principal.pk]
        if not secundarios:
            return JsonResponse(
                {"ok": False, "error": "Selecciona al menos dos solicitudes para combinar."},
                status=400,
            )
        ref_sec = ", ".join(t.codigo for t in secundarios)
        combinados = 0
        for sec in secundarios:
            _, creado = TicketVinculo.objects.get_or_create(
                ticket_principal=principal,
                ticket_secundario=sec,
                tipo=TicketVinculo.Tipo.COMBINAR,
                defaults={"comentario": "", "creado_por": request.user},
            )
            TicketComentario.objects.create(
                ticket=sec,
                usuario=request.user,
                autor_nombre=request.user.nombre,
                comentario=(
                    f"Solicitud combinada: este ticket se combinó con la solicitud "
                    f"principal {principal.codigo}. Ref. {ref_sec}."
                ),
                es_interno=True,
            )
            combinados += 1
        TicketComentario.objects.create(
            ticket=principal,
            usuario=request.user,
            autor_nombre=request.user.nombre,
            comentario=f"Solicitud combinada: incluye {ref_sec}.",
            es_interno=True,
        )
        return JsonResponse(
            {
                "ok": True,
                "mensaje": f"{combinados} solicitud(es) combinada(s) bajo {principal.codigo}.",
                "combinados": combinados,
            }
        )

    if accion == "vincular":
        comentario = request.POST.get("comentario", "").strip()
        principal = min(tickets, key=lambda t: t.fecha_creacion or timezone.now())
        secundarios = [t for t in tickets if t.pk != principal.pk]
        if not secundarios:
            return JsonResponse(
                {"ok": False, "error": "Selecciona al menos dos solicitudes para vincular."},
                status=400,
            )
        ref = ", ".join(t.codigo for t in tickets)
        vinculados = 0
        for sec in secundarios:
            _, creado = TicketVinculo.objects.get_or_create(
                ticket_principal=principal,
                ticket_secundario=sec,
                tipo=TicketVinculo.Tipo.VINCULAR,
                defaults={"comentario": comentario, "creado_por": request.user},
            )
            TicketComentario.objects.create(
                ticket=sec,
                usuario=request.user,
                autor_nombre=request.user.nombre,
                comentario=(
                    f"Solicitudes vinculadas: {ref}."
                    + (f" {comentario}" if comentario else "")
                ),
                es_interno=True,
            )
            vinculados += 1
        TicketComentario.objects.create(
            ticket=principal,
            usuario=request.user,
            autor_nombre=request.user.nombre,
            comentario=(
                f"Solicitudes vinculadas: {ref}."
                + (f" {comentario}" if comentario else "")
            ),
            es_interno=True,
        )
        return JsonResponse(
            {
                "ok": True,
                "mensaje": f"{vinculados} solicitud(es) vinculada(s) bajo {principal.codigo}.",
                "vinculados": vinculados,
            }
        )

    return JsonResponse({"ok": False, "error": "Acción no válida."}, status=400)


@staff_required
def mis_tickets_tecnico(request):
    """Unificado con la lista general de tickets: redirige a tickets:lista."""
    return redirect("tickets:lista")


@staff_required
def panel_tecnico_msgs_ajax(request, pk):
    """JSON con los mensajes del ticket para refrescar el chat sin recargar."""
    try:
        ticket = Ticket.objects.select_related("tecnico_asignado").get(
            pk=pk,
            tecnico_asignado=request.user,
        )
    except Ticket.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Ticket no encontrado o no asignado."}, status=404)
    return JsonResponse({"ok": True, "mensajes": _respuestas_para(ticket, include_internos=True)})


@staff_required
@require_POST
def panel_tecnico_chat_ajax(request, pk):
    """Envía un mensaje del técnico al solicitante en el chat del panel."""
    try:
        ticket = Ticket.objects.select_related("tecnico_asignado").get(
            pk=pk,
            tecnico_asignado=request.user,
        )
    except Ticket.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Ticket no encontrado o no asignado."}, status=404)
    comentario = request.POST.get("comentario", "").strip()
    if not comentario:
        return JsonResponse({"ok": False, "error": "Escribe un mensaje para responder."}, status=400)
    es_interno = request.POST.get("interno") in ("1", "true", "on")

    c = TicketComentario.objects.create(
        ticket=ticket,
        usuario=request.user,
        autor_nombre=request.user.nombre,
        comentario=comentario,
        es_interno=es_interno,
    )

    notificado = False
    if not es_interno:
        notificar_comentario(ticket, request.user.nombre, comentario)
        if ticket.glpi_id:
            try:
                sync_followup_to_glpi(ticket, comentario)
                notificado = True
            except GlpiError:
                notificado = False
        GlpiEvento.objects.create(
            ticket=ticket,
            tipo=GlpiEvento.Tipo.SEGUIMIENTO,
            descripcion=f"{ticket.codigo}: respuesta del técnico registrada",
            payload_bruto={"usuario": request.user.email, "comentario": comentario},
        )

    return JsonResponse({
        "ok": True,
        "notificado": notificado,
        "mensaje": {
            "rol": "interno" if es_interno else "soporte",
            "autor": c.autor_nombre or request.user.nombre,
            "fecha_label": DateFormat(timezone.now()).format("d/m/Y H:i"),
            "texto": comentario,
        },
    })
