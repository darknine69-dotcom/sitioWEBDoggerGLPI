"""Avisos de ANS: el ticket se está pasando del tiempo comprometido.

`Ticket.datos_ans` es quien decide en el servidor cuándo un ticket pasa a
«por vencer» y cuándo ya venció. Este módulo es el que manda los avisos una
sola vez cuando eso ocurre:

  · campana y correo al técnico asignado, que es quien tiene que resolver,
  · campana y correo a la persona que abrió el ticket, que es quien espera,
  · campana al observador que supervisa a esa persona, con enlace directo al
    caso para que pueda presionar al técnico.

La marca `Ticket.ans_alertado_en` evita repetir: ni el cron ni el panel vuelven
a mandar nada mientras exista. Si el ticket se resuelve antes del límite, ya no
hace falta avisar de nada porque aquí solo se miran abiertos y en progreso.

Tres caminos entran aquí: el comando `avisar_ans_por_vencer` (para el cron),
la campana de notificaciones (con revisión periódica) y el panel del
observador al entrar.

El umbral no se inventa aquí: es el de siempre (25 % del plazo, o las dos
últimas horas si eso resulta más tarde), el mismo que pinta la etiqueta y hace
correr el cronómetro. Si se calculase distinto, el aviso y el reloj se
contradecirían delante del usuario.
"""

import logging
from itertools import islice

from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .models import ElementoMiLista, Ticket
from .services.motor_ans import evaluar_lote

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
    iterador = pendientes.iterator(chunk_size=200)
    ahora = timezone.now()
    while True:
        bloque = list(islice(iterador, 200))
        if not bloque:
            break
        resultados = evaluar_lote(bloque, ahora=ahora, permitir_provisional=True)
        for ticket in bloque:
            resultado = resultados[ticket.pk]
            estado, texto, detalle, _limite, _aviso = ticket.datos_ans_desde_resultado(resultado)
            if estado not in AVISABLES:
                continue
            ticket.ans_estado = estado
            ticket.ans_texto = texto
            ticket.ans_detalle = detalle
            salen.append((ticket, resultado.limite))
            if limite is not None and len(salen) >= limite:
                break
        if limite is not None and len(salen) >= limite:
            break
    # Vencidos primero, y dentro de cada grupo lo que se va antes.
    salen.sort(
        key=lambda item: (item[0].ans_estado != "vencido", item[1] or ahora)
    )
    return [ticket for ticket, _ in salen]


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


def _aviso_campana(usuario, ticket, texto, *, clave, url):
    from apps.notificaciones.models import Notificacion
    from apps.notificaciones.services import crear

    existente = Notificacion.objects.filter(usuario=usuario, clave=clave).first()
    if existente:
        if existente.url != url:
            existente.url = url
            existente.save(update_fields=["url"])
        return None

    tecnico = ticket.tecnico_asignado
    nombre_tec = (tecnico.nombre if tecnico else "") or "sin técnico"
    return crear(
        usuario,
        Notificacion.Tipo.TICKET_RECORDATORIO,
        f"{ticket.codigo} está {texto.lower()}",
        f"{ticket.solicitante_nombre or 'Sin nombre'} · "
        f"{ticket.get_prioridad_display()} · {nombre_tec}",
        url=url,
        icono="i-stopwatch",
        clave=clave,
        actor="Sistema ANS",
        actor_rol="Sistema",
    )


