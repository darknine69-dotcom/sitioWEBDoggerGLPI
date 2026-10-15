"""Freno de fuerza bruta sin dependencias nuevas.

Usa el caché de Django (memoria local por proceso) para contar intentos
por llave (IP, cuenta, etc.) en una ventana deslizante. Al superar el
tope, bloquea por un cooldown. Pensado para login, reset de contraseña
y consulta de tickets: barato, sin Redis, sin tablas.

En producción con varios workers cada uno lleva su contador (el bloqueo
es aproximado, no exacto). Con un solo proceso —el despliegue actual—
es exacto.
"""

import time

from django.core.cache import cache

PREFIJO = "throttle"


def _llave(nombre, identidad):
    return f"{PREFIJO}:{nombre}:{identidad}"


def _ventana(cacheada):
    ahora = time.monotonic()
    if not isinstance(cacheada, list):
        return []
    # Solo intentos dentro de la ventana (se guarda la expiración con cada uno).
    return [expira for expira in cacheada if expira > ahora]


def registrar_intento(nombre, identidad, max_intentos=5, ventana_seg=600, bloqueo_seg=900):
    """Suma un intento fallido. Devuelve True si quedó bloqueado."""
    llave = _llave(nombre, identidad)
    ahora = time.monotonic()
    intentos = _ventana(cache.get(llave, []))
    intentos.append(ahora + ventana_seg)
    if len(intentos) >= max_intentos:
        # Bloqueo: se guarda una marca con su propio TTL.
        cache.set(llave + ":bloqueado", True, bloqueo_seg)
        cache.set(llave, [], bloqueo_seg)
        return True
    cache.set(llave, intentos, ventana_seg)
    return False


def bloqueado(nombre, identidad):
    """True si la identidad está en cooldown."""
    return bool(cache.get(_llave(nombre, identidad) + ":bloqueado"))


def limpiar(nombre, identidad):
    """Olvida los intentos (al lograr entrar, para no castigar de más)."""
    cache.delete_many([_llave(nombre, identidad), _llave(nombre, identidad) + ":bloqueado"])


def ip_del_request(request):
    """IP real detrás de proxy (X-Forwarded-For) o directa."""
    xff = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    return xff or request.META.get("REMOTE_ADDR", "?")
