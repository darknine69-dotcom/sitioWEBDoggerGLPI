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
import logging
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.db.models.functions import Lower
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.accounts.models import Usuario

from . import ans_avisos
from .models import (
    ElementoMiLista,
    MonitoreoAuditoria,
    ObservadorPunto,
    Punto,
    Ticket,
    TicketComentario,
    ZonaObservador,
)
from .views_monitoreo import (
    _auditar,
    _auditoria_enriquecida,
    _motivo_post,
    _version_equipo,
    _xlsx_auditoria,
)

# Estados que el observador monitorea: verde activo, rojo incidencia, amarillo pendiente.
ESTADO_VERDE = "verde"
ESTADO_ROJO = "rojo"
ESTADO_AMARILLO = "amarillo"

# Paleta cerrada de las carpetas: el color viaja en el formulario y aquí se
# valida contra la lista, así una carpeta no puede quedarse con cualquier
# texto dentro de un atributo de estilo.
PALETA_ZONA = (
    "#D62B1F",  # rojo
    "#E0871B",  # naranja
    "#E0A106",  # ámbar
    "#2F7D4F",  # verde
    "#0E7490",  # turquesa
    "#1D4ED8",  # azul
    "#6D28D9",  # violeta
    "#BE185D",  # magenta
    "#6B6259",  # gris
    "#111827",  # negro
)

_ACTIVOS = [Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO]
_URGENTE = Ticket.Prioridad.URGENTE

logger = logging.getLogger(__name__)


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
    from apps.tickets.services.cache import cachear, clave

    def _cargar():
        return list(
            ObservadorPunto.objects.filter(observador=usuario)
            .select_related("punto")
            .order_by("punto__nombre")
            .values_list("punto__nombre", flat=True)
        )

    return cachear(clave("obs", "puntos", usuario.pk), _cargar, segundos=300)


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
    for clave in puntos:
        # La zona asignada existe aunque todavía no tenga tickets.
        por_punto[clave] = {
            "punto": clave,
            "total": 0,
            "estado": ESTADO_VERDE,
            "sin_tecnico": 0,
            "verde": 0,
            "rojo": 0,
            "amarillo": 0,
            "abiertos": 0,
        }
    for t in consulta.select_related("tecnico_asignado").only(
        "solicitante_punto", "estado", "prioridad", "codigo", "tecnico_asignado__nombre"
    ):
        clave = (t.solicitante_punto or "").strip()
        if clave not in puntos:
            continue
        fila = por_punto[clave]
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


def _resumen_por_correo(usuario, global_scope=False, correos=None):
    """Acumula, por correo, los tickets de las zonas del observador.

    De cada persona deja cuántos tickets lleva, cuántos se resolvieron y qué
    técnicos tiene asignados. Es lo que permite mostrar el avance de la
    resolución y quién está viendo el caso.

    Con global_scope=True cuenta todos los tickets de cada correo, sin
    importar el punto: se usa para la gente que ya está en la lista del
    observador, a la que se le muestran sus datos reales.

    Con correos=[] se limita a esos correos, para no recorrer la tabla
    entera cuando solo se necesitan las cuentas de la lista.
    """
    resumen = {}
    base = (
        Ticket.objects.all()
        if global_scope
        else _visible_a_observador(usuario, Ticket.objects.all())
    )
    if correos:
        base = base.annotate(
            correo_normalizado=Lower("solicitante_email")
        ).filter(correo_normalizado__in=list(correos))

    def fila(correo):
        return resumen.setdefault(
            correo,
            {
                "nombre": "",
                "total": 0,
                "abiertos": 0,
                "urgentes": 0,
                "resueltos": 0,
                "cerrados": 0,
                "en_progreso": 0,
                "tecnicos": {},
                "puntos": set(),
                "estado": ESTADO_VERDE,
                "ultimo": None,
            },
        )

    for t in base.select_related(
        "tecnico_asignado"
    ).order_by("fecha_creacion"):
        correo = (t.solicitante_email or "").strip().lower()
        if not correo:
            continue
        f = fila(correo)
        if t.solicitante_nombre:
            # Al ordenarse por fecha, queda el nombre del ticket más nuevo.
            f["nombre"] = t.solicitante_nombre.strip()
        f["total"] += 1
        if t.estado in _ACTIVOS:
            f["abiertos"] += 1
        if t.prioridad == _URGENTE and t.estado in _ACTIVOS:
            f["urgentes"] += 1
        if t.estado == Ticket.Estado.RESUELTO:
            f["resueltos"] += 1
        elif t.estado == Ticket.Estado.CERRADO:
            f["cerrados"] += 1
        elif t.estado == Ticket.Estado.EN_PROGRESO:
            f["en_progreso"] += 1
        if t.tecnico_asignado_id:
            nombre = (t.tecnico_asignado.nombre or "").strip()
            if nombre:
                f["tecnicos"][nombre] = f["tecnicos"].get(nombre, 0) + 1
        if t.solicitante_punto:
            f["puntos"].add(t.solicitante_punto.strip())
        if t.fecha_creacion and (f["ultimo"] is None or t.fecha_creacion > f["ultimo"]):
            f["ultimo"] = t.fecha_creacion

    for f in resumen.values():
        f["puntos"] = sorted(f["puntos"])
        f["tecnico_principal"] = (
            max(f["tecnicos"].items(), key=lambda kv: kv[1])[0]
            if f["tecnicos"] else ""
        )
        f["tecnicos"] = [
            {"nombre": nombre, "tickets": cuentas}
            for nombre, cuentas in sorted(
                f["tecnicos"].items(), key=lambda kv: (-kv[1], kv[0])
            )
        ]
        f["cerrados_total"] = f["resueltos"] + f["cerrados"]
        f["avance"] = (
            int(round(100.0 * f["cerrados_total"] / f["total"])) if f["total"] else 0
        )
        # Verde si ya no queda nada pendiente, amarillo si sigue abierto.
        if f["abiertos"]:
            f["estado"] = ESTADO_AMARILLO
        else:
            f["estado"] = ESTADO_VERDE
    return resumen


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

    # Cuentas de la aplicación en sus puntos, aunque no tengan tickets:
    # lo que el admin crea (o asigna de ubicación) se ve aquí de una vez,
    # con sus números en cero hasta que levanten su primer ticket.
    nombres_puntos = puntos_del_observador(usuario)
    resumen = _resumen_por_correo(usuario)
    if nombres_puntos:
        vistos = {f["email"] for f in lista_personas if f["email"]}
        for u in Usuario.objects.filter(
            activo=True, is_active=True, ubicacion__in=nombres_puntos
        ).order_by("nombre"):
            correo = (u.email or "").strip().lower()
            if not correo or correo in vistos:
                continue
            vistos.add(correo)
            r = resumen.get(correo, {})
            lista_personas.append(
                {
                    "email": correo,
                    "nombre": u.nombre or correo,
                    "rol": u.get_rol_display(),
                    "puntos": [u.ubicacion],
                    "total": r.get("total", 0),
                    "abiertos": r.get("abiertos", 0),
                    "tecnico": r.get("tecnico_principal", ""),
                    "estado": r.get("estado", ESTADO_VERDE),
                    "sin_tickets": True,
                }
            )
    for fila in lista_personas:
        fila.setdefault("rol", "")
        if not fila.get("tecnico") and fila["email"]:
            fila["tecnico"] = resumen.get(fila["email"], {}).get(
                "tecnico_principal", ""
            )
    lista_personas.sort(key=lambda f: (-f["abiertos"], f["nombre"] or ""))

    total_tickets = visibles.count()
    # El panel es el monitoreo: los mismos grupos por zona con el detalle
    # completo de usuarios, tickets, técnicos y respuestas. De una misma
    # pasada salen también la actividad reciente y «Presionar», que el
    # panel enseña al final.
    contexto_mon = _contexto_monitoreo(usuario)
    grupos = contexto_mon["grupos"]
    # Buscar y agregar integrado al panel: encuentra cuentas por nombre,
    # correo o ubicación para agregarlas a la lista sin salir de aquí.
    q_busc = (request.GET.get("q_busc") or "")[:120].strip()
    busqueda = []
    if q_busc:
        ya = {
            (e.usuario_email or "").strip().lower()
            for e in ElementoMiLista.objects.filter(observador=usuario)
            if (e.usuario_email or "").strip()
        }
        for u in Usuario.objects.filter(activo=True, is_active=True).filter(
            Q(nombre__icontains=q_busc) | Q(email__icontains=q_busc)
            | Q(ubicacion__icontains=q_busc)
        ).order_by("nombre")[:12]:
            correo = (u.email or "").strip().lower()
            busqueda.append(
                {
                    "nombre": u.nombre or u.email,
                    "email": correo,
                    "rol": u.get_rol_display(),
                    "ubicacion": u.ubicacion or "—",
                    "ya_agregado": correo in ya,
                }
            )
    return render(
        request,
        "observador/panel.html",
        {
            "tarjetas": tarjetas,
            "personas": lista_personas,
            "total_tickets": total_tickets,
            "total_personas": len(lista_personas),
            "total_zonas": len(tarjetas),
            "abiertos": visibles.filter(estado__in=_ACTIVOS).count(),
            "mi_lista_total": ElementoMiLista.objects.filter(
                observador=usuario
            ).count(),
            "personas_en_alerta": sum(
                1 for f in lista_personas if f["estado"] == ESTADO_ROJO
            ),
            "conteo": _contar_por_estado(visibles),
            "sin_puntos": not tarjetas,
            "q_busc": q_busc,
            "busqueda": busqueda,
            "grupos": grupos,
            # Lo mismo que en Monitoreo: los técnicos con carga abierta y lo
            # último que pasó en la lista, para presionar sin cambiar de vista.
            "presionar": contexto_mon["presionar"],
            "actividad": contexto_mon["actividad"],
        },
    )


