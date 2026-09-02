import json
import secrets
import string
from collections import Counter
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

from .decorators import admin_required, staff_required, user_required
from .exports import generar_excel_tickets
from .forms import (
    AsignarTecnicoForm,
    CategoriaForm,
    ComentarioForm,
    ConsultaTicketForm,
    TicketEdicionForm,
    TicketForm,
    UsuarioPanelForm,
)
from .models import Categoria, GlpiEvento, Ticket, TicketAdjunto, TicketComentario
from .sla import orden_prioridad_annotation
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


def _auto_asignar_tecnico(ticket) -> bool:
    """
    Regla de asignación automática: si el ticket no tiene técnico y su
    categoría tiene un técnico por defecto configurado, se lo asigna.
    """
    if ticket.tecnico_asignado_id or not ticket.categoria_id:
        return False
    categoria = Categoria.objects.filter(
        pk=ticket.categoria_id, tecnico_default__isnull=False
    ).select_related("tecnico_default").first()
    if not categoria:
        return False
    ticket.tecnico_asignado = categoria.tecnico_default
    ticket.asignacion_automatica = True
    return True


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


def _build_dashboard_context(request, tickets):
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
    estado_bars = [
        {
            "label": estado_display.get(k, k),
            "slug": k,
            "count": estado_counts.get(k, 0),
            "pct": round(estado_counts.get(k, 0) / total_estados * 100),
        }
        for k in estado_labels
    ]

    tecnico_counts = Counter(
        (t.tecnico_asignado.nombre if t.tecnico_asignado else "Sin asignar") for t in tickets
    )
    tecnico_bars = [
        {"label": k, "count": v} for k, v in tecnico_counts.most_common(8)
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

    eventos_qs = GlpiEvento.objects.select_related("ticket").order_by("-fecha")
    page_number = request.GET.get("page_glpi", 1)
    paginator = Paginator(eventos_qs, 4)
    eventos_glpi_page = paginator.get_page(page_number)

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
        "eventos_glpi": eventos_glpi_page.object_list,
        "eventos_glpi_page": eventos_glpi_page,
        "ans_stats": ans_stats,
    }


def paginate_recent_tickets(request, queryset, page_param="page_recientes", per_page=5):
    paginator = Paginator(
        queryset.annotate(
            _prioridad_orden=orden_prioridad_annotation()
        ).order_by("_prioridad_orden", "-fecha_creacion"),
        per_page,
    )
    page_number = request.GET.get(page_param, 1)
    page_obj = paginator.get_page(page_number)
    return page_obj


