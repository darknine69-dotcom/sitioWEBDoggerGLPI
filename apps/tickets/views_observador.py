"""Módulo del Observador.

El observador entra con su correo y contraseña, igual que los demás roles, y
el sistema valida que sea observador antes de mostrarle nada. Su trabajo es
mirar: ve los puntos o zonas que tiene asignados, las personas de esos
puntos, y el estado de los tickets asociados. No puede crear ni editar
tickets, solo consultar, agregar elementos a su lista personal y sacar
reportes.

Las consultas se filtran siempre por los puntos asignados al observador:
aunque manipule la URL no llega a ver zonas ajenas.
"""

import csv

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Usuario

from .models import ElementoMiLista, ObservadorPunto, Punto, Ticket

# Estados que el observador monitorea: verde activo, rojo incidencia, amarillo pendiente.
ESTADO_VERDE = "verde"
ESTADO_ROJO = "rojo"
ESTADO_AMARILLO = "amarillo"

_ACTIVOS = [Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO]
_URGENTE = Ticket.Prioridad.URGENTE


def solo_observador(vista):
    """Deja pasar solo a observadores activos; el resto va a la403."""

    @login_required(login_url="accounts:login")
    def envoltura(request, *args, **kwargs):
        usuario = request.user
        if not getattr(usuario, "es_observador", False):
            return render(request, "forbidden.html", status=403)
        return vista(request, *args, **kwargs)

    envoltura.__name__ = vista.__name__
    envoltura.__doc__ = vista.__doc__
    return envoltura


# ------------------------------------------------------------------ helpers
def puntos_del_observador(usuario):
    """Nombres de los puntos asignados al observador (vacío = todos)."""
    return list(
        ObservadorPunto.objects.filter(observador=usuario)
        .select_related("punto")
        .order_by("punto__nombre")
        .values_list("punto__nombre", flat=True)
    )


def _visible_a_observador(usuario, consulta):
    """Restringe tickets a los puntos asignados, si tiene alguno."""
    puntos = puntos_del_observador(usuario)
    if not puntos:
        return consulta.none()
    return consulta.filter(solicitante_punto__in=puntos)


def _estado_de(ticket, ahora):
    """Traduce un ticket al color del panel de monitoreo."""
    if ticket.estado in (Ticket.Estado.RESUELTO, Ticket.Estado.CERRADO):
        return ESTADO_VERDE
    if ticket.prioridad == _URGENTE and ticket.estado == Ticket.Estado.ABIERTO:
        return ESTADO_ROJO
    if ticket.estado == Ticket.Estado.EN_PROGRESO:
        return ESTADO_AMARILLO
    return ESTADO_AMARILLO


def _contar_por_estado(queryset):
    conteo = {ESTADO_VERDE: 0, ESTADO_ROJO: 0, ESTADO_AMARILLO: 0}
    for t in queryset.only("estado", "prioridad"):
        conteo[_estado_de(t, timezone.now())] += 1
    return conteo


def _resumen_por_punto(usuario):
    """Tarjetas de la vista principal: una por punto asignado."""
    puntos = puntos_del_observador(usuario)
    if not puntos:
        return []

    ahora = timezone.now()
    consulta = _visible_a_observador(usuario, Ticket.objects.all())
    por_punto = {}
    for t in consulta.select_related("tecnico_asignado").only(
        "solicitante_punto", "estado", "prioridad", "codigo", "tecnico_asignado__nombre"
    ):
        clave = (t.solicitante_punto or "").strip()
        if clave not in puntos:
            continue
        fila = por_punto.setdefault(
            clave,
            {
                "punto": clave,
                "total": 0,
                "estado": ESTADO_VERDE,
                "sin_tecnico": 0,
                "verde": 0,
                "rojo": 0,
                "amarillo": 0,
                "abiertos": 0,
            },
        )
        fila["total"] += 1
        estado = _estado_de(t, ahora)
        fila[estado] += 1
        if t.estado in _ACTIVOS:
            fila["abiertos"] += 1
        # El peor estado manda: si hay algo rojo, el punto aparece en rojo.
        orden = {ESTADO_VERDE: 0, ESTADO_AMARILLO: 1, ESTADO_ROJO: 2}
        if orden[estado] > orden[fila["estado"]]:
            fila["estado"] = estado
        if not t.tecnico_asignado_id:
            fila["sin_tecnico"] += 1
    return [por_punto[p] for p in puntos]


