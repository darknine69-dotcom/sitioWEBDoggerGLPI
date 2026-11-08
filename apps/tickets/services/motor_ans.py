"""Cálculo ANS de solo lectura. Los plazos provisionales no son evidencia histórica."""
from dataclasses import dataclass
from datetime import timedelta
from copy import copy

from django.utils import timezone


@dataclass(frozen=True)
class ResultadoANS:
    estado: str
    inicio: object = None
    limite: object = None
    evaluado_en: object = None
    transcurrido: object = None
    restante: object = None
    porcentaje: object = None
    incumplimiento: object = None
    cumplimiento: object = None
    provisional: bool = False
    calidad: str = "sin_informacion"


@dataclass(frozen=True)
class ResultadoEventoANS:
    evento_id: int
    ciclo: int
    tipo: str
    ocurrido_en: object
    limite: object
    estado: str
    cumplimiento: object
    calidad: str


def plazo_en_momento(ticket, momento, *, ajustes=None):
    """Plazo demostrable en un instante; None si el orden no puede probarse."""
    original = ticket.ans_limite_original
    if ticket.ans_verificacion not in ("verificado", "reconstruido") or not original:
        return None
    version = getattr(ticket, "ans_version_ajuste", 0)
    if not version:
        return original
    ajustes = list(ticket.ajustes_ans.order_by("version")) if ajustes is None else ajustes
    if len(ajustes) != version:
        return None
    vigente, previo, fecha_anterior = original, original, None
    for numero, ajuste in enumerate(ajustes, 1):
        fecha = ajuste.creado_en
        if (ajuste.version != numero or ajuste.limite_anterior != previo or not fecha
                or (fecha_anterior and fecha <= fecha_anterior) or fecha == momento):
            return None
        if fecha < momento:
            vigente = ajuste.limite_nuevo
        previo, fecha_anterior = ajuste.limite_nuevo, fecha
    return vigente


def calcular_ans(ticket, *, ahora=None, umbral=timedelta(hours=2), permitir_provisional=False, ajustes=None, eventos=None):
    """Calcula el estado sin guardar datos; por defecto exige evidencia histórica."""
    ahora = ahora if ahora is not None else timezone.now()
    if timezone.is_naive(ahora) or umbral < timedelta(0):
        raise ValueError("Se requiere fecha con zona horaria y umbral no negativo")
    desconocido = ticket.ans_verificacion == "desconocido"
    inicio = ticket.ans_inicio_original
    limite_original = ticket.ans_limite_original
    provisional = desconocido or ticket.ans_verificacion != "verificado" or not inicio or not limite_original
    if provisional and not permitir_provisional:
        return ResultadoANS(estado="sin_informacion")
    inicio = inicio or ticket.fecha_creacion
    terminal = ticket.estado in (ticket.Estado.RESUELTO, ticket.Estado.CERRADO)
    final = ticket.fecha_finalizacion if terminal else None
    if terminal and getattr(ticket, "pk", None) and not getattr(ticket._state, "adding", True):
        if eventos is None:
            eventos = list(ticket.transiciones_ans.order_by("ocurrido_en", "pk"))
        if eventos:
            ajustes_historial = ajustes if ajustes is not None else (None if ticket.ans_version_ajuste else [])
            historial = historial_ans(ticket, eventos=eventos, ajustes=ajustes_historial)
            if any(item.calidad == "sin_informacion" for item in historial):
                return ResultadoANS(estado="sin_informacion", inicio=inicio, provisional=provisional)
    # La evidencia del plazo en el cierre no se sustituye por ajustes posteriores.
    if terminal and final:
        limite = plazo_en_momento(ticket, final, ajustes=ajustes)
    elif ajustes is not None and getattr(ticket, "ans_version_ajuste", 0) and ajustes:
        limite = ajustes[-1].limite_nuevo
    elif ajustes is not None and getattr(ticket, "ans_version_ajuste", 0):
        limite = ticket.ans_limite_original or (ticket.fecha_creacion + timedelta(hours=ticket.ans_horas) if ticket.fecha_creacion else None)
    else:
        limite = ticket.fecha_limite_ans
    if not inicio or not limite or limite <= inicio:
        return ResultadoANS(estado="sin_informacion", provisional=provisional)
    if terminal and not final:
        return ResultadoANS(estado="sin_informacion", inicio=inicio, limite=limite, provisional=provisional)
    momento = final if terminal else ahora
    transcurrido = max(momento - inicio, timedelta(0))
    restante = max(limite - momento, timedelta(0))
    exceso = max(momento - limite, timedelta(0))
    porcentaje = transcurrido.total_seconds() / (limite - inicio).total_seconds() * 100
    if terminal:
        cumplimiento = momento <= limite
        estado = "cumplido" if cumplimiento else "incumplido"
    else:
        cumplimiento = None
        estado = "vencido" if momento >= limite else "por_vencer" if restante <= umbral else "vigente"
    calidad = "provisional" if provisional else "verificado"
    if terminal and provisional:
        cumplimiento = None
        estado = "sin_informacion"
    return ResultadoANS(estado, inicio, limite, momento, transcurrido, restante, porcentaje, exceso, cumplimiento, provisional, calidad)