def avisos_en_campana(ticket, texto, observadores=None):
    """Notifica en la aplicación al técnico, solicitante y supervisores."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    creadas = []
    estado = getattr(ticket, "ans_estado", None) or ticket.datos_ans[0]
    sufijo = ":vencido" if estado == "vencido" else ""
    if sufijo:
        from django.db import transaction
        from apps.notificaciones.models import AlertaOperativa, HistorialAlerta
        with transaction.atomic():
            alerta, creada = AlertaOperativa.objects.get_or_create(
                clave_origen=f"ticket:{ticket.pk}:ans_vencido", defaults={"ticket": ticket, "tipo": "ans_vencido", "responsable_id": ticket.tecnico_asignado_id, "codigo_ticket": ticket.codigo, "titulo_ticket": ticket.titulo[:200]}
            )
            if creada:
                HistorialAlerta.objects.create(alerta=alerta, accion="creada")
            elif alerta.estado == AlertaOperativa.Estado.RESUELTA:
                reabierta = AlertaOperativa.objects.filter(pk=alerta.pk, estado=AlertaOperativa.Estado.RESUELTA).update(
                    estado=AlertaOperativa.Estado.ABIERTA, reconocida_en=None, resuelta_en=None,
                    responsable_id=ticket.tecnico_asignado_id,
                )
                if reabierta:
                    HistorialAlerta.objects.create(alerta=alerta, accion="reabierta")
        # Conservar enlaces antiguos del observador sin reutilizar su estado.
        from apps.notificaciones.models import Notificacion
        Notificacion.objects.filter(clave=f"ans-{ticket.pk}").update(
            url=_url_seccion(ancla=f"#ans-ticket-{ticket.pk}")
        )
    tecnico = ticket.tecnico_asignado
    if tecnico and getattr(tecnico, "activo", True):
        aviso = _aviso_campana(
            tecnico, ticket, texto,
            clave=f"ans-{ticket.pk}:tecnico{sufijo}",
            url=reverse("tickets:detalle", args=[ticket.pk]),
        )
        if aviso:
            creadas.append(aviso)

    correo = (ticket.solicitante_email or "").strip()
    if correo:
        solicitantes = User.objects.filter(
            email__iexact=correo,
            rol=User.Rol.USUARIO,
            activo=True,
            is_active=True,
        )
        for solicitante in solicitantes:
            aviso = _aviso_campana(
                solicitante, ticket, texto,
                clave=f"ans-{ticket.pk}:solicitante:{solicitante.pk}{sufijo}",
                url=reverse("tickets:mi_ticket", args=[ticket.pk]),
            )
            if aviso:
                creadas.append(aviso)

    ancla = f"#ans-ticket-{ticket.pk}"
    if observadores is None:
        observadores = observadores_de(ticket)
    for observador in observadores:
        aviso = _aviso_campana(
            observador, ticket, texto,
            clave=f"ans-{ticket.pk}{sufijo}",
            url=_url_seccion(ancla=ancla),
        )
        if aviso:
            creadas.append(aviso)
    return creadas


def avisar(ticket, observadores=None):
    """Manda todos los avisos de un ticket y lo marca. Devuelve cuántos salió.

    El correo a técnico y a usuario va aunque no haya ningún observador
    mirando: el compromiso de tiempo es del helpdesk, no de la supervisión.
    """
    with transaction.atomic():
        # La reserva y el encolado durable se confirman juntos; otras pasadas
        # no pueden reclamar el mismo ticket al mismo tiempo.
        reclamado = Ticket.objects.filter(pk=ticket.pk, ans_alertado_en__isnull=True).update(ans_alertado_en=timezone.now())
        if not reclamado:
            return 0
        return _enviar_aviso_reclamado(ticket, observadores)


def _enviar_aviso_reclamado(ticket, observadores=None):
    from apps.notificaciones.emails import (
        correo_ans_por_vencer_tecnico,
        correo_ans_por_vencer_usuario,
    )

    from .services.motor_ans import calcular_ans
    ahora = timezone.now()
    resultado = calcular_ans(ticket, ahora=ahora, permitir_provisional=True)
    if resultado.limite is None:
        raise ValueError("El ticket no tiene un plazo ANS evaluable")
    restante = resultado.limite - ahora
    enviados = 0

    tecnico = ticket.tecnico_asignado
    if tecnico and getattr(tecnico, "activo", True):
        if not correo_ans_por_vencer_tecnico(ticket, restante):
            raise RuntimeError("No se pudo registrar el correo ANS del técnico")
        enviados += 1

    if (ticket.solicitante_email or "").strip():
        if not correo_ans_por_vencer_usuario(ticket, restante):
            raise RuntimeError("No se pudo registrar el correo ANS del solicitante")
        enviados += 1

    # El texto viene calculado desde la lista; si alguien llama a `avisar`
    # directo, se pide al propio ticket para no dejar el título a medias.
    texto = getattr(ticket, "ans_texto", "") or ticket.datos_ans[1]
    notificaciones = avisos_en_campana(ticket, texto, observadores)
    enviados += len(notificaciones)

    return enviados


def completar_campanas_pendientes(limite=LIMITE_POR_EJECUCION):
    """Crea avisos de campana que falten para ANS activos, sin reenviar correo."""
    tickets = por_vencer(
        limite=limite,
        solo_sin_avisar=False,
    )
    avisos = []
    for ticket in tickets:
        avisos.extend(avisos_en_campana(ticket, ticket.ans_texto))
    return avisos


def revisar_y_avisar(consulta=None, limite=LIMITE_POR_EJECUCION):
    """Avisa de todos los tickets por vencer que aún no se avisaron.

    Entrada del cron (`manage.py avisar_ans_por_vencer`) y del panel del
    observador. Devuelve la lista de los tickets avisados, por si el llamante
    quiere contarlos o imprimirlos.
    """
    _revisar_inactividad(consulta=consulta, limite=limite)
    if consulta is None:
        _escalar_inactividad(limite=limite)
    avisados = []
    for ticket in por_vencer(consulta=consulta, limite=limite):
        try:
            if ticket.ans_estado == "vencido":
                # La alerta operativa no depende de que SMTP esté disponible.
                avisos_en_campana(ticket, ticket.ans_texto)
            avisar(ticket)
        except Exception:  # noqa: BLE001 - un correo malo no frena al resto
            logger.exception("No se pudo avisar el ANS de %s", ticket.codigo)
            continue
        avisados.append(ticket)
    # La marca histórica de correo es única; la campana sí debe reflejar
    # la transición posterior a vencido sin reenviar el correo anterior.
    for ticket in por_vencer(consulta=consulta, limite=limite, solo_sin_avisar=False):
        if ticket.ans_alertado_en and ticket.ans_estado == "vencido":
            avisos_en_campana(ticket, ticket.ans_texto)
    return avisados


def _escalar_inactividad(limite=LIMITE_POR_EJECUCION):
    """Escala una sola vez por destinatario, únicamente si la regla está activa."""
    from datetime import timedelta
    from django.contrib.auth import get_user_model
    from apps.tickets.models import ConfigSitio
    from apps.notificaciones.models import AlertaOperativa, EntregaEscalamiento, HistorialAlerta, Notificacion
    from apps.notificaciones.services import crear

    regla = ConfigSitio.cargar().escalamiento_inactividad or {}
    horas = regla.get("horas")
    if regla.get("habilitado") is not True or not isinstance(horas, int) or horas < 1:
        return
    ahora = timezone.now()
    candidatos = AlertaOperativa.objects.filter(
        tipo="ticket_inactivo", estado=AlertaOperativa.Estado.ABIERTA,
        creada_en__lte=ahora - timedelta(hours=horas), ticket__isnull=False,
        ticket__estado__in=[Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO],
        ticket__eliminado_en__isnull=True,
    ).order_by("creada_en", "pk")
    if limite is not None:
        candidatos = candidatos[:limite]
    for alerta_id in candidatos.values_list("pk", flat=True):
        try:
            with transaction.atomic():
                alerta = AlertaOperativa.objects.select_for_update().get(pk=alerta_id)
                ticket = Ticket.objects.select_for_update().filter(pk=alerta.ticket_id, estado__in=[Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO]).first()
                if (not ticket or alerta.estado != AlertaOperativa.Estado.ABIERTA
                        or not alerta.ultima_actividad_en or ticket.fecha_actualizacion > alerta.ultima_actividad_en
                        or alerta.historial.filter(accion="seguimiento").exists()
                        or ticket.comentarios.filter(usuario__rol__in=["admin", "tecnico"], fecha__gt=alerta.ultima_actividad_en).exists()):
                    continue
                destinatarios = []
                if regla.get("administradores") is True:
                    destinatarios.extend(get_user_model().objects.filter(rol="admin", activo=True, is_active=True))
                if regla.get("observadores") is True:
                    destinatarios.extend(u for u in observadores_de(ticket) if u.rol == "observador" and u.is_active and u.activo)
                if regla.get("tecnico") is True and ticket.tecnico_asignado_id:
                    tecnico = ticket.tecnico_asignado
                    if tecnico and tecnico.rol in ("admin", "tecnico") and tecnico.is_active and tecnico.activo:
                        destinatarios.append(tecnico)
                if regla.get("solicitante") is True and ticket.solicitante_email:
                    destinatarios.extend(get_user_model().objects.filter(
                        email=ticket.solicitante_email, rol="usuario", activo=True, is_active=True
                    ))
                for destinatario in {u.pk: u for u in destinatarios}.values():
                    if EntregaEscalamiento.objects.filter(alerta=alerta, usuario=destinatario).exists():
                        continue
                    if destinatario.rol == "observador":
                        url = reverse("notificaciones:alertas_operativas") + f"?estado=todas&alerta={alerta.pk}#alerta-{alerta.pk}"
                    elif destinatario.rol == "usuario":
                        url = reverse("tickets:mi_ticket", args=[ticket.pk])
                    else:
                        url = reverse("tickets:detalle", args=[ticket.pk])
                    titulo = f"Tu ticket {ticket.codigo} sigue pendiente" if destinatario.rol == "usuario" else f"Escalamiento: {ticket.codigo} sin atención"
                    mensaje = ("Tu solicitud sigue pendiente de atención. Puedes consultar su estado aquí."
                               if destinatario.rol == "usuario" else
                               f"Prioridad {ticket.get_prioridad_display()} · alerta de inactividad sin seguimiento.")
                    aviso = crear(destinatario, Notificacion.Tipo.TICKET_RECORDATORIO,
                        titulo, mensaje,
                        url=url, clave=f"escalamiento:{alerta.pk}:{destinatario.pk}")
                    if aviso:
                        EntregaEscalamiento.objects.create(alerta=alerta, usuario=destinatario)
                        HistorialAlerta.objects.create(alerta=alerta, accion="escalada", detalle=f"Destinatario: {destinatario.nombre}"[:500])
        except Exception:
            logger.exception("No se pudo procesar escalamiento de alerta %s", alerta_id)


def _revisar_inactividad(consulta=None, limite=LIMITE_POR_EJECUCION):
    """Alertas por prioridad en horas transcurridas, independientes del ANS."""
    from datetime import timedelta
    from django.db.models import Max
    from apps.tickets.models import ConfigSitio
    from apps.notificaciones.models import AlertaOperativa, HistorialAlerta, Notificacion
    from apps.notificaciones.services import crear

    if consulta is None:
        # Una alerta de inactividad o ANS no debe permanecer activa cuando el
        # ticket ya se resolvió. Se conserva y audita, sin cambiar el ticket.
        cerradas = AlertaOperativa.objects.filter(
            tipo__in=["ans_vencido", "ticket_inactivo"],
            ticket__estado__in=[Ticket.Estado.RESUELTO, Ticket.Estado.CERRADO],
        ).exclude(estado=AlertaOperativa.Estado.RESUELTA).values_list("pk", flat=True)
        for alerta_id in cerradas.iterator():
            with transaction.atomic():
                actualizada = AlertaOperativa.objects.filter(pk=alerta_id).exclude(estado=AlertaOperativa.Estado.RESUELTA).update(
                    estado=AlertaOperativa.Estado.RESUELTA, resuelta_en=timezone.now()
                )
                if actualizada:
                    HistorialAlerta.objects.create(alerta_id=alerta_id, accion="ticket_cerrado")

    limites = {"urgente": 1, "alta": 4, "media": 12, "baja": 24}
    limites.update(ConfigSitio.cargar().limites_inactividad or {})
    ahora = timezone.now()
    condiciones = Q(pk__in=[])
    for prioridad, horas in limites.items():
        if prioridad in ("urgente", "alta", "media", "baja") and isinstance(horas, int) and horas > 0:
            condiciones |= Q(prioridad=prioridad, fecha_actualizacion__lte=ahora - timedelta(hours=horas))
    tickets = (_abiertos(consulta).filter(condiciones)
               .annotate(ultimo_comentario=Max("comentarios__fecha", filter=Q(comentarios__usuario__rol__in=["admin", "tecnico"])))
               .order_by("fecha_actualizacion", "pk"))
    if limite is not None:
        tickets = tickets[:limite]
    for ticket in tickets:
        ultima = max(fecha for fecha in (ticket.fecha_actualizacion, ticket.ultimo_comentario) if fecha)
        segundos = int((ahora - ultima).total_seconds())
        if segundos < limites[ticket.prioridad] * 3600:
            continue
        clave = f"ticket:{ticket.pk}:inactivo:{int(ultima.timestamp())}"
        with transaction.atomic():
            alerta, creada = AlertaOperativa.objects.get_or_create(clave_origen=clave, defaults={
                "ticket": ticket, "tipo": "ticket_inactivo", "responsable": ticket.tecnico_asignado,
                "codigo_ticket": ticket.codigo, "titulo_ticket": ticket.titulo[:200],
                "severidad": {"urgente": "crítica", "alta": "alta", "media": "media", "baja": "baja"}[ticket.prioridad],
                "ultima_actividad_en": ultima, "inactividad_segundos": segundos,
            })
            if creada:
                HistorialAlerta.objects.create(alerta=alerta, accion="creada")
                if ticket.tecnico_asignado_id:
                    crear(ticket.tecnico_asignado, Notificacion.Tipo.TICKET_RECORDATORIO,
                          f"{ticket.codigo}: ticket sin actividad",
                          f"Prioridad {ticket.get_prioridad_display()} · {segundos // 3600} h sin actividad. Revisa el caso.",
                          url=reverse("tickets:detalle", args=[ticket.pk]), clave=f"inactividad:{alerta.pk}:tecnico")


def tickets_del_observador(usuario, alertas=False):
    """Consulta de tickets de las cuentas que el observador sigue.

    Es el mismo recorte que usa su panel: personas de su lista y, si tiene
    puntos asignados por el administrador, también sus tickets. `alertas=True`
    limita a las personas cuya zona tiene las alertas ANS encendidas.
    """
    consulta = Ticket.objects.filter(
        estado__in=[Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO]
    ).select_related("categoria", "tecnico_asignado")

    elementos = ElementoMiLista.objects.filter(observador=usuario).select_related("usuario")
    correos = {
        (elemento.usuario_email or (
            elemento.usuario.email if elemento.usuario_id else ""
        )).strip().lower()
        for elemento in elementos
    }
    correos.discard("")
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
        ).select_related("usuario")
        correos = {
            (elemento.usuario_email or (
                elemento.usuario.email if elemento.usuario_id else ""
            )).strip().lower()
            for elemento in filtrados
        }
        correos.discard("")
        puntos = list(
            filtrados.exclude(punto__isnull=True).values_list(
                "punto__nombre", flat=True
            )
        )

    if not correos and not puntos:
        return consulta.none()
    condicion = None
    if correos:
        for correo in correos:
            correo_q = Q(solicitante_email__iexact=correo)
            condicion = correo_q if condicion is None else (condicion | correo_q)
    if puntos:
        punto_q = Q(solicitante_punto__in=puntos)
        condicion = punto_q if condicion is None else (condicion | punto_q)
    return consulta.filter(condicion)
