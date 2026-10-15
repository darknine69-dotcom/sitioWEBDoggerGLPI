"""Trabajo en segundo plano sin Celery: hilos cortos para IO lento.

Correos y GLPI no deben frenar el request: SMTP puede tardar segundos y
la API de GLPI tiene timeout de hasta 30 s. Como el proyecto corre en
hosting compartido y Windows (sin Redis ni workers dedicados), se usan
hilos daemon con higiene de conexiones.

En pruebas se corre en síncrono para que `mail.outbox` siga siendo
determinista. Se fuerza con `DOGGER_FONDO_ASINCRONO=False`.
"""

import logging
import sys
import threading

from django.conf import settings
from django.db import close_old_connections

logger = logging.getLogger(__name__)


def en_pruebas():
    """True bajo `manage.py test` (ahí todo va en síncrono)."""
    return any(a == "test" for a in sys.argv[1:2])


def en_fondo(func, *args, **kwargs):
    """Ejecuta `func` en un hilo daemon; devuelve el hilo o el resultado.

    En síncrono devuelve lo que retorne `func`; en hilo devuelve el
    objeto Thread (el resultado se pierde: úsalo solo para efectos
    secundarios como correos o avisos a GLPI).
    """
    if not getattr(settings, "DOGGER_FONDO_ASINCRONO", True) or en_pruebas():
        return func(*args, **kwargs)

    def _correr():
        try:
            close_old_connections()
            func(*args, **kwargs)
        except Exception:
            logger.exception("Fallo tarea de fondo %s", getattr(func, "__name__", func))
        finally:
            try:
                close_old_connections()
            except Exception:
                pass

    hilo = threading.Thread(
        target=_correr,
        daemon=True,
        name=f"fondo-{getattr(func, '__name__', 'tarea')}",
    )
    hilo.start()
    return hilo
