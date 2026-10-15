"""Armar desde el administrador la lista de monitoreo del observador.

El observador solo puede agregar a su lista los usuarios que ya encuentra por
su cuenta. Desde aquí el administrador ve el tabla completa de usuarios
activos, con filtros, y los guarda en la zona que le toca para que el
observador los vea en su panel.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.models import Usuario

from .decorators import admin_required
from .models import (
    ElementoMiLista,
    MonitoreoAuditoria,
    ObservadorPunto,
    Punto,
    Ticket,
    ZonaObservador,
)


def _auditar(actor, accion, observador=None, zona_nombre="", detalle=""):
    """Deja constancia de un cambio del monitoreo para el registro visible."""
    return MonitoreoAuditoria.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        observador=observador if getattr(observador, "pk", None) else None,
        zona_nombre=(zona_nombre or "")[:80],
        accion=accion,
        detalle=(detalle or "")[:200],
    )


def _zonas_de(observador):
    return list(
        ObservadorPunto.objects.filter(observador=observador)
        .order_by("punto__nombre")
        .values_list("punto__nombre", flat=True)
    )


def _elementos_de(observador):
    """Los usuarios y zonas que el observador ya tiene en su lista."""
    return ElementoMiLista.objects.filter(observador=observador)


@admin_required
def monitoreo_admin(request):
    """Tabla de usuarios activos para guardarlos en una zona a monitorear."""
    observador_id = (request.GET.get("observador") or "").strip()
    q = (request.GET.get("q") or "")[:120].strip()
    rol = (request.GET.get("rol") or "").strip()
    zona = (request.GET.get("zona") or "").strip()
    estado = (request.GET.get("estado") or "").strip()

    observadores = list(
        Usuario.objects.filter(rol=Usuario.Rol.OBSERVADOR, activo=True)
        .order_by("nombre")
        .values_list("pk", "nombre")
    )

    observador = None
    if observador_id.isdigit():
        observador = Usuario.objects.filter(
            pk=int(observador_id), rol=Usuario.Rol.OBSERVADOR
        ).first()

    # Sin observador elegido se toma el primero, para que la vista siempre
    # muestre a alguien.
    if observador is None and observadores:
        observador = Usuario.objects.filter(pk=observadores[0][0]).first()

    observers_ids = {pk for pk, _ in observadores}
    elementos_por_correo = {
        (e.usuario_email or "").strip().lower(): e.pk
        for e in _elementos_de(observador) if (e.usuario_email or "").strip()
    } if observador else {}
    zona_por_correo = {}
    if observador:
        carpetas_sup = {
            n.lower() for n in ZonaObservador.objects.filter(
                observador=observador).values_list("nombre", flat=True)
        }
        for e in ElementoMiLista.objects.filter(observador=observador).select_related("zona", "punto"):
            c = (e.usuario_email or "").strip().lower()
            if not c or c in zona_por_correo:
                continue
            # Solo carpetas creadas: un punto suelto (ej. "Bogotá") no es zona,
            # salvo que exista la carpeta con ese mismo nombre.
            if e.zona_id:
                zona_por_correo[c] = e.zona.nombre
            elif e.punto_id and (e.punto.nombre or "").lower() in carpetas_sup:
                zona_por_correo[c] = e.punto.nombre
    ya_mis_lista = set(elementos_por_correo)
    zonas_ya = {
        (e.punto.nombre if e.punto_id else "")
        for e in _elementos_de(observador).select_related("punto")
    } if observador else set()

    # Zonas que ve el observador elegido: las asignadas y las de su lista.
    zonas = sorted(set(_zonas_de(observador)) | zonas_ya) if observador else []
    if not zonas:
        zonas = sorted(Punto.objects.values_list("nombre", flat=True))

    # Lugares de donde salen los tickets: el filtro "zona" mira orígenes
    # reales (solicitante_punto), no las zonas ya asignadas.
    puntos_ticket = list(
        Ticket.objects.exclude(solicitante_punto__isnull=True)
        .exclude(solicitante_punto="")
        .values_list("solicitante_punto", flat=True)
        .distinct().order_by("solicitante_punto")[:200]
    )
    puntos_por_correo = {}
    for email, punto in (
        Ticket.objects.exclude(solicitante_email__isnull=True)
        .exclude(solicitante_email="")
        .exclude(solicitante_punto__isnull=True)
        .exclude(solicitante_punto="")
        .values_list("solicitante_email", "solicitante_punto")
        .distinct()[:10000]
    ):
        clave = (email or "").strip().lower()
        if clave:
            puntos_por_correo.setdefault(clave, set()).add(punto)

    usuarios = Usuario.objects.filter(activo=True, is_active=True).exclude(
        pk__in=observers_ids
    )
    if rol:
        usuarios = usuarios.filter(rol=rol)
    if q:
        usuarios = usuarios.filter(
            Q(nombre__icontains=q) | Q(email__icontains=q)
            | Q(ubicacion__icontains=q)
        )

    # Tickets por solicitante, para ver a quien hay que mirar.
    abiertos = {
        fila["solicitante_email"]: fila["n"]
        for fila in Ticket.objects.filter(
            estado__in=[Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO]
        )
        .exclude(solicitante_email__in=[None, ""])
        .values("solicitante_email")
        .annotate(n=Count("pk"))
    }

    filas = []
    zona_buscada = (zona or "").strip().lower()
    for u in usuarios.order_by("nombre"):
        correo = (u.email or "").strip().lower()
        puntos = sorted(puntos_por_correo.get(correo, ()))
        if zona_buscada and zona_buscada not in {p.lower() for p in puntos}:
            continue
        puntos_txt = ", ".join(puntos[:2])
        if len(puntos) > 2:
            puntos_txt += f" +{len(puntos) - 2}"
        filas.append(
            {
                "obj": u,
                "nombre": u.nombre or u.email,
                "email": correo,
                "rol": u.get_rol_display(),
                "ubicacion": u.ubicacion or (puntos[0] if puntos else "") or "—",
                "zona_badge": zona_por_correo.get(correo, ""),
                "puntos": puntos_txt or "—",
                "abiertos": abiertos.get(correo, 0),
                "ya_agregado": correo in ya_mis_lista,
                "elemento_id": elementos_por_correo.get(correo),
            }
        )

    if estado == "agregados":
        filas = [f for f in filas if f["ya_agregado"]]
    elif estado == "pendientes":
        filas = [f for f in filas if not f["ya_agregado"]]
    elif estado == "con_tickets":
        filas = [f for f in filas if f["abiertos"] > 0]

    zonas_destino = list(
        ZonaObservador.objects.filter(observador=observador)
        .order_by("-creado_en", "-pk")
        .values_list("nombre", flat=True)[:50]
    ) if observador else []
    vistos_destino = {z.lower() for z in zonas_destino}
    zonas_destino += [p for p in (zonas or []) if p.lower() not in vistos_destino][:50]
    zona_elegida = zona or (zonas_destino[0] if zonas_destino else "")
    creadas = _zonas_creadas_por_observador()
    return render(
        request,
        "tickets/monitoreo_admin.html",
        {
            "filas": filas,
            "observadores": observadores,
            "observador": observador,
            "observador_id": str(observador.pk) if observador else "",
            "q": q,
            "rol_sel": rol,
            "zona_sel": zona,
            "estado_sel": estado,
            "zonas": zonas,
            "puntos_ticket": puntos_ticket,
            "zonas_destino": zonas_destino,
            "zona_elegida": zona_elegida,
            "total": len(filas),
            "zonas_creadas": creadas,
            "auditoria": list(
                MonitoreoAuditoria.objects.select_related("actor", "observador")[:20]
            ),
            "dash": {
                "supervisores": len(creadas),
                "zonas": sum(len(b["zonas"]) for b in creadas),
                "cuentas": sum(
                    len(z["miembros"]) for b in creadas for z in b["zonas"]
                ),
                "abiertos": sum(
                    z["abiertos"] for b in creadas for z in b["zonas"]
                ),
            },
        },
    )


def _zonas_creadas_por_observador():
    """Zonas que creó cada observador, con su gente y sus números.

    Es lo que el administrador ve y administra: el supervisor a cargo de
    cada zona (el observador que la creó), las cuentas que tiene dentro y
    el estado de sus tickets. Sin zonas creadas, va vacío.
    """
    # Se agrupa por quien creó la zona, no solo por quien hoy tiene el rol:
    # si al supervisor le cambian el rol, su zona seguía sin aparecer aquí
    # (o la página reventaba con KeyError). Con el dueño real siempre sale.
    zonas = list(
        ZonaObservador.objects.select_related("observador")
        .prefetch_related("elementos__usuario")
        .order_by("observador__nombre", "nombre")
    )
    if not zonas:
        return []
    supervisores = list(
        Usuario.objects.filter(rol=Usuario.Rol.OBSERVADOR).order_by("nombre")
    )
    correos = {
        (e.usuario_email or "").strip().lower()
        for z in zonas for e in z.elementos.all()
        if (e.usuario_email or "").strip()
    }
    totales, abiertos, tecnicos = {}, {}, {}
    if correos:
        for fila in (
            Ticket.objects.exclude(solicitante_email__in=[None, ""])
            .values("solicitante_email")
            .annotate(n=Count("pk"))
        ):
            totales[(fila["solicitante_email"] or "").strip().lower()] = fila["n"]
        for fila in (
            Ticket.objects.filter(
                estado__in=[Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO]
            )
            .exclude(solicitante_email__in=[None, ""])
            .values("solicitante_email")
            .annotate(n=Count("pk"))
        ):
            abiertos[(fila["solicitante_email"] or "").strip().lower()] = fila["n"]
        for t in Ticket.objects.exclude(
            solicitante_email__in=[None, ""]
        ).select_related("tecnico_asignado").only(
            "solicitante_email", "tecnico_asignado__nombre"
        ):
            correo = (t.solicitante_email or "").strip().lower()
            nombre = ((t.tecnico_asignado.nombre if t.tecnico_asignado_id else "") or "").strip()
            if correo in correos and nombre:
                tecnicos.setdefault(correo, {}).setdefault(nombre, 0)
                tecnicos[correo][nombre] += 1
    por_supervisor = {}
    for sup in supervisores:
        por_supervisor[sup.pk] = {
            "supervisor": sup,
            "puntos": _zonas_de(sup),
            "zonas": [],
        }
    for z in zonas:
        if z.observador_id not in por_supervisor:
            # Dueño sin rol de observador (se lo cambiaron): igual se muestra,
            # marcando su rol actual en la tarjeta.
            por_supervisor[z.observador_id] = {
                "supervisor": z.observador,
                "puntos": _zonas_de(z.observador),
                "zonas": [],
            }
    for z in zonas:
        miembros = []
        for e in z.elementos.all():
            correo = (e.usuario_email or "").strip().lower()
            cuentas_tec = tecnicos.get(correo, {})
            miembros.append(
                {
                    "elemento_id": e.pk,
                    "nombre": (e.usuario.nombre if e.usuario_id else "") or correo or "—",
                    "email": correo,
                    "rol": e.usuario.get_rol_display() if e.usuario_id else "Sin cuenta",
                    "ubicacion": (e.usuario.ubicacion if e.usuario_id else "") or "—",
                    "total": totales.get(correo, 0),
                    "abiertos": abiertos.get(correo, 0),
                    "tecnico": max(cuentas_tec.items(), key=lambda kv: kv[1])[0] if cuentas_tec else "—",
                }
            )
        miembros.sort(key=lambda m: (-m["abiertos"], m["nombre"].lower()))
        total_zona = sum(m["total"] for m in miembros)
        abiertos_zona = sum(m["abiertos"] for m in miembros)
        por_supervisor[z.observador_id]["zonas"].append(
            {
                "zona": z,
                "miembros": miembros,
                "abiertos": abiertos_zona,
                "total": total_zona,
                "avance": (
                    int(round(100.0 * (total_zona - abiertos_zona) / total_zona))
                    if total_zona else 0
                ),
            }
        )
    return [v for v in por_supervisor.values() if v["zonas"]]


@admin_required
@login_required
def monitoreo_agregar(request):
    """Guarda un usuario en la zona elegida para que el observador lo vigile."""
    if request.method != "POST":
        return redirect(reverse("tickets:monitoreo_admin"))

    observador_id = request.POST.get("observador") or ""
    correo = (request.POST.get("email") or "").strip().lower()
    nombre_zona = (request.POST.get("zona") or "").strip()
    volver = request.POST.get("volver") or reverse("tickets:monitoreo_admin")

    observador = Usuario.objects.filter(
        pk=observador_id, rol=Usuario.Rol.OBSERVADOR
    ).first() if observador_id.isdigit() else None
    if observador is None or not correo:
        return redirect(volver)

    punto = None
    carpeta = None
    if nombre_zona:
        # Sin crear puntos fantasma: solo se enlaza lo que ya existe.
        punto = Punto.objects.filter(nombre__iexact=nombre_zona).first()
        carpeta = ZonaObservador.objects.filter(
            observador=observador, nombre__iexact=nombre_zona).first()

    # Si ya estaba en la lista, se actualiza la zona en vez de duplicarlo.
    datos = {
        "tipo": ElementoMiLista.TIPO_USUARIO,
        "usuario": Usuario.objects.filter(email__iexact=correo).first(),
        "punto": punto,
    }
    if carpeta is not None:
        datos["zona"] = carpeta
    ElementoMiLista.objects.update_or_create(
        observador=observador,
        usuario_email=correo,
        defaults=datos,
    )
    _auditar(
        request.user, MonitoreoAuditoria.AGREGAR_LISTA, observador,
        nombre_zona, correo,
    )

    # La zona tambien queda asignada al observador para que pueda verla.
    if punto is not None:
        ObservadorPunto.objects.get_or_create(observador=observador, punto=punto)

    return redirect(volver)


@admin_required
@require_POST
def monitoreo_zona_crear(request):
    """El admin crea una carpeta de zona para el supervisor.

    Aparece de inmediato en su desplegable de destino, igual que las que
    crea el propio supervisor.
    """
    observador_id = request.POST.get("observador") or ""
    nombre = (request.POST.get("nombre") or "").strip()[:80]
    volver = request.POST.get("volver") or reverse("tickets:monitoreo_admin")
    observador = Usuario.objects.filter(
        pk=observador_id, rol=Usuario.Rol.OBSERVADOR
    ).first() if observador_id.isdigit() else None
    if observador is None or not nombre:
        return redirect(volver)
    zona, creada = ZonaObservador.objects.get_or_create(
        observador=observador, nombre=nombre)
    if creada:
        _auditar(request.user, MonitoreoAuditoria.CREAR_ZONA,
                 observador, zona.nombre, "")
        messages.success(request, f"Zona {zona.nombre} creada para {observador.nombre}.")
    else:
        messages.info(request, f"La zona {zona.nombre} ya existía.")
    return redirect(volver)


@admin_required
@require_POST
def monitoreo_quitar_zona(request):
    """Saca una cuenta de la zona elegida en el desplegable.

    Solo si está en esa zona: si su seguimiento apunta a otra, se avisa
    en vez de borrar de donde no se pidió.
    """
    observador_id = request.POST.get("observador") or ""
    correo = (request.POST.get("email") or "").strip().lower()
    nombre_zona = (request.POST.get("zona") or "").strip()
    volver = request.POST.get("volver") or reverse("tickets:monitoreo_admin")
    observador = Usuario.objects.filter(
        pk=observador_id, rol=Usuario.Rol.OBSERVADOR
    ).first() if observador_id.isdigit() else None
    if observador is None or not correo or not nombre_zona:
        return redirect(volver)
    elemento = ElementoMiLista.objects.filter(
        observador=observador, usuario_email__iexact=correo
    ).select_related("punto", "zona").first()
    if elemento is None:
        messages.info(request, "Esa cuenta ya no está en el seguimiento.")
        return redirect(volver)
    actual = ((elemento.zona.nombre if elemento.zona_id else "")
              or (elemento.punto.nombre if elemento.punto_id else ""))
    if actual.lower() != nombre_zona.lower():
        messages.info(request, f"{correo} no está en la zona {nombre_zona}.")
        return redirect(volver)
    elemento.delete()
    _auditar(request.user, MonitoreoAuditoria.QUITAR_MIEMBRO,
             observador, nombre_zona, correo)
    messages.success(request, f"{correo} fuera de la zona {nombre_zona}.")
    return redirect(volver)


@admin_required
@login_required
def monitoreo_quitar(request, pk):
    """Saca un elemento de la lista del observador."""
    if request.method != "POST":
        return redirect(reverse("tickets:monitoreo_admin"))
    observador_id = request.POST.get("observador") or ""
    volver = request.POST.get("volver") or reverse("tickets:monitoreo_admin")
    borrados, _ = ElementoMiLista.objects.filter(
        pk=pk, observador__pk=observador_id if observador_id.isdigit() else 0
    ).delete()
    if borrados:
        _auditar(
            request.user, MonitoreoAuditoria.QUITAR_LISTA,
            Usuario.objects.filter(pk=observador_id).first() if observador_id.isdigit() else None,
            "", f"elemento {pk}",
        )
    return redirect(volver)


@admin_required
@login_required
def monitoreo_zona_miembro_quitar(request, pk):
    """Saca una cuenta de la zona (queda en la lista, sin zona)."""
    if request.method != "POST":
        return redirect(reverse("tickets:monitoreo_admin"))
    volver = request.POST.get("volver") or reverse("tickets:monitoreo_admin")
    elemento = ElementoMiLista.objects.filter(pk=pk).select_related("zona").first()
    if elemento is None or elemento.zona_id is None:
        return redirect(volver)
    nombre_zona = elemento.zona.nombre if elemento.zona else ""
    supervisor = elemento.observador
    elemento.zona = None
    elemento.save(update_fields=["zona"])
    _auditar(
        request.user, MonitoreoAuditoria.QUITAR_MIEMBRO, supervisor,
        nombre_zona, (elemento.usuario_email or ""),
    )
    return redirect(volver)


@admin_required
@login_required
def monitoreo_zona_eliminar(request, pk):
    """Elimina una zona creada por un observador (su gente no se borra)."""
    if request.method != "POST":
        return redirect(reverse("tickets:monitoreo_admin"))
    volver = request.POST.get("volver") or reverse("tickets:monitoreo_admin")
    zona = ZonaObservador.objects.select_related("observador").filter(pk=pk).first()
    if zona is not None:
        _auditar(
            request.user, MonitoreoAuditoria.ELIMINAR_ZONA, zona.observador,
            zona.nombre, f"{zona.elementos.count()} cuentas",
        )
        zona.delete()
    return redirect(volver)


@admin_required
@login_required
def monitoreo_zona_renombrar(request, pk):
    """Renombra una zona desde el panel del administrador."""
    if request.method != "POST":
        return redirect(reverse("tickets:monitoreo_admin"))
    volver = request.POST.get("volver") or reverse("tickets:monitoreo_admin")
    zona = ZonaObservador.objects.select_related("observador").filter(pk=pk).first()
    if zona is None:
        return redirect(volver)
    nombre = (request.POST.get("nombre") or "").strip()[:80]
    if not nombre:
        messages.error(request, "El nombre nuevo no puede quedar vacío.")
        return redirect(volver)
    if ZonaObservador.objects.filter(
        observador=zona.observador, nombre__iexact=nombre
    ).exclude(pk=zona.pk).exists():
        messages.error(
            request, f"{zona.observador.nombre} ya tiene una zona llamada «{nombre}»."
        )
        return redirect(volver)
    anterior = zona.nombre
    zona.nombre = nombre
    zona.save(update_fields=["nombre"])
    _auditar(
        request.user, MonitoreoAuditoria.RENOMBRAR_ZONA, zona.observador,
        nombre, f"antes: {anterior}",
    )
    messages.success(request, f"Zona «{anterior}» ahora se llama «{nombre}».")
    return redirect(volver)


@admin_required
@login_required
def monitoreo_zona_crear(request):
    """Crea una zona para un supervisor desde el panel del administrador."""
    if request.method != "POST":
        return redirect(reverse("tickets:monitoreo_admin"))
    volver = request.POST.get("volver") or reverse("tickets:monitoreo_admin")
    observador_id = request.POST.get("observador") or ""
    nombre = (request.POST.get("nombre") or "").strip()[:80]
    observador = Usuario.objects.filter(
        pk=observador_id, rol=Usuario.Rol.OBSERVADOR
    ).first() if observador_id.isdigit() else None
    if observador is None:
        messages.error(request, "Elige un supervisor válido para la zona.")
        return redirect(volver)
    if not nombre:
        messages.error(request, "Ponle un nombre a la zona para crearla.")
        return redirect(volver)
    if ZonaObservador.objects.filter(
        observador=observador, nombre__iexact=nombre
    ).exists():
        messages.error(
            request, f"{observador.nombre} ya tiene una zona llamada «{nombre}»."
        )
        return redirect(volver)
    ZonaObservador.objects.create(observador=observador, nombre=nombre)
    _auditar(request.user, MonitoreoAuditoria.CREAR_ZONA, observador, nombre, "")
    messages.success(
        request, f"Zona «{nombre}» creada para {observador.nombre}."
    )
    return redirect(volver)


@admin_required
@login_required
def monitoreo_zona_miembro_agregar(request, pk):
    """Mete una cuenta a la zona desde el panel del administrador."""
    if request.method != "POST":
        return redirect(reverse("tickets:monitoreo_admin"))
    volver = request.POST.get("volver") or reverse("tickets:monitoreo_admin")
    zona = ZonaObservador.objects.select_related("observador").filter(pk=pk).first()
    if zona is None:
        return redirect(volver)
    correo = (request.POST.get("email") or "").strip().lower()
    if not correo:
        messages.error(request, "Escribe el correo de la cuenta para agregarla.")
        return redirect(volver)
    elemento, creado = ElementoMiLista.objects.get_or_create(
        observador=zona.observador,
        usuario_email=correo,
        defaults={
            "tipo": ElementoMiLista.TIPO_USUARIO,
            "usuario": Usuario.objects.filter(email__iexact=correo).first(),
            "zona": zona,
        },
    )
    if not creado and elemento.zona_id != zona.pk:
        elemento.zona = zona
        elemento.save(update_fields=["zona"])
    _auditar(
        request.user, MonitoreoAuditoria.AGREGAR_MIEMBRO, zona.observador,
        zona.nombre, correo,
    )
    messages.success(request, f"{correo} quedó en la zona «{zona.nombre}».")
    return redirect(volver)


_VISTA_PRINCIPAL_POR_ROL = {
    "admin": "Panel de administración",
    "tecnico": "Panel Técnico",
    "usuario": "Mis solicitudes",
    "observador": "Monitoreo",
}


@admin_required
def monitoreo_cuenta_detalle(request, pk):
    """Vista principal de la cuenta en seguimiento, según su rol.

    Al darle clic al nombre (o a la fila) se abre lo mismo que ve esa
    cuenta al entrar, pero con todo lo suyo: si es usuario, sus
    solicitudes creadas; si es técnico, sus asignados y su calificación;
    si es observador, su lista y sus zonas. Lo creado siempre sale, y lo
    asignado sale cuando tiene asignaciones.
    """
    from django.http import Http404

    elemento = (
        ElementoMiLista.objects.filter(pk=pk)
        .select_related("observador", "usuario", "punto", "zona")
        .first()
    )
    if elemento is None:
        raise Http404
    cuenta = elemento.usuario
    correo = (elemento.usuario_email or "").strip().lower()
    rol = getattr(cuenta, "rol", None) or "usuario"
    tickets = list(
        Ticket.objects.filter(solicitante_email__iexact=correo)
        .select_related("tecnico_asignado", "categoria")
        .prefetch_related("adjuntos", "comentarios__usuario")
        .order_by("-fecha_creacion") if correo else []
    )
    tecnicos = {}
    for t in tickets:
        nombre = (
            (t.tecnico_asignado.nombre if t.tecnico_asignado_id else "") or ""
        ).strip()
        if nombre:
            tecnicos[nombre] = tecnicos.get(nombre, 0) + 1
    # Lo asignado: lo que atiende esa cuenta como técnico (o admin de apoyo).
    asignados = list(
        Ticket.objects.filter(tecnico_asignado=cuenta)
        .select_related("tecnico_asignado")
        .prefetch_related("adjuntos", "comentarios__usuario")
        .order_by("-fecha_creacion") if cuenta is not None else []
    )
    calificacion = None
    if rol == Usuario.Rol.TECNICO and cuenta is not None:
        from apps.tickets.views import _calificacion_de

        calificacion = _calificacion_de(cuenta)
    # Lo vigilado: si la cuenta es observadora, su lista y sus zonas.
    lista_total = 0
    zonas_obs = []
    if rol == Usuario.Rol.OBSERVADOR and cuenta is not None:
        lista_total = ElementoMiLista.objects.filter(observador=cuenta).count()
        zonas_obs = list(
            ZonaObservador.objects.filter(observador=cuenta).order_by("nombre")
        )
    return render(
        request,
        "tickets/monitoreo_cuenta.html",
        {
            "elemento": elemento,
            "cuenta": cuenta,
            "correo": correo,
            "rol": rol,
            "vista_principal": _VISTA_PRINCIPAL_POR_ROL.get(rol, "Mis solicitudes"),
            "tickets": tickets,
            "total": len(tickets),
            "abiertos": sum(
                1 for t in tickets
                if t.estado in (Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO)
            ),
            "en_progreso": sum(
                1 for t in tickets if t.estado == Ticket.Estado.EN_PROGRESO
            ),
            "resueltos": sum(
                1 for t in tickets
                if t.estado in (Ticket.Estado.RESUELTO, Ticket.Estado.CERRADO)
            ),
            "tecnicos": sorted(tecnicos.items(), key=lambda kv: (-kv[1], kv[0])),
            "asignados": asignados,
            "asignados_total": len(asignados),
            "asignados_abiertos": sum(
                1 for t in asignados
                if t.estado in (Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO)
            ),
            "calificacion": calificacion,
            "lista_total": lista_total,
            "zonas_obs": zonas_obs,
        },
    )


@admin_required
@login_required
def monitoreo_zonas(request):
    """Asigna o quita una zona completa a un observador."""
    if request.method != "POST":
        return redirect(reverse("tickets:monitoreo_admin"))
    volver = request.POST.get("volver") or reverse("tickets:monitoreo_admin")
    observador_id = request.POST.get("observador") or ""
    nombre_zona = (request.POST.get("punto") or "").strip()
    accion = request.POST.get("accion") or "asignar"

    observador = Usuario.objects.filter(
        pk=observador_id, rol=Usuario.Rol.OBSERVADOR
    ).first() if observador_id.isdigit() else None
    punto = Punto.objects.filter(nombre=nombre_zona).first() if nombre_zona else None
    if observador is None or punto is None:
        return redirect(volver)

    if accion == "quitar":
        ObservadorPunto.objects.filter(observador=observador, punto=punto).delete()
        _auditar(
            request.user, MonitoreoAuditoria.QUITAR_PUNTO, observador,
            nombre_zona, "",
        )
    else:
        ObservadorPunto.objects.get_or_create(observador=observador, punto=punto)
        _auditar(
            request.user, MonitoreoAuditoria.ASIGNAR_PUNTO, observador,
            nombre_zona, "",
        )
    return redirect(volver)
