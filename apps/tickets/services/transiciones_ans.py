"""Transiciones serializadas y auditoría futura de estados de tickets."""
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import PermissionDenied, ValidationError

from apps.tickets.models import Ticket, TicketTransicionANS, TicketAjusteANS


class EstadoTicketModificado(Exception):
    """El estado cambió después de que el usuario lo consultó."""


def ajustar_plazo_ans(ticket_id, limite_nuevo, *, actor, motivo, clave, version_esperada):
    """Añade un ajuste auditado sin sobrescribir el plazo original."""
    if not (actor and actor.is_authenticated and actor.activo and actor.rol == "admin"):
        raise PermissionDenied("Se requiere un administrador activo.")
    motivo = (motivo or "").strip()
    clave = (clave or "").strip()
    if not motivo or not clave or len(clave) > 64 or not limite_nuevo or timezone.is_naive(limite_nuevo):
        raise ValidationError("Se requiere plazo con zona horaria, motivo y clave de solicitud válida.")
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update().get(pk=ticket_id)
        existente = TicketAjusteANS.objects.filter(clave=clave).first()
        if existente:
            if (existente.ticket_id == ticket.pk and existente.actor_id == actor.pk
                    and existente.limite_nuevo == limite_nuevo and existente.motivo == motivo):
                return existente
            raise ValidationError("La clave ya corresponde a otra solicitud.")
        if ticket.ans_version_ajuste != version_esperada:
            raise EstadoTicketModificado("El plazo cambió; actualiza la página.")
        limite_anterior = ticket.fecha_limite_ans
        version = version_esperada + 1
        if not Ticket.objects.filter(pk=ticket.pk, ans_version_ajuste=version_esperada)._reservar_version_ajuste(version):
            raise EstadoTicketModificado("El plazo cambió; actualiza la página.")
        return TicketAjusteANS.objects.create(ticket=ticket, actor=actor, limite_anterior=limite_anterior,
                                               limite_nuevo=limite_nuevo, motivo=motivo, clave=clave, version=version)


def crear_tickets_ans(tickets):
    """Alternativa atómica a bulk_create: conserva save e instantáneas ANS."""
    creados = []
    with transaction.atomic():
        for ticket in tickets:
            if not ticket._state.adding:
                raise ValueError("Todos los tickets deben ser nuevos")
            ticket.save(force_insert=True)
            creados.append(ticket)
    return creados


def cambiar_estado_ans(ticket_id, estado, *, actor=None, estado_esperado=None, resolver_y_cerrar=False):
    if estado not in dict(Ticket.Estado.choices):
        raise ValueError("Estado de ticket inválido")
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update().get(pk=ticket_id)
        anterior = ticket.estado
        if estado_esperado is not None and anterior != estado_esperado:
            raise EstadoTicketModificado("El ticket cambió; actualiza la página.")
        final = Ticket.Estado.CERRADO if resolver_y_cerrar else estado
        if anterior == final:
            return ticket
        # La actualización condicional adquiere un bloqueo de escritura incluso
        # en motores donde select_for_update no ofrece bloqueo de fila.
        actualizado = Ticket.objects.filter(pk=ticket.pk, estado=anterior)._actualizar_estado_ans(final)
        if actualizado != 1:
            raise EstadoTicketModificado("El ticket cambió; actualiza la página.")
        terminales = (Ticket.Estado.RESUELTO, Ticket.Estado.CERRADO)
        activos = (Ticket.Estado.ABIERTO, Ticket.Estado.EN_PROGRESO)
        ciclo = 1 + ticket.transiciones_ans.filter(tipo="reapertura").count()
        tipo = "estado"
        if anterior in terminales and final in activos:
            ciclo += 1
            tipo = "reapertura"
        elif resolver_y_cerrar or final == Ticket.Estado.RESUELTO:
            tipo = "resolucion"
        elif final == Ticket.Estado.CERRADO:
            tipo = "cierre"
        ticket.estado = final
        if resolver_y_cerrar:
            ticket.fecha_resolucion = timezone.now()
        ticket._ans_transicion_autorizada = True
        try:
            ticket.save(update_fields=["estado", "fecha_resolucion", "fecha_cierre", "fecha_actualizacion"])
        finally:
            del ticket._ans_transicion_autorizada
        evento = {"ticket": ticket, "estado_anterior": anterior, "estado_nuevo": final,
                  "ciclo": ciclo, "actor": actor if getattr(actor, "pk", None) else None}
        TicketTransicionANS.objects.create(tipo=tipo, **evento)
        if resolver_y_cerrar:
            TicketTransicionANS.objects.create(tipo="cierre", **evento)
        return ticket