@admin_required
def reportes(request):
    stats = Ticket.estadisticas()
    tickets_qs = Ticket.objects.select_related("categoria", "tecnico_asignado")
    tickets = list(tickets_qs.order_by("-fecha_creacion")[:200])
    dashboard_context = _build_dashboard_context(request, tickets)
    tiempo_promedio = Ticket.tiempo_promedio_resolucion_horas(tickets_qs)

    colores_estado = {
        "abierto": "#D62B1F",
        "en-progreso": "#F2A900",
        "resuelto": "#2F7D4F",
        "cerrado": "#6B6259",
    }
    estados_modal = []
    for codigo, etiqueta in Ticket.Estado.choices:
        qs_estado = tickets_qs.filter(estado=codigo)
        total_estado = qs_estado.count()
        # Agrupar por solicitante
        from collections import defaultdict
        user_groups = defaultdict(lambda: {"tickets": 0, "emails": set(), "punto": ""})
        for t in qs_estado.order_by("-fecha_creacion"):
            nombre = t.solicitante_nombre or t.solicitante_email or "Anónimo"
            user_groups[nombre]["tickets"] += 1
            if t.solicitante_email:
                user_groups[nombre]["emails"].add(t.solicitante_email)
            if t.solicitante_punto and not user_groups[nombre]["punto"]:
                user_groups[nombre]["punto"] = t.solicitante_punto
        # Ordenar por cantidad de tickets descendente
        usuarios_sorted = sorted(
            user_groups.items(),
            key=lambda x: x[1]["tickets"],
            reverse=True,
        )[:10]
        usuarios_modal = [
            {
                "nombre": nombre,
                "tickets_count": info["tickets"],
                "email": next(iter(info["emails"]), ""),
                "punto": info["punto"],
                "iniciales": "".join(w[0] for w in nombre.split()[:2]).upper(),
            }
            for nombre, info in usuarios_sorted
        ]
        estados_modal.append({
            "codigo": codigo,
            "label": etiqueta,
            "color": colores_estado.get(codigo, "#6B6259"),
            "total": total_estado,
            "usuarios": usuarios_modal,
        })

    return render(
        request,
        "tickets/reportes.html",
        {
            "stats": stats,
            "tiempo_promedio": tiempo_promedio,
            "estados_modal": estados_modal,
            "estados": Ticket.Estado.choices,
            **dashboard_context,
        },
    )


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

    page_obj = _paginar(usuarios, request, per_page=5)

    # Búsqueda en vivo del perfil en GLPI (pestaña Técnicos con texto de búsqueda)
    perfiles_encontrados = 0
    if tab == "tecnico" and q and dj_settings.GLPI.get("enabled"):
        client = GlpiClient()
        if client.available:
            try:
                client.init_session()
                remotos = client.list_users()
            except GlpiError:
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

    # Sin resultados locales pero con búsqueda en Técnicos:
    # ofrecer coincidencias de GLPI aún no importadas.
    glpi_remotos = []
    if tab == "tecnico" and q and not page_obj.object_list and glpi_base:
        try:
            client = GlpiClient()
            remotos = []
            if client.available:
                client.init_session()
                remotos = client.list_users()
                client.kill_session()
        except GlpiError:
            remotos = []
        palabras = [p.lower() for p in q.split()]
        ids_locales = set(
            User.objects.exclude(glpi_user_id=None).values_list("glpi_user_id", flat=True)
        )
        correos_locales = set(User.objects.values_list("email", flat=True))
        for r in remotos:
            texto = f"{r['login']} {r['nombre_real']} {r['email']}".lower()
            if all(p in texto for p in palabras):
                if r["glpi_id"] in ids_locales:
                    continue
                correo_real = r["email"].lower() if "@" in r["email"] else ""
                if correo_real and correo_real in correos_locales:
                    continue
                glpi_remotos.append(r)
        glpi_remotos = glpi_remotos[:8]

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
        },
    )


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
    return redirect(f"{url}?tab=tecnico" + (f"&q={qv}" if qv else ""))


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
    page_obj = _paginar(
        tickets_qs.annotate(_prioridad_orden=orden_prioridad_annotation()).order_by(
            "_prioridad_orden", "-fecha_creacion"
        ),
        request,
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
    form = TicketForm(request.POST or None, request.FILES or None, initial=initial)
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
        messages.success(request, f"Ticket creado: {ticket.codigo}")
        if es_usuario_final:
            return redirect("tickets:mi_ticket", pk=ticket.pk)
        return redirect("tickets:detalle", pk=ticket.pk)

    return render(
        request,
        "tickets/crear_ticket.html",
        {
            "form": form,
            "es_usuario_final": es_usuario_final,
            "cat_sugerencias_json": json.dumps(claves_para_json(), ensure_ascii=False),
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
    recientes_page = paginate_recent_tickets(request, tickets_qs, per_page=10)
    dashboard_context = _build_dashboard_context(request, tickets)
    return render(
        request,
        "tickets/dashboard.html",
        {
            "stats": stats,
            "recientes": recientes_page.object_list,
            "recientes_page": recientes_page,
            **dashboard_context,
        },
    )


def _paginar(qs, request, param="page", per_page=15):
    paginator = Paginator(qs, per_page)
    numero = request.GET.get(param) or 1
    return paginator.get_page(numero)


def _params_sin_page(request, param="page"):
    params = request.GET.copy()
    params.pop(param, None)
    return params.urlencode()


@admin_required
def lista_tickets(request):
    qs = Ticket.objects.select_related("categoria", "tecnico_asignado").annotate(
        adjuntos_count=Count("adjuntos")
    )
    estado = request.GET.get("estado", "").strip()
    prioridad = request.GET.get("prioridad", "").strip()
    categoria = request.GET.get("categoria", "").strip()
    tecnico = request.GET.get("tecnico", "").strip()
    q = request.GET.get("q", "").strip()

    if estado:
        qs = qs.filter(estado=estado)
    if prioridad:
        qs = qs.filter(prioridad=prioridad)
    if categoria:
        qs = qs.filter(categoria_id=categoria)
    if tecnico:
        qs = qs.filter(tecnico_asignado_id=tecnico)
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

    page_obj = _paginar(
        qs.annotate(_prioridad_orden=orden_prioridad_annotation()).order_by(
            "_prioridad_orden", "-fecha_creacion"
        ),
        request,
        per_page=6,
    )

    filtros_activos = any([estado, prioridad, categoria, tecnico, q])
    return render(
        request,
        "tickets/lista.html",
        {
            "tickets": page_obj.object_list,
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
            "total_resultados": page_obj.paginator.count,
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
    return render(
        request,
        "tickets/detalle.html",
        {
            "ticket": ticket,
            "timeline": timeline_data_,
            "eventos_count": sum(1 for i in timeline_data_ if i["tipo"] == "sistema"),
            "comentario_form": comentario_form,
            "asignar_form": asignar_form,
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
    for adj in ticket.adjuntos.all():
        if adj.archivo:
            adj.archivo.delete(save=False)
    ticket.delete()
    messages.success(request, f"Ticket {codigo} eliminado.")
    return redirect("tickets:lista")


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


def _respuestas_para(ticket):
    """Historial de mensajes del ticket (comentarios de soporte + del usuario)."""
    items = []
    for c in ticket.comentarios.order_by("fecha"):
        autor = c.autor_nombre or (c.usuario.nombre if c.usuario_id else "Mesa de ayuda")
        rol = "soporte"
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
