"""Etiquetas de plantilla para la navegación principal.

El estado activo se resuelve comparando la URL actual con una lista de
nombres de vista, para no depender de un ``{% block nav_* %}`` opcional en
cada plantilla (antes 10 páginas quedaban sin resaltar).
"""

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


def _url_actual(context):
    request = context.get("request")
    match = getattr(request, "resolver_match", None)
    return getattr(match, "url_name", None)


@register.simple_tag(takes_context=True)
def nav_active(context, *url_names):
    """Devuelve ``is-active`` si la página actual está en la lista."""
    actual = _url_actual(context)
    # El texto es fijo (nunca viene de la petición) y lleva espacio inicial para
    # poder pegarlo detrás de class="..." sin tener que escribirlo en la plantilla.
    return mark_safe(" is-active" if actual and actual in url_names else "")


@register.simple_tag(takes_context=True)
def nav_current(context, *url_names):
    """Devuelve ``aria-current="page"`` si la página actual está en la lista."""
    actual = _url_actual(context)
    return mark_safe(' aria-current="page"' if actual and actual in url_names else "")
