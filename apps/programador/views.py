import calendar
import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render

from apps.tickets.models import Categoria, Ticket
from .models import CalendarioEvento, DisponibilidadTecnico, Festivo

TIPO_LABEL = {c.value: c.label for c in CalendarioEvento.Tipo}


def _staff_only(user):
    return getattr(user, "es_staff_helpdesk", False)


@login_required(login_url="accounts:login")
def panel_programador(request):
    if not _staff_only(request.user):
        return render(request, "forbidden.html", status=403)

    tecnicos = request.user.__class__.objects.filter(
        Q(rol="admin") | Q(rol="tecnico"), is_active=True
    ).order_by("nombre")
    sitios = sorted(
        set(
            Ticket.objects.exclude(solicitante_punto__isnull=True)
            .exclude(solicitante_punto="")
            .values_list("solicitante_punto", flat=True)
        )
        | set(CalendarioEvento.objects.exclude(sitio="").values_list("sitio", flat=True))
    )
    grupos = sorted(
        set(Categoria.objects.exclude(grupo="").values_list("grupo", flat=True))
        | set(CalendarioEvento.objects.exclude(grupo="").values_list("grupo", flat=True))
    )
    year, month = request.GET.get("anio"), request.GET.get("mes")
    hoy = dt.date.today()
    if year and month:
        try:
            hoy = hoy.replace(year=int(year), month=int(month), day=1)
        except (ValueError, TypeError):
            pass

    tickets_abiertos = (
        Ticket.objects.exclude(estado=Ticket.Estado.CERRADO)
        .exclude(estado=Ticket.Estado.RESUELTO)
        .order_by("-fecha_creacion")[:400]
    )

    return render(
        request,
        "programador/programador.html",
        {
            "tecnicos": tecnicos,
            "sitios": sitios,
            "grupos": grupos,
            "hoy": hoy,
            "tickets_abiertos": tickets_abiertos,
            "tipo_label": TIPO_LABEL,
            "active_tab": request.GET.get("tab", "programador"),
            "tecnico_def": request.user.pk if request.user.rol == "tecnico" else "",
            "tecnico_nombre": request.user.nombre if request.user.rol == "tecnico" else "",
        },
    )


@login_required(login_url="accounts:login")
def programador_datos(request):
    """JSON con eventos, disponibilidad y festivos de un mes (con filtros)."""
    if not _staff_only(request.user):
        return JsonResponse({"error": "No autorizado"}, status=403)

    try:
        year = int(request.GET.get("anio"))
        month = int(request.GET.get("mes"))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Parámetros inválidos"}, status=400)

    tecnico_id = request.GET.get("tecnico_id") or ""
    sitio = request.GET.get("sitio") or ""
    grupo = request.GET.get("grupo") or ""

    # Rango del mes completo (incluye cola: lun anterior a Dom..Sab)
    primero = dt.date(year, month, 1)
    ultimo = dt.date(year, month, calendar.monthrange(year, month)[1])
    inicio = primero - dt.timedelta(days=primero.weekday())
    fin = ultimo + dt.timedelta(days=6 - ultimo.weekday())

    q_ev = Q(fecha__range=(inicio, fin))
    q_disp = Q(fecha__range=(inicio, fin))

    if tecnico_id.isdigit():
        q_ev &= Q(tecnico_id=int(tecnico_id)) | Q(tecnico__isnull=True)
    if sitio:
        q_ev &= Q(sitio__iexact=sitio)
    if grupo:
        q_ev &= Q(grupo__iexact=grupo)

    eventos = [
        {
            "id": e.id,
            "tipo": e.tipo,
            "tipo_label": e.get_tipo_display(),
            "titulo": e.titulo,
            "descripcion": e.descripcion,
            "fecha": e.fecha.isoformat(),
            "hora": e.hora.strftime("%H:%M") if e.hora else "",
            "tecnico_id": e.tecnico_id,
            "tecnico": e.tecnico.nombre if e.tecnico else "",
            "sitio": e.sitio,
            "grupo": e.grupo,
            "ticket_id": e.ticket_id,
            "ticket_codigo": e.ticket.codigo if e.ticket else "",
            "completado": e.completado,
            "puede_editar": (e.creado_por_id == request.user.id) or request.user.rol == "admin",
        }
        for e in CalendarioEvento.objects.filter(q_ev).select_related("tecnico", "ticket")
    ]

    disp = {
        f"{d.tecnico_id}|{d.fecha.isoformat()}": {"tipo": d.tipo, "nota": d.nota}
        for d in DisponibilidadTecnico.objects.filter(q_disp).select_related("tecnico")
    }

    festivos = {f.fecha.isoformat(): f.nombre for f in Festivo.objects.filter(fecha__range=(inicio, fin))}

    return JsonResponse(
        {
            "ok": True,
            "anio": year,
            "mes": month,
            "eventos": eventos,
            "disponibilidad": disp,
            "festivos": festivos,
        }
    )