# ------------------------------------------------------------------- vistas
@solo_observador
def panel_observador(request):
    """Vista principal: solo los puntos asignados y quién los atiende."""
    usuario = request.user
    Punto.sincronizar()
    tarjetas = _resumen_por_punto(usuario)

    # Personas que aparecen en los tickets de esos puntos.
    visibles = _visible_a_observador(usuario, Ticket.objects.all())
    personas = {}
    for t in visibles.only(
        "solicitante_email", "solicitante_nombre", "solicitante_punto",
        "estado", "prioridad", "codigo", "id",
    ):
        correo = (t.solicitante_email or "").strip().lower()
        clave = correo or (t.solicitante_nombre or "").strip().lower()
        if not clave:
            continue
        fila = personas.setdefault(
            clave,
            {
                "email": correo,
                "nombre": t.solicitante_nombre,
                "puntos": set(),
                "total": 0,
                "abiertos": 0,
                "estado": ESTADO_VERDE,
            },
        )
        fila["total"] += 1
        if (t.solicitante_punto or "").strip():
            fila["puntos"].add(t.solicitante_punto.strip())
        if t.estado in _ACTIVOS:
            fila["abiertos"] += 1
        estado = _estado_de(t, timezone.now())
        orden = {ESTADO_VERDE: 0, ESTADO_AMARILLO: 1, ESTADO_ROJO: 2}
        if orden[estado] > orden[fila["estado"]]:
            fila["estado"] = estado

    lista_personas = []
    for fila in personas.values():
        fila["puntos"] = sorted(fila["puntos"])
        lista_personas.append(fila)
    lista_personas.sort(key=lambda f: (-f["abiertos"], f["nombre"] or ""))

    total_tickets = visibles.count()
    return render(
        request,
        "observador/panel.html",
        {
            "tarjetas": tarjetas,
            "personas": lista_personas,
            "total_tickets": total_tickets,
            "total_personas": len(lista_personas),
            "total_zonas": len(tarjetas),
            "personas_en_alerta": sum(
                1 for f in lista_personas if f["estado"] == ESTADO_ROJO
            ),
            "conteo": _contar_por_estado(visibles),
            "sin_puntos": not tarjetas,
        },
    )


@solo_observador
def buscar_observador(request):
    """Búsqueda y agregación: encuentra personas o puntos y los mete a su lista.

    El buscador nunca sale de los puntos asignados: lo que no es suyo no
    aparece, así que no se puede filtrar la información por otro lado.
    """
    usuario = request.user
    q = request.GET.get("q", "").strip()
    tipo = request.GET.get("tipo", "todo").strip()
    resultados = {"personas": [], "puntos": []}

    # Las zonas nuevas se registran antes de filtrar, para que el buscador
    # no se quede corto si los tickets todavia no las tienen.
    Punto.sincronizar()
    puntos = puntos_del_observador(usuario)

    if q:
        # Puntos: coincidencia por nombre dentro de los asignados.
        if tipo in ("todo", "punto"):
            consulta_p = Punto.objects.filter(nombre__icontains=q)
            if puntos:
                consulta_p = consulta_p.filter(nombre__in=puntos)
            else:
                consulta_p = consulta_p.none()
            resultados["puntos"] = [
                {
                    "nombre": p.nombre,
                    "ya_agregado": ElementoMiLista.objects.filter(
                        observador=usuario, punto=p
                    ).exists(),
                }
                for p in consulta_p.order_by("nombre")[:40]
            ]

        # Personas: las que tienen tickets en los puntos asignados.
        if tipo in ("todo", "persona"):
            visibles = _visible_a_observador(usuario, Ticket.objects.all()).filter(
                Q(solicitante_nombre__icontains=q) | Q(solicitante_email__icontains=q)
            )
            vistos = {}
            for t in visibles.only("solicitante_email", "solicitante_nombre", "solicitante_punto"):
                correo = (t.solicitante_email or "").strip().lower()
                clave = correo or (t.solicitante_nombre or "").strip().lower()
                if not clave or clave in vistos:
                    continue
                fila = vistos[clave] = {
                    "email": correo,
                    "nombre": t.solicitante_nombre,
                    "punto": (t.solicitante_punto or "").strip(),
                }
                ya = ElementoMiLista.objects.filter(observador=usuario)
                if correo:
                    fila["ya_agregado"] = ya.filter(usuario_email=correo).exists()
                elif fila["punto"]:
                    fila["ya_agregado"] = ya.filter(punto__nombre=fila["punto"]).exists()
                else:
                    fila["ya_agregado"] = False
            resultados["personas"] = list(vistos.values())[:40]

    return render(
        request,
        "observador/buscar.html",
        {"q": q, "tipo": tipo, "resultados": resultados, "puntos": puntos},
    )