@solo_observador
def buscar_observador(request):
    """Búsqueda y agregación: encuentra personas o puntos y los mete a su lista.

    Busca en dos lados: en las cuentas de la aplicación (las mismas que ve el
    administrador) y en los solicitantes que dejaron tickets en las zonas del
    observador. Los puntos siguen limitados a los asignados.
    """
    usuario = request.user
    q = (request.GET.get("q", "") or "")[:120].strip()
    tipo = request.GET.get("tipo", "todo").strip()
    resultados = {"cuentas": [], "personas": [], "puntos": []}

    # Las zonas nuevas se registran antes de filtrar, para que el buscador
    # no se quede corto si los tickets todavia no las tienen.
    Punto.sincronizar()
    puntos = puntos_del_observador(usuario)

    if q:
        # Cuentas de la aplicación: mismo origen que la vista del admin, para
        # que el observador encuentre a cualquiera que tenga usuario.
        if tipo in ("todo", "persona"):
            ya = set(
                (e.usuario_email or "").strip().lower()
                for e in ElementoMiLista.objects.filter(observador=usuario)
            )
            resumen = _resumen_por_correo(usuario)
            consulta = Usuario.objects.filter(activo=True, is_active=True).filter(
                Q(nombre__icontains=q) | Q(email__icontains=q)
                | Q(ubicacion__icontains=q)
            ).order_by("nombre")[:40]
            for u in consulta:
                correo = (u.email or "").strip().lower()
                r = resumen.get(correo, {})
                resultados["cuentas"].append(
                    {
                        "nombre": u.nombre or u.email,
                        "email": correo,
                        "rol": u.get_rol_display(),
                        "ubicacion": u.ubicacion,
                        "tecnico": r.get("tecnico_principal", ""),
                        "total": r.get("total", 0),
                        "abiertos": r.get("abiertos", 0),
                        "avance": r.get("avance", 0),
                        "falta": 100 - r.get("avance", 0),
                        "ya_agregado": correo in ya,
                    }
                )

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
            resultados["personas"] = [
                p for p in vistos.values()
                if p["email"] not in {c["email"] for c in resultados["cuentas"]}
            ][:40]

    return render(
        request,
        "observador/buscar.html",
        {"q": q, "tipo": tipo, "resultados": resultados, "puntos": puntos},
    )


