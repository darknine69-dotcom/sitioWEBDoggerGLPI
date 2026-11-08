"""Construcción de fechas ficticias en bases efímeras de pruebas."""
from datetime import timedelta
from django.db.models import QuerySet
from apps.tickets.models import Ticket


def envejecer_ticket(ticket, inicio, **otros):
    """Simula que el ticket y su instantánea se crearon a la vez."""
    QuerySet.update(Ticket.objects.filter(pk=ticket.pk), fecha_creacion=inicio,
                    ans_inicio_original=inicio,
                    ans_limite_original=inicio + timedelta(hours=ticket.ans_horas), **otros)
    ticket.refresh_from_db()
    return ticket