@solo_observador
def usuarios_observador(request):
    """Usuarios que se ven desde las zonas asignadas, con filtros.

    Es el equivalente del listado de usuarios del administrador, pero acotado:
    solo aparecen las personas que tienen tickets en los puntos del observador,
    con su estado y sus números. No hay forma de editar ni de salir de la zona.
    """
    usuario = request.user
    q = request.GET.get("q", "").strip()
    punto = request.GET.get("punto", "").strip()
    estado = request.GET.get("estado", "").strip()
    orden = request.GET.get("orden", "abiertos").strip()

    visibles = _visible_a_observador(usuario, Ticket.objects.all())

    if punto:
        visibles = visibles.filter(solicitante_punto=punto)

    ahora = timezone.now()
    ya_en_lista = {
        (e.usuario_email or "").strip().lower()
        for e in ElementoMiLista.objects.filter(observador=usuario)
        if (e.usuario_email or "").strip()
    }

    personas = {}
    for t in visibles.only(
        "solicitante_email", "solicitante_nombre", "solicitante_punto",
        "estado", "prioridad", "fecha_creacion",
    ):
        correo = (t.solicitante_email or "").strip().lower()
        clave = correo or (t.solicitante_nombre or "").strip().lower()
        if not clave:
            continue
        fila = personas.setdefault(
            clave,
            {
                "clave": clave,
                "email": correo,
                "nombre": t.solicitante_nombre or (correo or "Sin nombre"),
                "puntos": set(),
                "total": 0,
                "abiertos": 0,
                "estado": ESTADO_VERDE,
                "ultimo": t.fecha_creacion,
                "ya_agregado": correo in ya_en_lista,
            },
        )
        fila["total"] += 1
        if t.solicitante_punto:
            fila["puntos"].add(t.solicitante_punto.strip())
        if t.estado in _ACTIVOS:
            fila["abiertos"] += 1
        if t.fecha_creacion and (fila["ultimo"] is None or t.fecha_creacion > fila["ultimo"]):
            fila["ultimo"] = t.fecha_creacion
        orden_estado = {ESTADO_VERDE: 0, ESTADO_AMARILLO: 1, ESTADO_ROJO: 2}
        est = _estado_de(t, ahora)
        if orden_estado[est] > orden_estado[fila["estado"]]:
            fila["estado"] = est

    filas = list(personas.values())
    for f in filas:
        f["puntos"] = sorted(f["puntos"])

    total_sin_filtro = len(filas)

    if q:
        aguja = q.lower()
        filas = [
            f for f in filas
            if aguja in (f["nombre"] or "").lower() or aguja in (f["email"] or "").lower()
        ]

    if estado == "activos":
        filas = [f for f in filas if f["abiertos"] > 0]
    elif estado == "alerta":
        filas = [f for f in filas if f["estado"] == ESTADO_ROJO]
    elif estado == "tranquilos":
        filas = [f for f in filas if f["estado"] == ESTADO_VERDE]

    if orden == "nombre":
        filas.sort(key=lambda f: (f["nombre"] or "").lower())
    elif orden == "tickets":
        filas.sort(key=lambda f: (-f["total"], (f["nombre"] or "").lower()))
    elif orden == "recientes":
        filas.sort(key=lambda f: (f["ultimo"] is None, -(f["ultimo"].timestamp() if f["ultimo"] else 0)))
    else:
        filas.sort(key=lambda f: (-f["abiertos"], f["estado"] != ESTADO_ROJO, (f["nombre"] or "").lower()))

    conteo = {ESTADO_VERDE: 0, ESTADO_ROJO: 0, ESTADO_AMARILLO: 0}
    for f in filas:
        conteo[f["estado"]] += 1

    return render(
        request,
        "observador/usuarios.html",
        {
            "filas": filas,
            "conteo": conteo,
            "total": len(filas),
            "total_sin_filtro": total_sin_filtro,
            "q": q,
            "punto_sel": punto,
            "estado_sel": estado,
            "orden_sel": orden if orden in ("abiertos", "nombre", "tickets", "recientes") else "abiertos",
            "puntos": puntos_del_observador(usuario),
        },
    )


@solo_observador
def mi_lista_observador(request):
    """Lista dinámica: lo que el observador fue agregando, con su estado."""
    usuario = request.user
    elementos = (
        ElementoMiLista.objects.filter(observador=usuario)
        .select_related("usuario", "punto")
        .order_by("-creado_en")
    )
    filas = _filas_de_mi_lista(usuario, elementos)
    conteo = {ESTADO_VERDE: 0, ESTADO_ROJO: 0, ESTADO_AMARILLO: 0}
    for f in filas:
        conteo[f["estado"]] += 1
    return render(
        request,
        "observador/mi_lista.html",
        {"filas": filas, "conteo": conteo, "total": len(filas)},
    )


