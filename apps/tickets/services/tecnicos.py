"""Datos de los técnicos activos para el panel de los usuarios.

Aquí se arma la lista que se muestra en el modal «Técnicos» de Mi panel:
quiénes hay, qué tan disponibles están y cómo los ha calificado la gente
con el pulgar arriba / abajo.
"""

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

# Hasta este número de tickets activos el técnico se considera disponible.
DISPONIBLE_HASTA = 3
# Minutos de actividad reciente para marcarlo como "en línea".
MINUTOS_EN_LINEA = 5

ESTADOS_ACTIVOS = ("abierto", "en-progreso")


def puede_calificar(usuario):
    """Quién tiene derecho a calificar técnicos.

    Los usuarios finales y los administradores califican; un técnico no se
    califica a sí mismo y el observador solo consulta.
    """
    if usuario is None or not usuario.is_authenticated or not usuario.activo:
        return False
    return usuario.rol in ("usuario", "admin")


def _etiqueta_disponibilidad(activos, en_linea):
    """Pequeño texto de disponibilidad para la tarjeta del técnico."""
    if activos == 0:
        return ("disponible", "Disponible ahora", "Sin tickets pendientes")
    if activos <= DISPONIBLE_HASTA:
        etiqueta = "Ocupado" if not en_linea else "Disponible"
        detalle = (
            f"{activos} ticket{'s' if activos > 1 else ''} en curso"
            if not en_linea
            else f"{activos} ticket{'s' if activos > 1 else ''} · conectado"
        )
        return ("ocupado" if not en_linea else "disponible", etiqueta, detalle)
    return (
        "saturado",
        "Muy ocupado",
        f"{activos} tickets en curso",
    )


def mapeados_del_tecnico(usuario_actual, ticket=None):
    """Técnicos activos con su disponibilidad, sus datos y sus calificaciones.

    Viene listo para el modal: cada elemento trae el estado de disponibilidad,
    los datos de contacto del técnico y los contadores de pulgares. El
    orden pone primero a los que están disponibles y después por nombre.

    Con `ticket` (el detalle de un ticket ya resuelto) cada técnico añade su
    voto en ese ticket y la barra de aprobación contada solo sobre tickets
    resueltos, que es lo que se está calificando.
    """
    from apps.accounts.models import Usuario
    from apps.tickets.models import CalificacionTecnico, Ticket

    qs = Usuario.objects.filter(rol=Usuario.Rol.TECNICO, activo=True, is_active=True)
    if usuario_actual.rol == Usuario.Rol.TECNICO:
        # Un técnico no aparece en su propia lista.
        qs = qs.exclude(pk=usuario_actual.pk)

    qs = qs.annotate(
        activos=Count(
            "tickets_asignados",
            filter=Q(tickets_asignados__estado__in=ESTADOS_ACTIVOS),
            distinct=True,
        ),
        resueltos=Count(
            "tickets_asignados",
            filter=Q(tickets_asignados__estado__in=[Ticket.Estado.RESUELTO, Ticket.Estado.CERRADO]),
            distinct=True,
        ),
        me_gusta=Count(
            "calificaciones_recibidas",
            filter=Q(calificaciones_recibidas__valor=CalificacionTecnico.Valor.ME_GUSTA),
            distinct=True,
        ),
        no_me_gusta=Count(
            "calificaciones_recibidas",
            filter=Q(calificaciones_recibidas__valor=CalificacionTecnico.Valor.NO_ME_GUSTA),
            distinct=True,
        ),
    )

    # El voto general es el único sin ticket: con el campo nuevo, una persona
    # puede tener varios votos del mismo técnico y sin filtrar la lista
    # "ganaba" uno al azar.
    mi_voto = dict(
        CalificacionTecnico.objects.filter(
            usuario=usuario_actual, ticket__isnull=True
        ).values_list("tecnico_id", "valor")
    )

    # Con el campo ticket, una persona puede tener varios votos del mismo
    # técnico: se cuentan de una vez para no preguntar por cada uno.
    votos_del_ticket = {}
    barras = {}
    if ticket is not None:
        for tecnico_id, usuario_id, valor in CalificacionTecnico.objects.filter(
            ticket=ticket
        ).values_list("tecnico_id", "usuario_id", "valor"):
            fila = votos_del_ticket.setdefault(
                tecnico_id, {"me_gusta": 0, "no_me_gusta": 0, "mi": 0}
            )
            if valor == CalificacionTecnico.Valor.ME_GUSTA:
                fila["me_gusta"] += 1
            else:
                fila["no_me_gusta"] += 1
            if usuario_id == usuario_actual.pk:
                fila["mi"] = valor
        for t in qs:
            barras[t.pk] = CalificacionTecnico.aprobacion_por_resueltos(t)

    ahora = timezone.now()
    lista = []
    for tecnico in qs:
        ultima = getattr(tecnico, "ultima_actividad", None)
        en_linea = bool(
            ultima and (ahora - ultima) <= timedelta(minutes=MINUTOS_EN_LINEA)
        )
        estado, etiqueta, detalle = _etiqueta_disponibilidad(tecnico.activos, en_linea)
        likes = tecnico.me_gusta or 0
        dislikes = tecnico.no_me_gusta or 0
        del_ticket = votos_del_ticket.get(tecnico.pk, {})
        lista.append(
            {
                "pk": tecnico.pk,
                "nombre": tecnico.nombre,
                "iniciales": tecnico.iniciales,
                "avatar": tecnico.avatar.url if tecnico.avatar else "",
                "email": tecnico.email,
                "telefono": getattr(tecnico, "telefono", ""),
                "ubicacion": getattr(tecnico, "ubicacion", ""),
                "activos": tecnico.activos or 0,
                "resueltos": tecnico.resueltos or 0,
                "en_linea": en_linea,
                "ultima_actividad": ultima,
                "estado": estado,
                "estado_etiqueta": etiqueta,
                "estado_detalle": detalle,
                "me_gusta": likes,
                "no_me_gusta": dislikes,
                "total_votos": likes + dislikes,
                "mi_voto": mi_voto.get(tecnico.pk, 0),
                # Lo siguiente solo tiene sentido cuando el modal se abre desde
                # un ticket ya resuelto: el tally de ese ticket y la barra de
                # aprobación contada sobre tickets resueltos.
                "mi_voto_ticket": del_ticket.get("mi", 0),
                "me_gusta_ticket": del_ticket.get("me_gusta", 0),
                "no_me_gusta_ticket": del_ticket.get("no_me_gusta", 0),
                "barra": barras.get(tecnico.pk),
                # Lo que la tarjeta muestra depende del alcance: desde un
                # ticket se ve el tally de ese ticket y el voto ahí; desde Mi
                # panel, el voto general al técnico.
                "voto_mostrar": (
                    del_ticket.get("mi", 0)
                    if ticket is not None
                    else mi_voto.get(tecnico.pk, 0)
                ),
                "conteo_up": (
                    del_ticket.get("me_gusta", 0) if ticket is not None else likes
                ),
                "conteo_down": (
                    del_ticket.get("no_me_gusta", 0) if ticket is not None else dislikes
                ),
            }
        )

    peso = {"disponible": 0, "ocupado": 1, "saturado": 2}
    lista.sort(key=lambda t: (peso.get(t["estado"], 3), t["nombre"].lower()))
    return lista
