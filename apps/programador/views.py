import calendar
import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render

from apps.tickets.models import Categoria, Ticket
from .models import (
    CalendarioEvento,
    CalendarioEventoLectura,
    DisponibilidadTecnico,
    DisponibilidadTecnicoLectura,
    Festivo,
)

TIPO_LABEL = {c.value: c.label for c in CalendarioEvento.Tipo}


def _staff_only(user):
    return getattr(user, "es_staff_helpdesk", False)


def _puede_ver_evento(user, evento):
    if user.rol == "admin":
        return True
    if user.rol != "tecnico":
        return False
    visibilidad = (evento.metadatos or {}).get("visibilidad")
    if visibilidad == "todos":
        return True
    if visibilidad == "persona":
        return evento.tecnico_id == user.pk or evento.creado_por_id == user.pk
    return evento.tecnico_id == user.pk or evento.creado_por_id == user.pk or evento.tipo in (CalendarioEvento.Tipo.ANUNCIO, CalendarioEvento.Tipo.PROYECTO)


@login_required(login_url="accounts:login")
def panel_programador(request):
    if not _staff_only(request.user):
        return render(request, "forbidden.html", status=403)

    tecnicos = request.user.__class__.objects.filter(
        Q(rol="admin") | Q(rol="tecnico")
    ).order_by("nombre")
    destinatarios_programador = tecnicos.filter(is_active=True)
    if request.user.rol == "tecnico":
        tecnicos = tecnicos.filter(pk=request.user.pk)
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
    # Evento a destacar: llega desde la notificación ("Ver") para abrir directo
    # la ficha de esa fecha en vez de dejar al técnico buscando en el calendario.
    destacado = request.GET.get("ev", "")
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
            "destacado": destacado,
            "tecnicos": tecnicos,
            "destinatarios_programador": destinatarios_programador,
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

    if request.user.rol == "tecnico":
        # Las tareas privadas siguen siendo personales. Reuniones/eventos y
        # anuncios sí se comparten para que los demás técnicos puedan leerlos.
        q_ev &= Q(tecnico=request.user) | Q(creado_por=request.user) | Q(tipo__in=(CalendarioEvento.Tipo.ANUNCIO, CalendarioEvento.Tipo.PROYECTO, CalendarioEvento.Tipo.RECORDATORIO, CalendarioEvento.Tipo.TAREA))
    elif tecnico_id.isdigit():
        q_ev &= Q(tecnico_id=int(tecnico_id)) | Q(tecnico__isnull=True)
        q_disp &= Q(tecnico_id=int(tecnico_id))
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
            "metadatos": e.metadatos,
            "ticket_id": e.ticket_id,
            "ticket_codigo": e.ticket.codigo if e.ticket else "",
            "completado": e.completado,
            "puede_editar": (e.creado_por_id == request.user.id) or request.user.rol == "admin",
            "puede_editar_anuncio": request.user.rol == "admin" or (e.creado_por_id == request.user.id and request.user.puede_editar_anuncios),
            "lecturas": [
                lectura.usuario.nombre
                for lectura in e.lecturas.all()
                if lectura.usuario.rol == "tecnico" and lectura.usuario_id != e.creado_por_id
            ],
        }
        for e in CalendarioEvento.objects.filter(q_ev).select_related("tecnico", "ticket", "creado_por").prefetch_related("lecturas__usuario")
        if _puede_ver_evento(request.user, e)
    ]

    disp = {
        f"{d.tecnico_id}|{d.fecha.isoformat()}": {
            "id": d.id,
            "tipo": d.tipo,
            "nota": d.nota,
            "hora": d.hora.strftime("%H:%M") if d.hora else "",
            "creado_por": d.creado_por.nombre if d.creado_por else "",
            "creado_por_id": d.creado_por_id,
            "lecturas": [
                lectura.usuario.nombre
                for lectura in d.lecturas.all()
                if lectura.usuario.rol == "tecnico" and lectura.usuario_id != d.creado_por_id
            ],
        }
        for d in DisponibilidadTecnico.objects.filter(q_disp)
        .select_related("tecnico", "creado_por")
        .prefetch_related("lecturas__usuario")
    }

    festivos = {f.fecha.isoformat(): f.nombre for f in Festivo.objects.filter(fecha__range=(inicio, fin))}

    tecnicos = [
        {
            "id": u.pk,
            "nombre": u.nombre,
            "activo": u.is_active,
            "rol": u.rol,
            "rol_label": u.get_rol_display(),
            "avatar": u.avatar.url if u.avatar else "",
        }
        for u in request.user.__class__.objects.filter(
            Q(rol="admin") | Q(rol="tecnico")
        ).order_by("nombre")
    ]

    return JsonResponse(
        {
            "ok": True,
            "anio": year,
            "mes": month,
            "eventos": eventos,
            "disponibilidad": disp,
            "festivos": festivos,
            "tecnicos": tecnicos,
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
    # Solo los cuatro tipos que el formulario ofrece. "proyecto" sigue en el
    # modelo para no perder lo ya registrado, pero ya no se puede crear.
    validos = {"tarea", "solicitud", "recordatorio", "proyecto", "anuncio"}
    if tipo not in validos:
        return JsonResponse({"error": "Tipo de evento no válido"}, status=400)
    if not fecha or not (titulo or (tipo == "solicitud" and ticket_id.isdigit())):
        return JsonResponse({"error": "Fecha, tipo y título son obligatorios"}, status=400)
    try:
        fecha = dt.date.fromisoformat(fecha)
    except ValueError:
        return JsonResponse({"error": "Fecha inválida"}, status=400)

    editar_id = request.POST.get("editar_id", "")
    if editar_id:
        if not editar_id.isdigit() or tipo != CalendarioEvento.Tipo.ANUNCIO:
            return JsonResponse({"error": "Registro no válido"}, status=400)
        try:
            anuncio = CalendarioEvento.objects.get(pk=int(editar_id), tipo=CalendarioEvento.Tipo.ANUNCIO)
        except CalendarioEvento.DoesNotExist:
            return JsonResponse({"error": "Anuncio no encontrado"}, status=404)
        if request.user.rol != "admin" and (anuncio.creado_por_id != request.user.id or not request.user.puede_editar_anuncios):
            return JsonResponse({"error": "No autorizado para editar este anuncio"}, status=403)
        descripcion = (request.POST.get("descripcion") or "").strip()
        if not descripcion:
            return JsonResponse({"error": "El mensaje del anuncio es obligatorio"}, status=400)
        metadatos = dict(anuncio.metadatos or {})
        for clave in ("fecha_fin", "destinatarios", "importancia"):
            metadatos[clave] = (request.POST.get("meta_" + clave) or "").strip()
        anuncio.fecha = fecha
        anuncio.titulo = titulo[:150]
        anuncio.descripcion = descripcion
        anuncio.metadatos = metadatos
        anuncio.save(update_fields=["fecha", "titulo", "descripcion", "metadatos"])
        return JsonResponse({"ok": True, "id": anuncio.id, "actualizado": True})

    tecnico_id = request.POST.get("tecnico_id") or ""
    visibilidad = request.POST.get("meta_visibilidad", "")
    if tipo in ("recordatorio", "tarea", "proyecto") and visibilidad:
        if visibilidad not in ("todos", "persona"):
            return JsonResponse({"error": "Selecciona destinatarios válidos"}, status=400)
        if visibilidad == "persona":
            if not tecnico_id.isdigit() or not request.user.__class__.objects.filter(pk=int(tecnico_id), rol__in=("admin", "tecnico"), is_active=True).exists():
                return JsonResponse({"error": "Selecciona un destinatario activo"}, status=400)
        else:
            tecnico_id = ""
    elif request.user.rol == "tecnico":
        tecnico_id = str(request.user.pk)
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
        metadatos={
            key[5:]: value.strip()
            for key, value in request.POST.items()
            if key.startswith("meta_") and value.strip()
        },
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
    if request.user.rol == "tecnico":
        tecnico_id = str(request.user.pk)
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

    hora = request.POST.get("hora") or ""
    try:
        hora_t = dt.time.fromisoformat(hora) if hora else None
    except ValueError:
        return JsonResponse({"error": "Hora inválida"}, status=400)

    obj, creada = DisponibilidadTecnico.objects.update_or_create(
        tecnico_id=int(tecnico_id),
        fecha=fecha,
        defaults={
            "tipo": tipo,
            "nota": (request.POST.get("nota") or "").strip(),
            "hora": hora_t,
            "creado_por": request.user,
        },
    )
    # Una actualización equivale a una nueva comunicación para el equipo.
    if not creada:
        obj.lecturas.all().delete()
    return JsonResponse({"ok": True, "id": obj.id})


@login_required(login_url="accounts:login")
def programador_evento_leido(request):
    """Registra sólo el acuse de lectura de un técnico en un evento compartido."""
    if not _staff_only(request.user):
        return JsonResponse({"error": "No autorizado"}, status=403)
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido"}, status=405)
    try:
        evento = CalendarioEvento.objects.select_related("creado_por", "tecnico").get(pk=int(request.POST.get("id", 0)))
    except (CalendarioEvento.DoesNotExist, TypeError, ValueError):
        return JsonResponse({"error": "Evento no encontrado"}, status=404)

    if not _puede_ver_evento(request.user, evento):
        return JsonResponse({"error": "No autorizado para ver este evento"}, status=403)
    if request.user.rol == "tecnico" and evento.creado_por_id != request.user.id:
        CalendarioEventoLectura.objects.get_or_create(evento=evento, usuario=request.user)

    lecturas = CalendarioEventoLectura.objects.filter(evento=evento, usuario__rol="tecnico").exclude(usuario_id=evento.creado_por_id).select_related("usuario")
    return JsonResponse({"ok": True, "lecturas": [lectura.usuario.nombre for lectura in lecturas]})


@login_required(login_url="accounts:login")
def programador_disponibilidad_leida(request):
    """Registra automáticamente que otro técnico consultó una disponibilidad."""
    if not _staff_only(request.user):
        return JsonResponse({"error": "No autorizado"}, status=403)
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido"}, status=405)
    try:
        disponibilidad = DisponibilidadTecnico.objects.select_related("creado_por").get(
            pk=int(request.POST.get("id", 0))
        )
    except (DisponibilidadTecnico.DoesNotExist, TypeError, ValueError):
        return JsonResponse({"error": "Marca de disponibilidad no encontrada"}, status=404)

    # Es una lectura, no una aprobación: sólo otros técnicos generan el ✓.
    if request.user.rol == "tecnico" and disponibilidad.creado_por_id != request.user.id:
        DisponibilidadTecnicoLectura.objects.get_or_create(
            disponibilidad=disponibilidad,
            usuario=request.user,
        )

    lecturas = (
        DisponibilidadTecnicoLectura.objects.filter(
            disponibilidad=disponibilidad,
            usuario__rol="tecnico",
        )
        .exclude(usuario_id=disponibilidad.creado_por_id)
        .select_related("usuario")
    )
    return JsonResponse({"ok": True, "lecturas": [lectura.usuario.nombre for lectura in lecturas]})


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
