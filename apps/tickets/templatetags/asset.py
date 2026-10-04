"""Tags para servir los archivos estaticos con control de cache.

Sin esto el navegador se queda con la copia vieja de un .js o .css aunque el
archivo ya se haya actualizado en el servidor, y las correcciones no se ven.
Cada URL lleva la fecha de modificacion del archivo, asi que al copiar el
cambio a otro equipo el navegador pide de inmediato la version nueva.
"""

import os
from django import template
from django.conf import settings
from django.templatetags.static import static

register = template.Library()


def _ruta_absoluta(ruta):
    """Busca el archivo en STATIC_ROOT y luego en STATICFILES_DIRS."""
    relativa = str(ruta).lstrip("/")
    candidatas = []
    static_root = getattr(settings, "STATIC_ROOT", None)
    if static_root:
        candidatas.append(os.path.join(str(static_root), relativa))
    for carpeta in getattr(settings, "STATICFILES_DIRS", []) or []:
        candidatas.append(os.path.join(str(carpeta), relativa))
    return next((c for c in candidatas if os.path.isfile(c)), None)


@register.simple_tag
def asset(ruta):
    """{% asset 'js/programador.js' %} -> /static/js/programador.js?v=1730000000"""
    url = static(ruta)
    completa = _ruta_absoluta(ruta)
    if completa:
        try:
            return "%s?v=%d" % (url, int(os.path.getmtime(completa)))
        except OSError:
            pass
    return url


@register.simple_tag
def asset_css(ruta):
    """Alias de :func:`asset`, para dejar claro el tipo en la plantilla."""
    return asset(ruta)