def historial_ans(ticket, *, eventos=None, ajustes=None):
    """Evalúa eventos conservados, sin reconstruir transiciones ausentes."""
    eventos = list(ticket.transiciones_ans.order_by("ocurrido_en", "pk")) if eventos is None else eventos
    ajustes = list(ticket.ajustes_ans.order_by("version")) if ajustes is None else ajustes
    resultados = []
    ciclo_actual = 1
    terminal_previo = False
    tipos_ciclo = set()
    secuencia_incierta = False
    for indice, evento in enumerate(eventos):
        if evento.tipo not in ("resolucion", "cierre", "reapertura"):
            continue
        momento = evento.ocurrido_en
        if evento.tipo == "reapertura":
            if not terminal_previo or evento.ciclo != ciclo_actual + 1:
                secuencia_incierta = True
            ciclo_actual = evento.ciclo
            terminal_previo = False
            tipos_ciclo = set()
        else:
            if (evento.ciclo != ciclo_actual or evento.tipo in tipos_ciclo
                    or (evento.tipo == "resolucion" and "cierre" in tipos_ciclo)):
                secuencia_incierta = True
            tipos_ciclo.add(evento.tipo)
            terminal_previo = True
        ambiguo = ((indice > 0 and eventos[indice - 1].ocurrido_en == momento)
                   or (indice + 1 < len(eventos) and eventos[indice + 1].ocurrido_en == momento))
        # Dos eventos consecutivos de la misma operación resolución+cierre
        # son equivalentes respecto al plazo, pero no tienen orden temporal probado.
        limite = plazo_en_momento(ticket, momento, ajustes=ajustes)
        calidad = "verificado" if ticket.ans_verificacion == "verificado" else "provisional"
        if (not ticket.ans_inicio_original or not limite or ambiguo or secuencia_incierta
                or limite <= ticket.ans_inicio_original or momento < ticket.ans_inicio_original):
            calidad, estado, cumplimiento = "sin_informacion", "sin_informacion", None
        elif evento.tipo == "reapertura":
            estado, cumplimiento = "reapertura", None
        elif calidad != "verificado":
            estado, cumplimiento = "sin_informacion", None
        else:
            cumplimiento = momento <= limite
            estado = "cumplido" if cumplimiento else "incumplido"
        resultados.append(ResultadoEventoANS(evento.pk, evento.ciclo, evento.tipo, momento, limite, estado, cumplimiento, calidad))
    return resultados


def evaluar_lote(tickets, *, ahora=None, umbral=timedelta(hours=2), permitir_provisional=False, incluir_historial=False):
    """Evalúa un lote sin consultas por ticket ni cachés persistentes de resultados."""
    from django.db.models import prefetch_related_objects
    from apps.tickets.models import TicketAjusteANS, TicketTransicionANS

    tickets = list(tickets)
    # Solo los históricos sin duración necesitan la categoría actual para el
    # cálculo provisional. Refrescarla por lote evita consultas por ticket.
    categorias_pendientes = [ticket for ticket in tickets if ticket.categoria_id
                             and ticket.ans_duracion_original is None
                             and not ticket._state.fields_cache.get("categoria")]
    if categorias_pendientes:
        prefetch_related_objects(categorias_pendientes, "categoria")
    ids = [ticket.pk for ticket in tickets if ticket.pk is not None]
    ajustes = {pk: [] for pk in ids}
    eventos = {pk: [] for pk in ids}
    if ids:
        for indice in range(0, len(ids), 500):
            for ajuste in TicketAjusteANS.objects.filter(ticket_id__in=ids[indice:indice + 500]).order_by("ticket_id", "version"):
                ajustes[ajuste.ticket_id].append(ajuste)
        ids_eventos = ids if incluir_historial else [ticket.pk for ticket in tickets if ticket.estado in (ticket.Estado.RESUELTO, ticket.Estado.CERRADO)]
        for indice in range(0, len(ids_eventos), 500):
            for evento in TicketTransicionANS.objects.filter(ticket_id__in=ids_eventos[indice:indice + 500]).order_by("ticket_id", "ocurrido_en", "pk"):
                eventos[evento.ticket_id].append(evento)
    instante = ahora if ahora is not None else timezone.now()
    resultados = {}
    for ticket in tickets:
        if ticket.pk is None or ticket.pk in resultados:
            raise ValueError("El lote requiere tickets guardados con identificadores únicos")
        datos_ajustes = ajustes[ticket.pk]
        # La lista puede provenir de objetos cargados antes de un nuevo ajuste.
        # Usar una copia evita cambiar la instancia que recibió el llamador.
        evaluado = ticket
        if datos_ajustes and datos_ajustes[-1].version > ticket.ans_version_ajuste:
            evaluado = copy(ticket)
            evaluado.ans_version_ajuste = datos_ajustes[-1].version
        resultado = calcular_ans(evaluado, ahora=instante, umbral=umbral, permitir_provisional=permitir_provisional, ajustes=datos_ajustes, eventos=eventos[ticket.pk])
        resultados[ticket.pk] = (resultado, historial_ans(evaluado, eventos=eventos[ticket.pk], ajustes=datos_ajustes)) if incluir_historial else resultado
    return resultados
