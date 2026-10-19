"""Avisos de ANS: el ticket se está pasando del tiempo comprometido.

`Ticket.datos_ans` es quien decide en el servidor cuándo un ticket pasa a
«por vencer» y cuándo ya venció. Este módulo es el que manda los avisos una
sola vez cuando eso ocurre:

  · correo al técnico asignado, que es quien tiene que resolver,
  · correo a la persona que abrió el ticket, que es quien está esperando,
  · campana al observador que supervisa a esa persona, con el enlace a su
    sección de «Por vencer» para que le presione.

La marca `Ticket.ans_alertado_en` evita repetir: ni el cron ni el panel vuelven
a mandar nada mientras exista. Si el ticket se resuelve antes del límite, ya no
hace falta avisar de nada porque aquí solo se miran abiertos y en progreso.

Dos caminos entran aquí: el comando `avisar_ans_por_vencer` (para el cron) y el
panel del observador cuando alguien entra, así el sistema no depende de que
haya un programador configurado.

El umbral no se inventa aquí: es el de siempre (25 % del plazo, o las dos
últimas horas si eso resulta más tarde), el mismo que pinta la etiqueta y hace
correr el cronómetro. Si se calculase distinto, el aviso y el reloj se
contradecirían delante del usuario.
"""

import logging

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .models import ElementoMiLista, Ticket

logger = logging.getLogger(__name__)

# Estados de `datos_ans` que avisan: el ticket está por vencer o ya venció.
AVISABLES = ("por-vencer", "vencido")

# Cuántos tickets se miran de una pasada: suficiente para un turno y acotado
# para que el cron no se coma el tablero si alguien lo deja mal programado.
LIMITE_POR_EJECUCION = 500


def _abiertos(consulta=None):
    """Solo tickets vivos: cerrado o resuelto ya no tiene ANS que vigilar."""
    base = consulta if consulta is not None else Ticket.objects.all()
    return base.filter(
        estado__in=[Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO]
    ).select_related("categoria", "tecnico_asignado")


def por_vencer(consulta=None, limite=LIMITE_POR_EJECUCION, solo_sin_avisar=True):
    """Tickets abiertos cuyo ANS ya está «por vencer» o vencido.

    Cada fila sale con `ans_estado`, `ans_texto` y `ans_detalle` puestos, que
    son los mismos tres valores que pinta la etiqueta en pantalla; se calculan
    aquí y no en la plantilla para que ordenar por lo más urgente sea directo.

    `solo_sin_avisar` quita los que ya se avisaron, que es lo que quiere el
    cron. La vista del observador lo pasa a False: el panel tiene que seguir
    enseñando los que ya se avisaron, porque siguen sin resolverse.
    """
    salen = []
    pendientes = _abiertos(consulta)
    if solo_sin_avisar:
        pendientes = pendientes.filter(ans_alertado_en__isnull=True)
    for ticket in pendientes.iterator():
        estado, texto, detalle, _limite, _aviso = ticket.datos_ans
        if estado not in AVISABLES:
            continue
        ticket.ans_estado = estado
        ticket.ans_texto = texto
        ticket.ans_detalle = detalle
        salen.append(ticket)
        if len(salen) >= limite:
            break
    # Vencidos primero, y dentro de cada grupo lo que se va antes.
    salen.sort(
        key=lambda t: (t.ans_estado != "vencido", t.fecha_limite_ans or timezone.now())
    )
    return salen


def observadores_de(ticket):
    """Quién supervisa a la persona del ticket y tiene las alertas ANS puestas.

    La carpeta manda: las alertas ANS se encienden y se apagan zona por zona
    (`ZonaObservador.alertas_ans`), así que solo avisa quien tenga a esa
    persona en su lista y en una zona con el interruptor puesto. Quien está en
    la lista sin zona todavía no recibe nada: no hay carpeta que decida.
    """
    email = (ticket.solicitante_email or "").strip().lower()
    punto = (ticket.solicitante_punto or "").strip()
    if not email and not punto:
        return []
    consulta = ElementoMiLista.objects.filter(
        observador__activo=True, zona__alertas_ans=True
    ).select_related("observador", "zona")
    if email:
        consulta = consulta.filter(usuario_email__iexact=email)
    else:
        consulta = consulta.filter(punto__nombre=punto)
    salen, vistos = [], set()
    for elemento in consulta:
        observador = elemento.observador
        if observador and observador.pk not in vistos:
            vistos.add(observador.pk)
            salen.append(observador)
    return salen


