"""Armar desde el administrador la lista de monitoreo del observador.

El observador solo puede agregar a su lista los usuarios que ya encuentra por
su cuenta. Desde aquí el administrador ve el tabla completa de usuarios
activos, con filtros, y los guarda en la zona que le toca para que el
observador los vea en su panel.
"""

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.accounts.models import Usuario

from .decorators import admin_required
from .models import (
    ElementoMiLista,
    ObservadorPunto,
    Punto,
    Ticket,
    ZonaObservador,
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
    q = (request.GET.get("q") or "").strip()
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
    ya_mis_lista = {
        (e.usuario_email or "").strip().lower()
        for e in _elementos_de(observador) if (e.usuario_email or "").strip()
    } if observador else set()
    zonas_ya = {
        (e.punto.nombre if e.punto_id else "")
        for e in _elementos_de(observador).select_related("punto")
    } if observador else set()

    # Zonas que ve el observador elegido: las asignadas y las de su lista.
    zonas = sorted(set(_zonas_de(observador)) | zonas_ya) if observador else []
    if not zonas:
        zonas = sorted(Punto.objects.values_list("nombre", flat=True))

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
    if zona:
        usuarios = usuarios.filter(ubicacion__icontains=zona)

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
    for u in usuarios.order_by("nombre"):
        correo = (u.email or "").strip().lower()
        filas.append(
            {
                "obj": u,
                "nombre": u.nombre or u.email,
                "email": correo,
                "rol": u.get_rol_display(),
                "ubicacion": u.ubicacion or "—",
                "abiertos": abiertos.get(correo, 0),
                "ya_agregado": correo in ya_mis_lista,
            }
        )

    if estado == "agregados":
        filas = [f for f in filas if f["ya_agregado"]]
    elif estado == "pendientes":
        filas = [f for f in filas if not f["ya_agregado"]]
    elif estado == "con_tickets":
        filas = [f for f in filas if f["abiertos"] > 0]

    zona_elegida = zona or (zonas[0] if zonas else "")
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
            "zona_elegida": zona_elegida,
            "total": len(filas),
            "zonas_creadas": creadas,
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
    supervisores = list(
        Usuario.objects.filter(rol=Usuario.Rol.OBSERVADOR).order_by("nombre")
    )
    if not supervisores:
        return []
    zonas = list(
        ZonaObservador.objects.filter(observador__in=supervisores)
        .select_related("observador")
        .prefetch_related("elementos__usuario")
        .order_by("observador__nombre", "nombre")
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
        por_supervisor[z.observador_id]["zonas"].append(
            {
                "zona": z,
                "miembros": miembros,
                "abiertos": sum(m["abiertos"] for m in miembros),
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
    if nombre_zona:
        punto, _ = Punto.objects.get_or_create(nombre=nombre_zona[:80])

    # Si ya estaba en la lista, se actualiza la zona en vez de duplicarlo.
    ElementoMiLista.objects.update_or_create(
        observador=observador,
        usuario_email=correo,
        defaults={
            "tipo": ElementoMiLista.TIPO_USUARIO,
            "usuario": Usuario.objects.filter(email__iexact=correo).first(),
            "punto": punto,
        },
    )

    # La zona tambien queda asignada al observador para que pueda verla.
    if punto is not None:
        ObservadorPunto.objects.get_or_create(observador=observador, punto=punto)

    return redirect(volver)


@admin_required
@login_required
def monitoreo_quitar(request, pk):
    """Saca un elemento de la lista del observador."""
    if request.method != "POST":
        return redirect(reverse("tickets:monitoreo_admin"))
    observador_id = request.POST.get("observador") or ""
    volver = request.POST.get("volver") or reverse("tickets:monitoreo_admin")
    ElementoMiLista.objects.filter(
        pk=pk, observador__pk=observador_id if observador_id.isdigit() else 0
    ).delete()
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
    elemento.zona = None
    elemento.save(update_fields=["zona"])
    return redirect(volver)


@admin_required
@login_required
def monitoreo_zona_eliminar(request, pk):
    """Elimina una zona creada por un observador (su gente no se borra)."""
    if request.method != "POST":
        return redirect(reverse("tickets:monitoreo_admin"))
    volver = request.POST.get("volver") or reverse("tickets:monitoreo_admin")
    ZonaObservador.objects.filter(pk=pk).delete()
    return redirect(volver)


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
    else:
        ObservadorPunto.objects.get_or_create(observador=observador, punto=punto)
    return redirect(volver)