def _filas_de_mi_lista(usuario, elementos):
    """Une cada elemento de la lista con el estado de sus tickets."""
    puntos = puntos_del_observador(usuario)
    visibles = _visible_a_observador(usuario, Ticket.objects.all())
    ahora = timezone.now()
    filas = []
    for e in elementos:
        consulta = visibles
        correo = (e.usuario_email or "").strip().lower()
        if correo:
            consulta = visibles.filter(
                Q(solicitante_email__iexact=correo)
                | Q(solicitante_nombre__iexact=e.usuario.nombre if e.usuario_id else "")
            )
        elif e.punto_id:
            consulta = visibles.filter(solicitante_punto=e.punto.nombre)
        tickets = list(consulta.order_by("-fecha_creacion")[:60])
        estado = ESTADO_VERDE
        orden = {ESTADO_VERDE: 0, ESTADO_AMARILLO: 1, ESTADO_ROJO: 2}
        for t in tickets:
            est = _estado_de(t, ahora)
            if orden[est] > orden[estado]:
                estado = est
        filas.append(
            {
                "elemento": e,
                "nombre": (
                    e.usuario.nombre
                    if e.usuario_id
                    else (e.usuario_email or (e.punto.nombre if e.punto_id else "—"))
                ),
                "detalle": (
                    (e.punto.nombre if e.punto_id else "")
                    + (" · " if e.punto_id and e.usuario_id else "")
                    + (e.usuario.nombre if e.usuario_id else "")
                ).strip(" ·"),
                "tickets": tickets,
                "abiertos": sum(1 for t in tickets if t.estado in _ACTIVOS),
                "total": len(tickets),
                "estado": estado,
            }
        )
    return filas


@solo_observador
def agregar_mi_lista(request):
    """Botón 'Agregar a mi lista': guarda la persona o el punto elegido."""
    if request.method != "POST":
        raise Http404
    usuario = request.user

    correo = (request.POST.get("email") or "").strip().lower()
    nombre_punto = (request.POST.get("punto") or "").strip()

    elemento = None
    if correo:
        # La persona puede no tener usuario registrado: guardamos el correo
        # siempre y enlazamos el usuario solo si existe.
        ElementoMiLista.objects.filter(
            observador=usuario, usuario_email=correo
        ).delete()
        elemento = ElementoMiLista.objects.create(
            observador=usuario,
            tipo=ElementoMiLista.TIPO_USUARIO,
            usuario_email=correo,
            usuario=Usuario.objects.filter(email__iexact=correo).first(),
        )
    elif nombre_punto:
        punto = Punto.objects.filter(nombre=nombre_punto).first()
        if punto is None:
            punto = Punto.objects.create(nombre=nombre_punto[:80])
        elemento, _ = ElementoMiLista.objects.get_or_create(
            observador=usuario,
            punto=punto,
            defaults={"tipo": ElementoMiLista.TIPO_PUNTO},
        )
    else:
        return redirect(reverse("tickets:obs_buscar"))

    destino = request.POST.get("volver") or reverse("tickets:obs_mi_lista")
    return redirect(destino)


@solo_observador
def quitar_mi_lista(request, pk):
    """Saca un elemento de la lista personal (no borra tickets)."""
    if request.method != "POST":
        raise Http404
    ElementoMiLista.objects.filter(pk=pk, observador=request.user).delete()
    return redirect(request.POST.get("volver") or reverse("tickets:obs_mi_lista"))


@solo_observador
def monitorear_observador(request):
    """Monitoreo: la lista con sus indicadores y las acciones de reporte."""
    usuario = request.user
    elementos = (
        ElementoMiLista.objects.filter(observador=usuario)
        .select_related("usuario", "punto")
        .order_by("-creado_en")
    )
    filas = _filas_de_mi_lista(usuario, elementos)
    conteo = {ESTADO_VERDE: 0, ESTADO_ROJO: 0, ESTADO_AMARILLO: 0}
    for f in filas:
        conteo[f["estado"]] += 1
    return render(
        request,
        "observador/monitoreo.html",
        {"filas": filas, "conteo": conteo, "total": len(filas)},
    )


@solo_observador
def exportar_observador(request):
    """Descarga la lista del observador como CSV, para el reporte."""
    usuario = request.user
    filas = _filas_de_mi_lista(
        usuario,
        ElementoMiLista.objects.filter(observador=usuario).select_related(
            "usuario", "punto"
        ),
    )
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = (
        'attachment; filename="monitoreo-observador.csv"'
    )
    escritura = csv.writer(respuesta)
    escritura.writerow(["Elemento", "Detalle", "Estado", "Tickets abiertos", "Tickets totales"])
    for f in filas:
        escritura.writerow([f["nombre"], f["detalle"], f["estado"], f["abiertos"], f["total"]])
    return respuesta