def _url_seccion(nombre="tickets:obs_monitoreo", ancla="#por-vencer"):
    """Enlace absoluto a la sección de «Por vencer» del panel del observador."""
    from django.conf import settings

    ruta = reverse(nombre) + ancla
    base = getattr(settings, "SITE_URL", "") or ""
    return f"{base.rstrip('/')}{ruta}" if base else ruta


def aviso_en_campana(observador, ticket, texto):
    """Deja el aviso en la campana del observador, uno por ticket."""
    from apps.notificaciones.models import Notificacion
    from apps.notificaciones.services import crear

    tecnico = ticket.tecnico_asignado
    nombre_tec = (tecnico.nombre if tecnico else "") or "sin técnico"
    return crear(
        observador,
        Notificacion.Tipo.TICKET_RECORDATORIO,
        f"{ticket.codigo} está {texto.lower()}",
        f"{ticket.solicitante_nombre or 'Sin nombre'} · "
        f"{ticket.get_prioridad_display()} · {nombre_tec}",
        url=_url_seccion(),
        icono="i-stopwatch",
        clave=f"ans-{ticket.pk}",
        actor="Sistema ANS",
        actor_rol="Sistema",
    )


def avisar(ticket, observadores=None):
    """Manda todos los avisos de un ticket y lo marca. Devuelve cuántos salió.

    El correo a técnico y a usuario va aunque no haya ningún observador
    mirando: el compromiso de tiempo es del helpdesk, no de la supervisión.
    """
    from apps.notificaciones.emails import (
        correo_ans_por_vencer_tecnico,
        correo_ans_por_vencer_usuario,
    )

    restante = ticket.fecha_limite_ans - timezone.now()
    enviados = 0

    tecnico = ticket.tecnico_asignado
    if tecnico and getattr(tecnico, "activo", True):
        if correo_ans_por_vencer_tecnico(ticket, restante):
            enviados += 1

    if (ticket.solicitante_email or "").strip():
        if correo_ans_por_vencer_usuario(ticket, restante):
            enviados += 1

    if observadores is None:
        observadores = observadores_de(ticket)
    # El texto viene calculado desde la lista; si alguien llama a `avisar`
    # directo, se pide al propio ticket para no dejar el título a medias.
    texto = getattr(ticket, "ans_texto", "") or ticket.datos_ans[1]
    for observador in observadores:
        if aviso_en_campana(observador, ticket, texto):
            enviados += 1

    ticket.ans_alertado_en = timezone.now()
    ticket.save(update_fields=["ans_alertado_en"])
    return enviados


def revisar_y_avisar(consulta=None, limite=LIMITE_POR_EJECUCION):
    """Avisa de todos los tickets por vencer que aún no se avisaron.

    Entrada del cron (`manage.py avisar_ans_por_vencer`) y del panel del
    observador. Devuelve la lista de los tickets avisados, por si el llamante
    quiere contarlos o imprimirlos.
    """
    avisados = []
    for ticket in por_vencer(consulta=consulta, limite=limite):
        try:
            avisar(ticket)
        except Exception:  # noqa: BLE001 - un correo malo no frena al resto
            logger.exception("No se pudo avisar el ANS de %s", ticket.codigo)
            continue
        avisados.append(ticket)
    return avisados


def tickets_del_observador(usuario, alertas=False):
    """Consulta de tickets de las cuentas que el observador sigue.

    Es el mismo recorte que usa su panel: personas de su lista y, si tiene
    puntos asignados por el administrador, también sus tickets. `alertas=True`
    limita a las personas cuya zona tiene las alertas ANS encendidas.
    """
    consulta = Ticket.objects.filter(
        estado__in=[Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO]
    ).select_related("categoria", "tecnico_asignado")

    correos = [
        e.usuario_email
        for e in ElementoMiLista.objects.filter(observador=usuario).exclude(
            usuario_email=""
        )
    ]
    puntos = list(
        ElementoMiLista.objects.filter(observador=usuario).exclude(
            punto__isnull=True
        ).values_list("punto__nombre", flat=True)
    )

    if alertas:
        # Solo las carpetas con el interruptor puesto: lo que la zona decide
        # no se le impone a la supervisión.
        filtrados = ElementoMiLista.objects.filter(
            observador=usuario, zona__alertas_ans=True
        )
        correos = [
            e.usuario_email
            for e in filtrados.exclude(usuario_email="")
        ]
        puntos = list(
            filtrados.exclude(punto__isnull=True).values_list(
                "punto__nombre", flat=True
            )
        )

    if not correos and not puntos:
        return consulta.none()
    condicion = None
    if correos:
        condicion = Q(solicitante_email__in=correos)
    if puntos:
        punto_q = Q(solicitante_punto__in=puntos)
        condicion = punto_q if condicion is None else (condicion | punto_q)
    return consulta.filter(condicion)
