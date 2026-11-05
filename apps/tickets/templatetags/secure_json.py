"""Render existing JSON strings safely inside HTML script elements."""
import json
import re

from django import template
from django.utils.html import escape, json_script
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def seguimiento_formato(valor):
    texto = str(escape(valor or ""))
    return mark_safe(re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", texto))


@register.simple_tag
def secure_json_script(serialized, element_id):
    return json_script(json.loads(serialized), element_id)