@login_required(login_url="accounts:login")
def programador_agregar(request):
    if not _staff_only(request.user):
        return JsonResponse({"error": "No autorizado"}, status=403)
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido"}, status=405)

    fecha = request.POST.get("fecha")
    tipo = request.POST.get("tipo")
    titulo = (request.POST.get("titulo") or "").strip()
    ticket_id = request.POST.get("ticket_id") or ""
    if not fecha or not tipo or not (titulo or (tipo == "solicitud" and ticket_id.isdigit())):
        return JsonResponse({"error": "Fecha, tipo y título son obligatorios"}, status=400)
    try:
        fecha = dt.date.fromisoformat(fecha)
    except ValueError:
        return JsonResponse({"error": "Fecha inválida"}, status=400)

    tecnico_id = request.POST.get("tecnico_id") or ""
    hora = request.POST.get("hora") or ""
    evento = CalendarioEvento(
        tipo=tipo,
        titulo=titulo[:150] or "Solicitud",
        descripcion=(request.POST.get("descripcion") or "").strip(),
        fecha=fecha,
        hora=dt.time.fromisoformat(hora) if hora else None,
        tecnico_id=int(tecnico_id) if tecnico_id.isdigit() else None,
        ticket_id=int(ticket_id) if ticket_id.isdigit() else None,
        sitio=(request.POST.get("sitio") or "").strip(),
        grupo=(request.POST.get("grupo") or "").strip(),
        creado_por=request.user,
    )
    if evento.ticket:
        evento.titulo = f"{evento.ticket.codigo} · {evento.ticket.titulo}"[:150]
        if not evento.sitio:
            evento.sitio = evento.ticket.solicitante_punto or ""
        if not evento.grupo and evento.ticket.categoria:
            evento.grupo = evento.ticket.categoria.grupo
    evento.save()
    return JsonResponse({"ok": True, "id": evento.id})


@login_required(login_url="accounts:login")
def programador_eliminar(request):
    if not _staff_only(request.user):
        return JsonResponse({"error": "No autorizado"}, status=403)
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido"}, status=405)

    try:
        evento = CalendarioEvento.objects.get(pk=int(request.POST.get("id", 0)))
    except (CalendarioEvento.DoesNotExist, ValueError):
        return JsonResponse({"error": "Evento no encontrado"}, status=404)

    if evento.creado_por_id == request.user.id or request.user.rol == "admin":
        evento.delete()
        return JsonResponse({"ok": True})
    return JsonResponse({"error": "No autorizado"}, status=403)


@login_required(login_url="accounts:login")
def programador_completado(request):
    if not _staff_only(request.user):
        return JsonResponse({"error": "No autorizado"}, status=403)
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido"}, status=405)
    try:
        evento = CalendarioEvento.objects.get(pk=int(request.POST.get("id", 0)))
    except (CalendarioEvento.DoesNotExist, ValueError):
        return JsonResponse({"error": "Evento no encontrado"}, status=404)
    evento.completado = request.POST.get("completado") == "1"
    evento.save(update_fields=["completado"])
    return JsonResponse({"ok": True})


@login_required(login_url="accounts:login")
def programador_disponibilidad(request):
    """Crea o elimina un registro de disponibilidad para un técnico/fecha."""
    if not _staff_only(request.user):
        return JsonResponse({"error": "No autorizado"}, status=403)
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido"}, status=405)

    tecnico_id = request.POST.get("tecnico_id") or ""
    fecha = request.POST.get("fecha") or ""
    tipo = request.POST.get("tipo") or ""
    if not tecnico_id.isdigit():
        return JsonResponse({"error": "Selecciona un técnico"}, status=400)
    try:
        fecha = dt.date.fromisoformat(fecha)
    except ValueError:
        return JsonResponse({"error": "Fecha inválida"}, status=400)

    if tipo in ("", "ninguno"):
        DisponibilidadTecnico.objects.filter(
            tecnico_id=int(tecnico_id), fecha=fecha
        ).delete()
        return JsonResponse({"ok": True})

    if tipo not in DisponibilidadTecnico.Tipo.values:
        return JsonResponse({"error": "Tipo inválido"}, status=400)

    obj, _ = DisponibilidadTecnico.objects.update_or_create(
        tecnico_id=int(tecnico_id),
        fecha=fecha,
        defaults={
            "tipo": tipo,
            "nota": (request.POST.get("nota") or "").strip(),
            "creado_por": request.user,
        },
    )
    return JsonResponse({"ok": True, "id": obj.id})


@login_required(login_url="accounts:login")
def programador_festivo(request):
    """Añade o elimina un día festivo (azul)."""
    if request.user.rol != "admin":
        return JsonResponse({"error": "Solo administradores"}, status=403)
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido"}, status=405)

    try:
        fecha = dt.date.fromisoformat(request.POST.get("fecha") or "")
    except ValueError:
        return JsonResponse({"error": "Fecha inválida"}, status=400)

    if request.POST.get("quitar") == "1":
        Festivo.objects.filter(fecha=fecha).delete()
        return JsonResponse({"ok": True})

    nombre = (request.POST.get("nombre") or "").strip()
    if not nombre:
        return JsonResponse({"error": "Indica el nombre del festivo"}, status=400)
    Festivo.objects.update_or_create(fecha=fecha, defaults={"nombre": nombre[:100]})
    return JsonResponse({"ok": True})