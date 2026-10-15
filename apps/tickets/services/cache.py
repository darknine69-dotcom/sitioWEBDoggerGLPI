"""Caché barato para lo que se recalcula en cada request.

Sin Redis en el hosting: LocMemCache por proceso con TTL cortos. Todo lo
que se cachea aquí es idempotente (listas de puntos, sugerencias de
categorías, modal de técnicos) y lleva versión auto-invalidante o TTL,
así un dato viejo como mucho dura minutos.

En pruebas se omite el caché para que cada test vea datos frescos.
"""

from django.core.cache import cache

from .fondo import en_pruebas

PREFIJO = "dogger"


def clave(*partes):
    return ":".join([PREFIJO] + [str(p) for p in partes])


def cachear(llave, constructor, segundos=300):
    """Devuelve lo cacheado o construye, guarda y devuelve.

    `constructor` es un callable sin argumentos (se evalúa perezoso, solo
    si hace falta).
    """
    if en_pruebas():
        return constructor()
    return cache.get_or_set(llave, constructor, segundos)


def invalidar(*partes):
    """Borra una llave (la usan las señales al cambiar datos base)."""
    cache.delete(clave(*partes))
