"""Consulta de eventos verificables para el futuro registro de actividad.

Los comentarios son hechos existentes; no se deducen cambios de estado ni
asignaciones históricas del estado actual del ticket.
"""
from django.core.paginator import Paginator
from django.db.models import Count, Q

from .models import TicketComentario


ROLES = ("usuario", "tecnico", "observador", "admin")


def consultar_seguimientos(parametros, por_pagina=5):
    base = TicketComentario.objects.select_related("ticket", "usuario").order_by("-fecha", "-pk")
    codigo = (parametros.get("codigo") or "").strip()[:80]
    if codigo:
        base = base.filter(ticket__codigo__icontains=codigo)
    tipo = parametros.get("tipo")
    if tipo == "presion":
        base = base.filter(es_presion=True)
    elif tipo == "seguimiento":
        base = base.filter(es_presion=False)
    conteos = dict(base.values("usuario__rol").annotate(total=Count("pk")).values_list("usuario__rol", "total"))
    rol = parametros.get("rol")
    if rol in ROLES:
        base = base.filter(usuario__rol=rol)
    busqueda = (parametros.get("q") or "").strip()[:100]
    if busqueda:
        base = base.filter(Q(ticket__codigo__icontains=busqueda) | Q(autor_nombre__icontains=busqueda))
    pagina = Paginator(base, por_pagina).get_page(parametros.get("page"))
    return pagina, conteos