@solo_observador
def usuarios_observador(request):
    """Tabla única de las personas que el observador tiene a la vista.

    Es la tabla de «Todos los usuarios»: junta las cuentas del aplicativo
    con la gente que no tiene cuenta pero levantó tickets en sus zonas, y
    sobre esa lista mandan el buscador y los filtros de arriba. Así no hay
    dos tablas contando lo mismo, y cada fila lleva su ubicación, su
    técnico, sus abiertos, sus tickets y su avance.
    """
    usuario = request.user
    q = (request.GET.get("q") or "")[:120].strip()
    rol = (request.GET.get("rol") or "").strip()
    punto = (request.GET.get("punto") or "").strip()
    estado = (request.GET.get("estado") or "").strip()
    orden = (request.GET.get("orden") or "nombre").strip()

    resumen = _resumen_por_correo(usuario)
    # La tabla es única: la lista completa manda y encima mandan los filtros.
    todos_usuarios, zonas_obs = _tabla_todos_usuarios(usuario, resumen)
    total_sin_filtro = len(todos_usuarios)
    filas = list(todos_usuarios)

    if rol:
        filas = [f for f in filas if f["rol_crudo"] == rol]
    if q:
        buscar = q.lower()
        filas = [
            f for f in filas
            if buscar in f["nombre"].lower()
            or buscar in f["email"].lower()
            or buscar in f["ubicacion"].lower()
        ]
    if punto:
        busco = punto.strip().lower()
        filas = [
            f for f in filas
            if busco in {
                ((f["zona"].nombre if f["zona"] else "") or "").strip().lower(),
                (f["ubicacion"] or "").strip().lower(),
                *((p or "").strip().lower() for p in (f["puntos"] or [])),
            }
        ]
    if estado == "activos":
        filas = [f for f in filas if f["abiertos"] > 0]
    elif estado == "alerta":
        filas = [f for f in filas if f["urgentes"] > 0]
    elif estado == "agregados":
        filas = [f for f in filas if f["ya_agregado"]]
    elif estado == "pendientes":
        filas = [f for f in filas if not f["ya_agregado"]]
    elif estado == "con_tickets":
        filas = [f for f in filas if f["total"] > 0]
    elif estado == "resueltos":
        filas = [f for f in filas if f["total"] > 0 and f["avance"] == 100]

    if orden == "abiertos":
        filas.sort(key=lambda f: (-f["abiertos"], f["nombre"].lower()))
    elif orden == "tickets":
        filas.sort(key=lambda f: (-f["total"], f["nombre"].lower()))
    elif orden == "avance":
        filas.sort(key=lambda f: (f["avance"], -f["total"]))
    else:
        filas.sort(key=lambda f: f["nombre"].lower())

    conteo = {ESTADO_VERDE: 0, ESTADO_ROJO: 0, ESTADO_AMARILLO: 0}
    for f in filas:
        conteo[f["estado"]] += 1

    total_tickets = sum(f["total"] for f in filas)
    cerrados = sum(f["cerrados_total"] for f in filas)

    # La zona recién creada (si venimos de crearla): Usuarios se abre con la
    # ventana que propone meterle puntos de venta.
    recien_creada = None
    clave_nueva = (request.GET.get("zona_nueva") or "").strip()
    if clave_nueva.isdigit():
        recien_creada = ZonaObservador.objects.filter(
            pk=clave_nueva, observador=usuario
        ).first()

    return render(
        request,
        "observador/usuarios.html",
        {
            "filas": filas,
            "conteo": conteo,
            "total": len(filas),
            "total_sin_filtro": total_sin_filtro,
            "total_tickets": total_tickets,
            "total_abiertos": sum(f["abiertos"] for f in filas),
            "avance_global": (
                int(round(100.0 * cerrados / total_tickets)) if total_tickets else 0
            ),
            "en_lista": sum(1 for f in filas if f["ya_agregado"]),
            "q": q,
            "rol_sel": rol,
            "punto_sel": punto,
            "estado_sel": estado,
            "orden_sel": orden if orden in ("nombre", "abiertos", "tickets", "avance") else "nombre",
            "todos_usuarios": todos_usuarios,
            "zonas_obs": zonas_obs,
            "zona_nueva": recien_creada,
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
    # Sin puntos asignados el filtro por puntos devolvería vacío y las
    # tarjetas salían en ceros y el avance en 0% aunque la gente de la zona
    # tuviera tickets: en ese caso se ve todo, como en el resto del módulo.
    # Con puntos asignados el filtro manda, para no arrastrar tickets de
    # zonas ajenas en las vistas generales. Mi lista es la excepción: cada
    # cuenta fue agregada explícitamente por el observador y sus cifras deben
    # reflejar todos sus tickets, igual que el panel de administración.
    filas = _filas_de_mi_lista(
        usuario, elementos, global_scope=True)
    # Las respuestas visibles del personal viajan en cada fila para que la
    # ficha de la derecha las muestre, igual que en Monitoreo.
    respuestas = _respuestas_por_correo(
        puntos_del_observador(usuario),
        [f["email"] for f in filas if f["email"]], limite=3,
        global_scope=True,
    )
    for f in filas:
        f["respuestas"] = respuestas.get((f["email"] or "").strip().lower(), [])
    conteo = {ESTADO_VERDE: 0, ESTADO_ROJO: 0, ESTADO_AMARILLO: 0}
    for f in filas:
        conteo[f["estado"]] += 1
    return render(
        request,
        "observador/mi_lista.html",
        {
            "filas": filas,
            "conteo": conteo,
            "total": len(filas),
            "panel": _panel_de_supervision(usuario, filas),
            # El botón de Excel solo aparece si alguna de sus zonas tiene la
            # casilla «Exportar auditoría» marcada: el permiso lo pone la
            # zona al crearse, no la persona.
            "puede_exportar_auditoria": ZonaObservador.objects.filter(
                observador=usuario, perm_exportar=True
            ).exists(),
            # Historial igual que el del administrador: todos los registros,
            # con sus contadores de hoy y de la semana.
            "auditoria": _auditoria_enriquecida(),
            "aud_hoy": MonitoreoAuditoria.objects.filter(
                fecha__date=timezone.localdate()).count(),
            "aud_semana": MonitoreoAuditoria.objects.filter(
                fecha__gte=timezone.now() - timedelta(days=7)).count(),
        },
    )


def _filas_de_mi_lista(usuario, elementos, global_scope=False):
    """Une cada elemento de la lista con el estado de sus tickets.

    Con global_scope=True se muestran los datos reales de cada cuenta
    (todos sus tickets y técnicos), aunque caigan fuera de los puntos
    asignados: es gente que el observador (o el admin) puso en su lista
    para seguirla.
    """
    puntos = puntos_del_observador(usuario)
    if global_scope:
        visibles = Ticket.objects.all()
    else:
        visibles = _visible_a_observador(usuario, Ticket.objects.all())
    ahora = timezone.now()
    resumen = _resumen_por_correo(usuario, global_scope=global_scope)
    filas = []
    for e in elementos:
        correo = (e.usuario_email or "").strip().lower()
        consulta = visibles
        if correo:
            consulta = visibles.filter(
                Q(solicitante_email__iexact=correo)
                | Q(solicitante_nombre__iexact=e.usuario.nombre if e.usuario_id else "")
            )
        elif e.punto_id:
            consulta = visibles.filter(solicitante_punto=e.punto.nombre)
        tickets = list(
            consulta.select_related(
                "tecnico_asignado", "categoria"
            ).order_by("-fecha_creacion")[:60]
        )
        estado = ESTADO_VERDE
        orden = {ESTADO_VERDE: 0, ESTADO_AMARILLO: 1, ESTADO_ROJO: 2}
        for t in tickets:
            est = _estado_de(t, ahora)
            if orden[est] > orden[estado]:
                estado = est
        r = resumen.get(correo, {})
        filas.append(
            {
                "elemento": e,
                "nombre": (
                    e.usuario.nombre
                    if e.usuario_id
                    else (e.usuario_email or (e.punto.nombre if e.punto_id else "—"))
                ),
                "email": e.usuario_email or "",
                "detalle": (
                    (e.punto.nombre if e.punto_id else "")
                    + (" · " if e.punto_id and e.usuario_id else "")
                    + (e.usuario.nombre if e.usuario_id else "")
                ).strip(" ·"),
                "tickets": tickets,
                "abiertos": r.get(
                    "abiertos", sum(1 for t in tickets if t.estado in _ACTIVOS)
                ),
                "total": r.get("total", len(tickets)),
                "estado": estado,
                "tecnico": r.get("tecnico_principal", ""),
                "tecnicos": r.get("tecnicos", []),
                "resueltos": r.get(
                    "resueltos",
                    sum(1 for t in tickets if t.estado == Ticket.Estado.RESUELTO),
                ),
                "cerrados": r.get(
                    "cerrados",
                    sum(1 for t in tickets if t.estado == Ticket.Estado.CERRADO),
                ),
                "cerrados_total": r.get(
                    "cerrados_total",
                    sum(
                        1 for t in tickets
                        if t.estado in (Ticket.Estado.RESUELTO, Ticket.Estado.CERRADO)
                    ),
                ),
                "avance": r.get("avance", 0),
                "falta": 100 - r.get("avance", 0),
                "es_punto": bool(e.punto_id and not e.usuario_id),
                "telefono": e.usuario.telefono if e.usuario_id else "",
                "avatar": e.usuario.avatar if e.usuario_id else None,
                "ans_tickets": [],
            }
        )
    # Tickets de esas mismas cuentas que caen fuera de los puntos asignados:
    # explican los ceros (el dato existe, pero no es de sus zonas). Una sola
    # consulta para todas las filas.
    correos = [f["email"].strip().lower() for f in filas if (f["email"] or "").strip()]
    fuera = {}
    if correos:
        consulta_fuera = Ticket.objects.annotate(
            correo_normalizado=Lower("solicitante_email")
        ).filter(correo_normalizado__in=correos)
        if puntos:
            consulta_fuera = consulta_fuera.exclude(solicitante_punto__in=puntos)
        for fila in consulta_fuera.values("solicitante_email").annotate(
            n=Count("pk")
        ):
            fuera[(fila["solicitante_email"] or "").strip().lower()] = fila["n"]
    for f in filas:
        f["fuera_puntos"] = 0 if global_scope else fuera.get(
            (f["email"] or "").strip().lower(), 0
        )
        correo = (f["email"] or "").strip().lower()
        f["urgentes"] = resumen.get(correo, {}).get("urgentes", 0)
        f["ans_vencidos"] = 0
        f["ans_por_vencer"] = 0

    correos_con_zona = {
        (f["email"] or "").strip().lower()
        for f in filas if (f["email"] or "").strip()
    }
    filas_por_correo = {
        (f["email"] or "").strip().lower(): f
        for f in filas if (f["email"] or "").strip()
    }
    filas_por_punto = {
        f["elemento"].punto.nombre: f
        for f in filas
        if f.get("elemento") is not None and f["elemento"].punto_id
    }
    puntos_con_zona = set(filas_por_punto)
    if correos_con_zona or puntos_con_zona:
        filtro_ans = Q()
        if correos_con_zona:
            filtro_ans |= Q(correo_normalizado__in=correos_con_zona)
        if puntos_con_zona:
            filtro_ans |= Q(solicitante_punto__in=puntos_con_zona)
        consulta_ans = visibles.annotate(
            correo_normalizado=Lower("solicitante_email")
        ).filter(filtro_ans)
        for ticket in ans_avisos.por_vencer(
            consulta=consulta_ans,
            limite=max(consulta_ans.count(), 1),
            solo_sin_avisar=False,
        ):
            correo = (ticket.solicitante_email or "").strip().lower()
            fila = filas_por_correo.get(correo) or filas_por_punto.get(
                ticket.solicitante_punto or ""
            )
            if fila is not None:
                clave = "ans_vencidos" if ticket.ans_estado == "vencido" else "ans_por_vencer"
                fila[clave] += 1
                fila["ans_tickets"].append(ticket)
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
def quitar_varios_mi_lista(request):
    """Saca de la lista personal todas las cuentas marcadas en el panel.

    El panel de la derecha deja marcar con la casilla de cada fila y aquí
    se bajan de golpe. Solo puede tocar las suyas: el filtro
    `observador=request.user` es lo que impide que, manipulando la
    petición, se quiten filas de la lista de otro supervisor.
    """
    from django.contrib import messages

    if request.method != "POST":
        raise Http404
    ids = []
    for valor in request.POST.getlist("elementos"):
        try:
            ids.append(int(valor))
        except (TypeError, ValueError):
            continue
    quitados = 0
    if ids:
        quitados = ElementoMiLista.objects.filter(
            pk__in=ids, observador=request.user
        ).delete()[0]

    if quitados == 1:
        messages.success(request, "Se quitó 1 cuenta de tu lista.")
    elif quitados:
        messages.success(request, f"Se quitaron {quitados} cuentas de tu lista.")
    else:
        messages.warning(request, "No había ninguna cuenta tuya entre las marcadas.")
    return redirect(request.POST.get("volver") or reverse("tickets:obs_mi_lista"))


@solo_observador
def monitorear_observador(request):
    """Monitoreo: la lista con sus indicadores y las acciones de reporte.

    Agrupa a las personas por zona (con su supervisor, sus cuentas, sus
    tickets y las últimas respuestas de los técnicos) para que la vista
    muestre el detalle completo y no solo una tabla plana.
    """
    usuario = request.user
    contexto = _contexto_monitoreo(usuario)
    return render(request, "observador/monitoreo.html", contexto)


def _actividad_reciente(filas, limite=20):
    """Lo último que pasó en la lista: tickets nuevos y respuestas.

    Junta los tickets recientes de todos los miembros y las últimas
    respuestas de los técnicos, ordenados por fecha.
    """
    vistos = {}
    for f in filas:
        for t in f.get("tickets", []):
            if t.pk not in vistos:
                vistos[t.pk] = t
    recientes = sorted(
        vistos.values(), key=lambda t: t.fecha_creacion, reverse=True
    )[:limite]
    frescos = {
        t.pk: t
        for t in Ticket.objects.filter(
            pk__in=[t.pk for t in recientes]
        ).select_related("tecnico_asignado")
    }
    tickets = [frescos[t.pk] for t in recientes if t.pk in frescos]
    respuestas = sorted(
        (r for f in filas for r in f.get("respuestas", [])),
        key=lambda r: r.fecha,
        reverse=True,
    )[:5]
    return {"tickets": tickets, "respuestas": respuestas}


def _tecnicos_para_presionar(filas):
    """Técnicos con carga abierta, en orden de prioridad.

    Primero los que tienen urgentes abiertos, luego por abiertos. Cada uno
    trae sus tickets para presionarlos ticket por ticket.
    """
    por_tec = {}
    for f in filas:
        for t in f.get("tickets", []):
            if t.estado not in _ACTIVOS or not t.tecnico_asignado_id:
                continue
            tec = t.tecnico_asignado
            entrada = por_tec.setdefault(
                tec.pk, {"tecnico": tec, "tickets": [], "urgentes": 0}
            )
            if t.pk not in {x.pk for x in entrada["tickets"]}:
                entrada["tickets"].append(t)
                if t.prioridad == _URGENTE:
                    entrada["urgentes"] += 1
    for entrada in por_tec.values():
        entrada["tickets"].sort(
            key=lambda t: (
                t.prioridad != _URGENTE,
                t.fecha_creacion,
            )
        )
    return sorted(
        por_tec.values(),
        key=lambda e: (
            -e["urgentes"], -len(e["tickets"]), e["tecnico"].nombre or ""
        ),
    )


def _tabla_todos_usuarios(usuario, resumen):
    """Todas las cuentas del aplicativo, con acciones para este rol.

    Es la única tabla de Usuarios: junta las cuentas registradas con la
    gente que no tiene cuenta pero sí levantó tickets en las zonas del
    observador o ya está en su lista, para que nadie se pierda.

    Cada fila lleva su ubicación (la de la cuenta o, si la cuenta no la
    tiene, el punto del ticket), su técnico, sus abiertos, su total y su
    avance. Quien ya está en la lista del observador se le muestran sus
    datos reales —todos sus tickets, aunque caigan fuera de los puntos
    asignados— igual que en Mi lista: es gente que él puso ahí para
    seguirla. El resto se queda con lo que hay en sus puntos.
    """
    elementos = {
        (e.usuario_email or "").strip().lower(): e
        for e in ElementoMiLista.objects.filter(observador=usuario).select_related(
            "zona"
        )
    }
    zonas = list(
        ZonaObservador.objects.filter(observador=usuario).order_by("nombre")
    )
    cuentas = list(
        Usuario.objects.filter(activo=True, is_active=True).order_by("nombre")
    )
    # Los que siguen al observador tienen sus datos reales, como en Mi lista.
    resumen_lista = (
        _resumen_por_correo(
            usuario, global_scope=True, correos=list(elementos)
        )
        if elementos
        else {}
    )

    def fila_de(correo, u, e):
        r = (resumen_lista.get(correo) if e is not None else None) or resumen.get(
            correo, {}
        )
        puntos_de = r.get("puntos", [])
        return {
            "nombre": (u.nombre if u else "") or r.get("nombre") or correo,
            "email": correo,
            "obj": u,
            "rol": u.get_rol_display() if u else "Sin cuenta",
            "rol_crudo": u.rol if u else "",
            # La ubicación de la cuenta, y si no la tiene, la del ticket.
            "ubicacion": (
                (u.ubicacion if u else "")
                or (puntos_de[0] if puntos_de else "")
                or "—"
            ),
            "puntos": puntos_de,
            "en_lista": e is not None,
            "ya_agregado": e is not None,
            "elemento": e,
            "elemento_id": e.pk if e else None,
            "zona": e.zona if e else None,
            "total": r.get("total", 0),
            "abiertos": r.get("abiertos", 0),
            "urgentes": r.get("urgentes", 0),
            "cerrados_total": r.get("cerrados_total", 0),
            "avance": r.get("avance", 0),
            "falta": 100 - r.get("avance", 0),
            "estado": r.get("estado", ESTADO_VERDE),
            "tecnico": r.get("tecnico_principal", ""),
            "tecnicos": r.get("tecnicos", []),
        }

    filas = []
    for u in cuentas:
        correo = (u.email or "").strip().lower()
        filas.append(fila_de(correo, u, elementos.get(correo) if correo else None))
    # Sin cuenta registrada: los que tienen tickets en mis zonas o están en
    # mi lista. Antes solo salían en la otra tabla, que ya no existe.
    correos_cuenta = {
        (u.email or "").strip().lower() for u in cuentas if (u.email or "").strip()
    }
    extra = set(resumen) | {
        c for c in elementos if c not in correos_cuenta
    }
    for correo in sorted(extra - correos_cuenta):
        filas.append(fila_de(correo, None, elementos.get(correo)))
    return filas, zonas


def _contexto_monitoreo(usuario):
    """Filas, grupos por zona y totales de la lista del observador.

    Lo comparten el Monitoreo y el Panel: el panel es el monitoreo, con
    el detalle completo de usuarios, tickets y técnicos por zona.
    """
    elementos = (
        ElementoMiLista.objects.filter(observador=usuario)
        .select_related("usuario", "punto", "zona")
        .order_by("-creado_en")
    )
    filas = _filas_de_mi_lista(usuario, elementos, global_scope=True)
    conteo = {ESTADO_VERDE: 0, ESTADO_ROJO: 0, ESTADO_AMARILLO: 0}
    for f in filas:
        conteo[f["estado"]] += 1
    puntos = puntos_del_observador(usuario)
    respuestas = _respuestas_por_correo(
        puntos, [f["email"] for f in filas if f["email"]], limite=10,
        global_scope=True,
    )
    for f in filas:
        f["respuestas"] = respuestas.get((f["email"] or "").strip().lower(), [])
    total_tickets = sum(f["total"] for f in filas)
    resumen = _resumen_por_correo(usuario)
    todos_usuarios, zonas_obs = _tabla_todos_usuarios(usuario, resumen)
    # Las zonas se siembran aunque estén vacías: una recién creada tiene que
    # verse en el monitoreo desde el principio, no cuando alguien entre.
    grupos = _grupos_por_zona(filas, zonas_obs)
    top_tecnicos = {}
    for f in filas:
        for t in f.get("tecnicos", []):
            top_tecnicos[t["nombre"]] = top_tecnicos.get(t["nombre"], 0) + t["tickets"]
    top_tecnicos = sorted(
        top_tecnicos.items(), key=lambda kv: (-kv[1], kv[0])
    )[:6]
    base = len(filas) or 1
    pct_v = round(100.0 * conteo[ESTADO_VERDE] / base, 1)
    pct_a = round(100.0 * conteo[ESTADO_AMARILLO] / base, 1)
    pct_r = round(100.0 * conteo[ESTADO_ROJO] / base, 1)
    dona = [
        {"color": "#2F7D4F", "pct": pct_v, "offset": 25.0},
        {"color": "#D9A436", "pct": pct_a, "offset": 25.0 - pct_v},
        {"color": "#D62B1F", "pct": pct_r, "offset": 25.0 - pct_v - pct_a},
    ]
    # ANS: lo que se le está yendo del plazo. El panel manda los avisos que
    # falten aunque nadie haya programado el cron —una sola vez por ticket,
    # la marca del ticket lo evita— y encima enseña el listado entero: lo ya
    # avisado no desaparece, porque sigue sin resolverse.
    consulta_ans = ans_avisos.tickets_del_observador(usuario, alertas=True)
    try:
        ans_avisos.revisar_y_avisar(consulta=consulta_ans)
    except Exception:  # noqa: BLE001 - un correo malo no puede tumbar el panel
        logger.exception("No se pudieron mandar los avisos de ANS")
    listado_ans = ans_avisos.por_vencer(
        consulta=consulta_ans, solo_sin_avisar=False
    )
    # El mismo tablero del administrador, acotado a lo que este observador
    # ve: mismas gráficas y mismos tipos de gráfico al acercar el ratón,
    # sin salirse de sus puntos asignados.
    from .views import (  # noqa: PLC0415 - import tardío a propósito
        _ALCANCES_20_DIAS,
        _ALCANCES_TORTAS,
        _build_tecnico_dashboard,
    )

    try:
        dash_json = _build_tecnico_dashboard(
            consulta=_visible_a_observador(usuario, Ticket.objects.all())
        )
    except Exception:  # noqa: BLE001 - una gráfica no tumbará el tablero
        logger.exception("No se pudo armar el tablero del observador")
        dash_json = "{}"
    return {
        "filas": filas,
        "conteo": conteo,
        "total": len(filas),
        "grupos": grupos,
        "total_zonas": sum(1 for g in grupos if g["zona"] is not None),
        "total_tickets": total_tickets,
        "total_abiertos": sum(f["abiertos"] for f in filas),
        "avance_global": (
            int(round(100.0 * sum(f["cerrados_total"] for f in filas) / total_tickets))
            if total_tickets else 0
        ),
        "top_tecnicos": top_tecnicos,
        "dona": dona,
        "todos_usuarios": todos_usuarios,
        "zonas_obs": zonas_obs,
        "actividad": _actividad_reciente(filas),
        "presionar": _tecnicos_para_presionar(filas),
        "max_zona_tickets": max(
            [g["total_tickets"] for g in grupos] + [0]
        ),
        "max_tec_tickets": max([n for _, n in top_tecnicos] + [0]),
        # Sección de ANS del Monitoreo.
        "por_vencer": listado_ans,
        "total_por_vencer": sum(
            1 for t in listado_ans if t.ans_estado == "por-vencer"
        ),
        "total_vencidos": sum(
            1 for t in listado_ans if t.ans_estado == "vencido"
        ),
        # Las etiquetas de ANS abren la ventana explicativa: las dos vistas
        # que usan este contexto la incluyen.
        "ans_modal": True,
        # Widgets del tablero del administrador (pivote y gráficos con su
        # selector de tipo), acotados a la mirada del observador.
        "dash_json": dash_json,
        "alcances_tortas": _ALCANCES_TORTAS,
        "alcances_20dias": _ALCANCES_20_DIAS,
    }


def _grupos_por_zona(filas, zonas=()):
    """Agrupa las filas por zona, con sus totales y su estado global.

    Las zonas del supervisor se siembran aunque aún no tengan a nadie: una
    zona recién creada tiene que verse en el monitoreo desde el principio,
    igual que en el tablero del administrador.

    Las cuentas que todavía no están en ninguna zona van en un grupo
    «Sin zona» al final. Sin ese grupo el indicador de Cuentas —que cuenta
    toda la lista— no cuadraba con la suma de la tabla ni con las
    tarjetas: alguien sin carpeta no aparecía en ninguna parte.
    """
    grupos = []
    por_zona = {}
    sin_zona = {"zona": None, "filas": []}
    for z in zonas:
        if z is not None and z.pk is not None:
            por_zona[z.pk] = {"zona": z, "filas": []}
    for f in filas:
        zona = (f["elemento"].zona if f["elemento"] else None)
        if zona is None:
            sin_zona["filas"].append(f)
            continue
        clave = zona.pk
        if clave not in por_zona:
            por_zona[clave] = {"zona": zona, "filas": []}
        por_zona[clave]["filas"].append(f)
    orden = {ESTADO_VERDE: 0, ESTADO_AMARILLO: 1, ESTADO_ROJO: 2}

    def _de_totales(grupo):
        grupo["abiertos"] = sum(f["abiertos"] for f in grupo["filas"])
        grupo["total_tickets"] = sum(f["total"] for f in grupo["filas"])
        grupo["cerrados"] = sum(f["cerrados_total"] for f in grupo["filas"])
        grupo["avance"] = (
            int(round(100.0 * grupo["cerrados"] / grupo["total_tickets"]))
            if grupo["total_tickets"] else 0
        )
        grupo["estado"] = ESTADO_VERDE
        for f in grupo["filas"]:
            if orden[f["estado"]] > orden[grupo["estado"]]:
                grupo["estado"] = f["estado"]

    for clave in sorted(por_zona):
        grupo = por_zona[clave]
        _de_totales(grupo)
        grupos.append(grupo)
    if sin_zona["filas"]:
        _de_totales(sin_zona)
        grupos.append(sin_zona)
    return grupos


def _panel_de_supervision(usuario, filas):
    """Tarjetas del panel de dos columnas de Mi lista: solo las zonas
    creadas por el observador, cada una con sus cuentas, su estado y su
    avance.

    Es el mismo armazón que usa el administrador en su panel de zonas: a la
    izquierda el supervisor con lo que tiene a cargo y, al elegir una tarjeta,
    a la derecha las cuentas de esa zona. Los datos viajan en JSON para que
    el buscador de la derecha funcione sin volver al servidor.

    Ni los puntos asignados ni el grupo «Sin zona» hacen tarjeta: las
    cuentas que no están en una zona no entran en el panel.
    """
    orden_estado = {ESTADO_VERDE: 0, ESTADO_AMARILLO: 1, ESTADO_ROJO: 2}
    estados_activos = (Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO)

    def _detalle_ticket(t):
        ans_estado, ans_texto = (
            t.datos_ans[:2] if t.estado in estados_activos else ("", "")
        )
        return {
            "pk": t.pk,
            "codigo": t.codigo,
            "titulo": t.titulo,
            "estado": t.estado,
            "estado_display": t.get_estado_display(),
            "fecha": (
                t.fecha_creacion.strftime("%d/%m/%Y %H:%M")
                if t.fecha_creacion else ""
            ),
            "tecnico": (
                t.tecnico_asignado.nombre if t.tecnico_asignado else ""
            ),
            "ans_estado": ans_estado,
            "ans_texto": ans_texto,
        }

    def _tarjeta(clave, nombre, fecha="", pk=None, color=""):
        return {
            "clave": clave,
            "pk": pk,
            "nombre": nombre,
            "fecha": fecha,
            "color": color,
            "usuarios": [],
            "cuentas": 0,
            "total": 0,
            "abiertos": 0,
            "cerrados": 0,
            "avance": 0,
            "estado": ESTADO_VERDE,
        }

    zonas = []
    por_clave = {}

    def _mete(tarjeta):
        if tarjeta["clave"] in por_clave:
            return por_clave[tarjeta["clave"]]
        zonas.append(tarjeta)
        por_clave[tarjeta["clave"]] = tarjeta
        return tarjeta

    for z in (
        ZonaObservador.objects.filter(observador=usuario)
        .order_by("-creado_en", "-pk")
        .values("pk", "nombre", "creado_en", "color")
    ):
        _mete(_tarjeta(
            f"z{z['pk']}",
            (z["nombre"] or "").strip(),
            z["creado_en"].strftime("%d/%m/%Y") if z.get("creado_en") else "",
            pk=z["pk"],
            color=z["color"] or "",
        ))
    for f in filas:
        elemento = f.get("elemento")
        zona = getattr(elemento, "zona", None) if elemento is not None else None
        if zona is None or not (zona.nombre or "").strip():
            # Sin zona propia no hay tarjeta: el panel ya no agrupa por punto
            # ni tiene grupo «Sin zona». Esas cuentas siguen saliendo en
            # Usuarios y en el resto de tablas de siempre.
            continue
        tarjeta = _mete(_tarjeta(
            f"z{zona.pk}", zona.nombre.strip(),
            zona.creado_en.strftime("%d/%m/%Y") if zona.creado_en else "",
            pk=zona.pk,
            color=zona.color or "",
        ))
        correo = (f.get("email") or "").strip().lower()
        tickets_panel = {
            t.pk: t for t in (
                (f.get("tickets") or []) + (f.get("ans_tickets") or [])
            )
        }
        tickets_recientes = list((f.get("tickets") or [])[:10])
        vistos_recientes = {t.pk for t in tickets_recientes}
        tickets_recientes.extend(
            t for t in (f.get("ans_tickets") or [])
            if t.pk not in vistos_recientes
        )
        tickets_presionables = [
            _detalle_ticket(t)
            for t in tickets_panel.values()
            if t.tecnico_asignado_id and t.estado in estados_activos
        ]
        orden_ans = {"vencido": 0, "por-vencer": 1}
        tickets_presionables.sort(
            key=lambda t: (orden_ans.get(t["ans_estado"], 2), t["codigo"])
        )
        tarjeta["usuarios"].append({
            "nombre": f.get("nombre") or correo or "—",
            "email": correo,
            "rol": f.get("rol")
                   or ("Punto de venta" if f.get("es_punto") else "Cuenta"),
            "estado": f.get("estado") or ESTADO_VERDE,
            "total": f.get("total", 0),
            "abiertos": f.get("abiertos", 0),
            "resueltos": f.get("resueltos", 0),
            "cerrados": f.get("cerrados", 0),
            "cerrados_total": f.get("cerrados_total", 0),
            "avance": f.get("avance", 0),
            "falta": f.get("falta", 100 - f.get("avance", 0)),
            "urgentes": f.get("urgentes", 0),
            "ans_vencidos": f.get("ans_vencidos", 0),
            "ans_por_vencer": f.get("ans_por_vencer", 0),
            "ans_estado": (
                "vencido" if f.get("ans_vencidos", 0)
                else "por-vencer" if f.get("ans_por_vencer", 0)
                else ""
            ),
            # La ficha de la cuenta, a la vista en el panel: los últimos
            # tickets con su color y las respuestas visibles del personal.
            # Sin esto la fila solo traía el contador y había que abrir la
            # ficha aparte para saber qué hay detrás.
            "tickets": [_detalle_ticket(t) for t in tickets_recientes],
            "tickets_presionables": tickets_presionables,
            "respuestas": [
                {
                    "autor": (
                        (r.usuario.nombre if r.usuario else "")
                        or r.autor_nombre or ""
                    ),
                    "codigo": r.ticket.codigo if r.ticket_id else "",
                    "fecha": r.fecha.strftime("%d/%m/%Y %H:%M") if r.fecha else "",
                    "texto": (r.comentario or "")[:180],
                }
                for r in (f.get("respuestas") or [])[:3]
            ],
            "en_lista": bool(f.get("elemento") or f.get("ya_agregado")),
            "elemento_id": getattr(elemento, "pk", None),
            "url_agregar": reverse("tickets:obs_agregar"),
            "url_quitar": (
                reverse("tickets:obs_quitar", args=[elemento.pk])
                if getattr(elemento, "pk", None) else ""
            ),
            "url": (
                reverse("tickets:obs_usuarios") + "?q=" + correo
                if correo else reverse("tickets:obs_usuarios")
            ),
        })

    for tarjeta in zonas:
        cuentas = tarjeta["usuarios"]
        tarjeta["cuentas"] = len(cuentas)
        tarjeta["total"] = sum(u["total"] for u in cuentas)
        tarjeta["abiertos"] = sum(u["abiertos"] for u in cuentas)
        tarjeta["cerrados"] = sum(u["cerrados_total"] for u in cuentas)
        tarjeta["resueltos"] = sum(u["resueltos"] for u in cuentas)
        tarjeta["urgentes"] = sum(u["urgentes"] for u in cuentas)
        tarjeta["ans_vencidos"] = sum(u["ans_vencidos"] for u in cuentas)
        tarjeta["ans_por_vencer"] = sum(u["ans_por_vencer"] for u in cuentas)
        tarjeta["avance"] = (
            int(round(100.0 * tarjeta["cerrados"] / tarjeta["total"]))
            if tarjeta["total"] else 0
        )
        tarjeta["estado"] = ESTADO_VERDE
        for u in cuentas:
            if orden_estado.get(u["estado"], 0) > orden_estado[tarjeta["estado"]]:
                tarjeta["estado"] = u["estado"]

    return {
        "supervisor": {
            "nombre": usuario.nombre or usuario.email,
            "email": usuario.email or "",
            "zonas": len(zonas),
        },
        "resumen": {
            "supervisores": int(bool(zonas)),
            "zonas": len(zonas),
            "cuentas": sum(z["cuentas"] for z in zonas),
            "abiertos": sum(z["abiertos"] for z in zonas),
        },
        "zonas": zonas,
    }


def _respuestas_por_correo(puntos, correos, limite=2, global_scope=False):
    """Últimas respuestas de los técnicos, por correo.

    Una sola consulta para todos los miembros: sin puntos asignados no se
    ve nada, igual que en el resto del módulo. Con global_scope=True trae
    las respuestas reales aunque sean de otros puntos (gente de la lista).
    Las de administradores no salen aquí: es el tablero del seguimiento
    con los técnicos.
    """
    correos = {(c or "").strip().lower() for c in correos if (c or "").strip()}
    if not correos or (not puntos and not global_scope):
        return {}
    consulta = TicketComentario.objects.filter(
        es_interno=False,
        usuario__rol=Usuario.Rol.TECNICO,
    )
    if not global_scope:
        consulta = consulta.filter(ticket__solicitante_punto__in=puntos)
    comentarios = (
        consulta.select_related("ticket", "usuario").order_by("-fecha")
    )
    por_correo = {}
    for c in comentarios:
        correo = (c.ticket.solicitante_email or "").strip().lower()
        if correo not in correos:
            continue
        lista = por_correo.setdefault(correo, [])
        if len(lista) < limite:
            lista.append(c)
    return por_correo


@solo_observador
def presionar_tecnico(request, pk):
    """El observador le escribe al técnico para que resuelva rápido.

    Guarda el mensaje en el hilo del ticket (visible, no interno) y le
    avisa al técnico por campana y correo. Solo tickets de sus puntos o
    de cuentas de su lista.
    """
    from django.contrib import messages

    from .notifications import notificar_comentario

    if request.method != "POST":
        raise Http404
    usuario = request.user
    volver = request.POST.get("volver") or reverse("tickets:obs_monitoreo")
    mensaje = (request.POST.get("mensaje") or "").strip()[:500]
    if not mensaje:
        messages.error(request, "Escribe el mensaje para el técnico.")
        return redirect(volver)
    try:
        ticket = Ticket.objects.select_related("tecnico_asignado").get(pk=pk)
    except (Ticket.DoesNotExist, ValueError, TypeError):
        raise Http404
    puntos = puntos_del_observador(usuario)
    en_lista = bool(
        ticket.solicitante_email
        and ElementoMiLista.objects.filter(
            observador=usuario, usuario_email__iexact=ticket.solicitante_email
        ).exists()
    )
    # También quien está en la lista por punto: esos tickets no llevan correo,
    # así que la comprobación por correo solo no los alcanzaba.
    en_punto_de_lista = bool(
        ticket.solicitante_punto
        and ElementoMiLista.objects.filter(
            observador=usuario, punto__nombre=ticket.solicitante_punto
        ).exists()
    )
    if (
        (ticket.solicitante_punto or "") not in puntos
        and not en_lista
        and not en_punto_de_lista
    ):
        raise Http404
    TicketComentario.objects.create(
        ticket=ticket,
        usuario=usuario,
        autor_nombre=usuario.nombre,
        comentario=mensaje,
        es_interno=False,
        es_presion=True,
    )
    notificar_comentario(ticket, usuario.nombre, mensaje, actor=usuario)
    messages.success(request, f"Mensaje enviado al técnico del {ticket.codigo}.")
    return redirect(volver)


@solo_observador
def exportar_observador(request):
    """Descarga la lista del observador como CSV, para el reporte."""
    usuario = request.user
    # Mismo alcance que la pantalla de Mi lista: el CSV lleva los mismos
    # números que el supervisor ve, ni uno de más ni uno de menos.
    filas = _filas_de_mi_lista(
        usuario,
        ElementoMiLista.objects.filter(observador=usuario).select_related(
            "usuario", "punto"
        ),
        global_scope=not puntos_del_observador(usuario),
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


# ------------------------------------------------------------------- zonas
@solo_observador
def zona_crear_observador(request):
    """Crea una zona propia del observador desde el panel de Usuarios.

    Misma mecánica que la del administrador: ventana emergente con las
    notificaciones de la zona, validación de nombre repetido y aviso por
    toast al crear o al fallar. Vuelve a la vista que lo abrió.
    """
    from django.contrib import messages

    if request.method != "POST":
        return redirect("tickets:obs_usuarios")
    usuario = request.user
    volver = request.POST.get("volver") or reverse("tickets:obs_usuarios")
    nombre = (request.POST.get("nombre") or "").strip()[:80]
    if not nombre:
        messages.error(request, "Ponle un nombre a la zona para crearla.")
        return redirect(volver)
    if ZonaObservador.objects.filter(
        observador=usuario, nombre__iexact=nombre
    ).exists():
        messages.error(request, f"Ya tienes una zona llamada «{nombre}».")
        return redirect(volver)
    zona = ZonaObservador.objects.create(
        observador=usuario,
        nombre=nombre,
        version_sistema=(_version_equipo(request) or "")[:30],
        # La casilla viene marcada por defecto: si no está en el POST, apagó.
        notif_correo=request.POST.get("notif_correo") == "on",
        notif_popup=request.POST.get("notif_popup") == "on",
        perm_exportar=request.POST.get("perm_exportar") == "on",
        perm_historial=request.POST.get("perm_historial") == "on",
        alertas_ans=request.POST.get("alertas_ans") == "on",
    )
    _auditar(usuario, MonitoreoAuditoria.CREAR_ZONA, usuario, nombre, "")
    _marca_equipo_supervisor(zona, request)
    messages.success(
        request, f"Zona «{zona.nombre}» creada. Ya puedes meterle cuentas."
    )
    # El siguiente paso es meterle puntos de venta: Usuarios se abre con la
    # ventana de la zona recién creada ya puesta.
    return redirect(f"{reverse('tickets:obs_usuarios')}?zona_nueva={zona.pk}")


@solo_observador
def zonas_observador(request):
    """Zonas propias del observador: carpetas con nombre para agrupar gente.

    Aquí se crean las zonas y se reparte entre ellas a las personas de Mi
    lista. Cada zona resume cuánta gente tiene y cuántos tickets abiertos
    suman, y lleva a su detalle para el seguimiento.
    """
    usuario = request.user
    error = ""
    if request.method == "POST":
        zona_id = (request.POST.get("zona_id") or "").strip()
        if zona_id:
            nuevo = (request.POST.get("nuevo_nombre") or "").strip()[:80]
            try:
                zona = ZonaObservador.objects.get(
                    pk=int(zona_id), observador=usuario
                )
            except (ZonaObservador.DoesNotExist, ValueError, TypeError):
                raise Http404
            if not nuevo:
                error = "El nombre nuevo no puede quedar vacío."
            elif ZonaObservador.objects.filter(
                observador=usuario, nombre__iexact=nuevo
            ).exclude(pk=zona.pk).exists():
                error = "Ya tienes una zona con ese nombre."
            else:
                anterior = zona.nombre
                zona.nombre = nuevo
                zona.save(update_fields=["nombre"])
                _auditar(
                    usuario, MonitoreoAuditoria.RENOMBRAR_ZONA, usuario,
                    nuevo, f"antes: {anterior}",
                )
                _marca_equipo_supervisor(zona, request)
                return redirect(
                    request.POST.get("volver") or reverse("tickets:obs_zonas")
                )
            nombre = ""
        else:
            nombre = (request.POST.get("nombre") or "").strip()[:80]
            if not nombre:
                error = "Ponle un nombre a la zona para crearla."
            elif ZonaObservador.objects.filter(
                observador=usuario, nombre__iexact=nombre
            ).exists():
                error = "Ya tienes una zona con ese nombre."
            else:
                zona = ZonaObservador.objects.create(observador=usuario, nombre=nombre)
                _auditar(
                    usuario, MonitoreoAuditoria.CREAR_ZONA, usuario, nombre, "",
                )
                _marca_equipo_supervisor(zona, request)
                return redirect("tickets:obs_zona_detalle", pk=zona.pk)
    resumen = _resumen_por_correo(usuario)
    zonas = list(
        ZonaObservador.objects.filter(observador=usuario).prefetch_related("elementos")
    )
    tarjetas = []
    for zona in zonas:
        miembros = [
            e for e in zona.elementos.all()
            if e.tipo == ElementoMiLista.TIPO_USUARIO
        ]
        abiertos = sum(
            resumen.get((e.usuario_email or "").strip().lower(), {}).get("abiertos", 0)
            for e in miembros
        )
        tarjetas.append({"zona": zona, "personas": len(miembros), "abiertos": abiertos})
    sin_zona = (
        ElementoMiLista.objects.filter(
            observador=usuario,
            zona__isnull=True,
            tipo=ElementoMiLista.TIPO_USUARIO,
        )
        .select_related("usuario")
        .order_by("usuario_email")
    )
    return render(
        request,
        "observador/zonas.html",
        {
            "tarjetas": tarjetas,
            "zonas": zonas,
            "sin_zona": sin_zona,
            "error": error,
        },
    )


@solo_observador
def zona_detalle_observador(request, pk):
    """Seguimiento por zona: su gente, sus tickets y las respuestas.

    Cada persona trae sus números (acotados a los puntos del observador,
    como en el resto del módulo) y las últimas respuestas que le dieron
    los técnicos a sus tickets.
    """
    usuario = request.user
    try:
        zona = ZonaObservador.objects.get(pk=pk, observador=usuario)
    except ZonaObservador.DoesNotExist:
        raise Http404
    filas, _ = _cuentas_y_tickets_de_zona(zona)
    # Resumen de la carpeta: lo primero que se ve de la zona.
    total_tickets = sum(f["total"] for f in filas)
    orden = {ESTADO_VERDE: 0, ESTADO_AMARILLO: 1, ESTADO_ROJO: 2}
    estado_zona = ESTADO_VERDE
    for f in filas:
        if orden[f["estado"]] > orden[estado_zona]:
            estado_zona = f["estado"]
    resumen = {
        "cuentas": len(filas),
        "total": total_tickets,
        "abiertos": sum(f["abiertos"] for f in filas),
        "resueltos": sum(f["cerrados_total"] for f in filas),
        "avance": (
            int(round(100.0 * sum(f["cerrados_total"] for f in filas) / total_tickets))
            if total_tickets else 0
        ),
        "estado": estado_zona,
    }
    resumen["falta"] = 100 - resumen["avance"]
    return render(
        request,
        "observador/zona_detalle.html",
        {"zona": zona, "filas": filas, "resumen": resumen},
    )


def _cuentas_y_tickets_de_zona(zona, limite_tickets=20, global_scope=None):
    """Cada cuenta de la zona con sus números y sus últimos tickets.

    Los tickets viajan en la fila porque las tarjetas de «Sus cuentas» los
    muestran uno a uno (el mismo chip que Monitoreo): sin ellos solo se ve
    el contador y no se sabe qué hay detrás. El alcance es el de siempre
    del módulo, acotado a los puntos del observador.

    Lo comparten la pantalla de la carpeta y su Excel: así lo que baja el
    fichero es exactamente lo que se ve en la página.
    """
    usuario = zona.observador
    # Sin puntos asignados el filtro devolvería vacío y la ficha salía en
    # ceros y sin tickets: en ese caso se ve todo, igual que en Mi lista. Con
    # puntos asignados el filtro manda, para no arrastrar tickets de zonas
    # ajenas.
    alcance_global = (
        not puntos_del_observador(usuario)
        if global_scope is None else global_scope
    )
    resumen = _resumen_por_correo(usuario, global_scope=alcance_global)
    visibles = (
        Ticket.objects.all() if alcance_global
        else _visible_a_observador(usuario, Ticket.objects.all())
    )
    miembros = (
        zona.elementos.filter(tipo=ElementoMiLista.TIPO_USUARIO)
        .select_related("usuario")
        .order_by("usuario_email")
    )
    filas = []
    for e in miembros:
        correo = (e.usuario_email or "").strip().lower()
        r = resumen.get(correo, {})
        propios = []
        if correo:
            consulta = (
                visibles.filter(solicitante_email__iexact=correo)
                .select_related("tecnico_asignado")
                .order_by("-fecha_creacion")
            )
            if limite_tickets:
                consulta = consulta[:limite_tickets]
            propios = list(consulta)
        filas.append(
            {
                "elemento": e,
                "nombre": (
                    (e.usuario.nombre if e.usuario else "") or correo
                ),
                "email": correo,
                "total": r.get("total", 0),
                "abiertos": r.get("abiertos", 0),
                "avance": r.get("avance", 0),
                "falta": 100 - r.get("avance", 0),
                "cerrados_total": r.get("cerrados_total", 0),
                "estado": r.get("estado", ESTADO_VERDE),
                "tickets": propios,
                "respuestas": _respuestas_de_tecnicos(correo, visibles),
            }
        )
    return filas, [t for f in filas for t in f["tickets"]]


def _respuestas_de_tecnicos(correo, visibles=None, limite=3):
    """Últimas respuestas del personal a los tickets de la persona.

    Solo respuestas visibles (no internas) de técnicos o administradores,
    sobre los mismos tickets que muestra la ficha: si el observador no tiene
    puntos asignados se ve todo, y si los tiene solo los de sus puntos.
    """
    if not correo:
        return []
    consulta = TicketComentario.objects.filter(
        ticket__solicitante_email__iexact=correo,
        es_interno=False,
        usuario__rol__in=[Usuario.Rol.TECNICO, Usuario.Rol.ADMIN],
    )
    if visibles is not None:
        consulta = consulta.filter(ticket__in=visibles)
    return list(
        consulta.select_related("ticket", "usuario").order_by("-fecha")[:limite]
    )


def _marca_equipo_supervisor(zona, request):
    """Guarda Windows e IP del supervisor cuando actúa en su zona."""
    if zona is None or getattr(zona, "pk", None) is None:
        return
    try:
        from apps.accounts.seguridad import ip_del_request
        ver = (_version_equipo(request) or "")[:30]
        ip = (ip_del_request(request) or "")[:45]
    except Exception:
        return
    cambios = {}
    if ver and zona.sup_version != ver:
        cambios["sup_version"] = ver
    if ip and zona.sup_ip != ip:
        cambios["sup_ip"] = ip
    if cambios:
        for k, v in cambios.items():
            setattr(zona, k, v)
        zona.save(update_fields=list(cambios))


@solo_observador
def zona_miembro_asignar(request):
    """Mete o saca un elemento de Mi lista en una zona (solo POST)."""
    if request.method != "POST":
        raise Http404
    usuario = request.user
    try:
        elemento = ElementoMiLista.objects.get(
            pk=request.POST.get("elemento"), observador=usuario
        )
    except (ElementoMiLista.DoesNotExist, ValueError, TypeError):
        raise Http404
    zona_id = (request.POST.get("zona") or "").strip()
    if zona_id:
        try:
            elemento.zona = ZonaObservador.objects.get(
                pk=int(zona_id), observador=usuario
            )
        except (ZonaObservador.DoesNotExist, ValueError, TypeError):
            raise Http404
        _auditar(
            usuario, MonitoreoAuditoria.AGREGAR_MIEMBRO, usuario,
            elemento.zona.nombre, (elemento.usuario_email or ""),
            cuenta=(elemento.usuario_email or ""),
            motivo=_motivo_post(request),
        )
        _marca_equipo_supervisor(elemento.zona, request)
    else:
        if elemento.zona_id:
            _auditar(
                usuario, MonitoreoAuditoria.QUITAR_MIEMBRO, usuario,
                (elemento.zona.nombre if elemento.zona else ""),
                (elemento.usuario_email or ""),
                cuenta=(elemento.usuario_email or ""),
                motivo=_motivo_post(request),
            )
            _marca_equipo_supervisor(elemento.zona, request)
        elemento.zona = None
    elemento.save(update_fields=["zona"])
    return redirect(request.POST.get("volver") or reverse("tickets:obs_zonas"))


@solo_observador
def zona_eliminar(request, pk):
    """Borra una zona propia: su gente queda sin zona, no se borra."""
    if request.method != "POST":
        raise Http404
    try:
        zona = ZonaObservador.objects.get(pk=pk, observador=request.user)
    except ZonaObservador.DoesNotExist:
        raise Http404
    _auditar(
        request.user, MonitoreoAuditoria.ELIMINAR_ZONA, request.user,
        zona.nombre, "",
    )
    zona.delete()
    return redirect(request.POST.get("volver") or reverse("tickets:obs_zonas"))


@solo_observador
def zona_color(request):
    """Pinta una carpeta con el color que se eligió en su paleta (solo POST).

    El color solo se admite si viene de la paleta cerrada de arriba: lo que
    llegue de otro lado no se guarda ni se refleja en el estilo.
    """
    if request.method != "POST":
        raise Http404
    try:
        zona = ZonaObservador.objects.get(
            pk=request.POST.get("zona_id"), observador=request.user
        )
    except (ZonaObservador.DoesNotExist, ValueError, TypeError):
        raise Http404
    color = (request.POST.get("color") or "").strip().upper()
    if color and color not in PALETA_ZONA:
        raise Http404
    zona.color = color
    zona.save(update_fields=["color"])
    return redirect(request.POST.get("volver") or reverse("tickets:obs_zonas"))


@solo_observador
@require_GET
def obs_auditoria_exportar(request):
    """Descarga en Excel la auditoría de las propias zonas.

    El permiso lo tiene la zona, no la persona: cada zona se creó con su
    casilla «Exportar auditoría» y solo las que la llevan marcada entran en
    el fichero. Si una zona la tiene quitada se queda fuera aunque el
    supervisor sea el mismo que pide la descarga, y si no queda ninguna
    con permiso no hay descarga.

    Las filas sin zona son las que dejó el propio observador fuera de una
    carpeta concreta (agregar o quitar cuentas de su lista): esas sí son
    suyas. Las de zonas ajenas no se cuelan.
    """
    from django.contrib import messages

    zonas = list(ZonaObservador.objects.filter(observador=request.user))
    permitidas = [(z.nombre or "").strip() for z in zonas if z.perm_exportar]
    bloqueadas = [
        (z.nombre or "").strip()
        for z in zonas
        if not z.perm_exportar and (z.nombre or "").strip()
    ]
    if not permitidas:
        messages.error(
            request,
            "Ninguna de tus zonas tiene permiso para exportar la auditoría.",
        )
        return redirect(reverse("tickets:obs_mi_lista"))

    consulta = MonitoreoAuditoria.objects.all()
    if bloqueadas:
        # El «no» de la zona manda sobre las filas suyas también: el permiso
        # se quitó en la carpeta, no en la persona.
        consulta = consulta.exclude(zona_nombre__in=bloqueadas)
    filas = (
        consulta.filter(
            Q(zona_nombre__in=permitidas)
            | Q(observador=request.user, zona_nombre="")
        )
        .select_related("actor", "observador")
        .order_by("-fecha", "-id")[:2000]
    )
    return _xlsx_auditoria(
        filas,
        titulo="Dogger · Auditoría de tus zonas",
        nombre="dogger_auditoria_tus_zonas",
    )


def _xlsx_zona(zona, filas, tickets, nombre="dogger_zona"):
    """Monta la descarga .xlsx de una carpeta: su resumen, sus cuentas y sus tickets.

    Dos hojas: «Zona» con el pulso arriba y una fila por cuenta, y «Tickets»
    con el detalle uno a uno. El formato es el mismo que el de la auditoría
    (encabezado negro, zebra y autofiltro) para que todas las descargas del
    módulo se vean de la misma familia.
    """
    from io import BytesIO

    from django.http import HttpResponse
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    NEGRO = PatternFill(start_color="171412", end_color="171412", fill_type="solid")
    BLANCO = Font(name="Arial", bold=True, color="FFFFFF", size=11)
    CUERPO = Font(name="Arial", size=10)
    fino = Side(style="thin", color="D9CFC2")
    borde = Border(left=fino, right=fino, top=fino, bottom=fino)
    zebra = PatternFill(start_color="FBF6EC", end_color="FBF6EC", fill_type="solid")

    wb = Workbook()
    wb.remove(wb.active)

    def _hoja(titulo, encabezados, cuerpo, nombre_hoja):
        ws = wb.create_sheet(nombre_hoja)
        ws.merge_cells(
            start_row=1, start_column=1, end_row=1, end_column=len(encabezados)
        )
        celda = ws.cell(row=1, column=1, value=titulo)
        celda.font = Font(name="Arial", bold=True, color="FFFFFF", size=14)
        celda.fill = NEGRO
        celda.alignment = Alignment(horizontal="center")
        for i, (texto, ancho) in enumerate(encabezados, start=1):
            celda = ws.cell(row=2, column=i, value=texto)
            celda.font = BLANCO
            celda.fill = NEGRO
            celda.border = borde
            celda.alignment = Alignment(
                horizontal="center", vertical="center", wrap_text=True
            )
            ws.column_dimensions[get_column_letter(i)].width = ancho
        ws.auto_filter.ref = f"A2:{get_column_letter(len(encabezados))}2"
        ws.freeze_panes = "A3"
        for n, valores in enumerate(cuerpo, start=3):
            for i, valor in enumerate(valores, start=1):
                celda = ws.cell(row=n, column=i, value=valor)
                celda.font = CUERPO
                celda.border = borde
                if n % 2:
                    celda.fill = zebra
        return ws

    _hoja(
        f"Dogger · Zona {zona.nombre}",
        [
            ("Cuenta", 30), ("Correo", 34), ("Tickets", 9),
            ("Abiertos", 10), ("Resueltos", 10), ("Avance", 9),
            ("Estado", 11),
        ],
        [
            [
                f["nombre"],
                f["email"],
                f["total"],
                f["abiertos"],
                f["cerrados_total"],
                f"{f['avance']}%",
                (f["estado"] or "").capitalize(),
            ]
            for f in filas
        ],
        "Zona",
    )
    _hoja(
        f"Dogger · Tickets de {zona.nombre}",
        [
            ("Código", 12), ("Cuenta", 30), ("Título", 52), ("Estado", 14),
            ("Técnico", 26), ("Creado", 18),
        ],
        [
            [
                t.codigo,
                (t.solicitante_nombre or t.solicitante_email or ""),
                (t.titulo or "")[:200],
                t.get_estado_display(),
                (t.tecnico_asignado.nombre or t.tecnico_asignado.email or "")
                if t.tecnico_asignado_id else "Sin asignar",
                timezone.localtime(t.fecha_creacion).strftime("%d/%m/%Y %H:%M")
                if t.fecha_creacion else "",
            ]
            for t in tickets
        ],
        "Tickets",
    )

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    respuesta = HttpResponse(
        buffer.getvalue(),
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )
    clave = "".join(c for c in (zona.nombre or "zona") if c.isalnum()) or "zona"
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}_{clave}.xlsx"'
    return respuesta


@solo_observador
def zona_excel_observador(request, pk):
    """Excel de la carpeta: su resumen, sus cuentas y sus tickets.

    Es lo mismo que se ve en la pantalla de la zona, bajado a una hoja de
    cálculo para llevarlo a la junta o adjuntarlo. El permiso «Exportar
    auditoría» no entra aquí: eso gobierna el historial de acciones, no los
    datos de la propia carpeta, que el observador ya tiene a la vista.
    """
    usuario = request.user
    try:
        zona = ZonaObservador.objects.get(pk=pk, observador=usuario)
    except ZonaObservador.DoesNotExist:
        raise Http404
    filas, tickets = _cuentas_y_tickets_de_zona(zona, limite_tickets=500)
    return _xlsx_zona(zona, filas, tickets)
