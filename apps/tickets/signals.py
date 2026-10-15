"""Invalidación del caché ante cambios en datos base.

Las llaves versionadas (categorías) se invalidan solas; aquí solo se
limpian las que dependen de TTL: puntos del observador.
"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.tickets.models import ObservadorPunto
from apps.tickets.services.cache import invalidar


@receiver([post_save, post_delete], sender=ObservadorPunto)
def _limpiar_puntos_observador(sender, instance, **kwargs):
    invalidar("obs", "puntos", instance.observador_id)
