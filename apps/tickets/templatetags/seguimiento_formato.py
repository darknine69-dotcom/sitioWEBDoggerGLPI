import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def seguimiento_formato(valor):
    """Renderiza únicamente negritas; el resto siempre se escapa."""
    texto = str(escape(valor or ""))
    texto = re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", texto)
    return mark_safe(texto)
