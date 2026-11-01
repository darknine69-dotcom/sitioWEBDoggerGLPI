"""Render existing JSON strings safely inside HTML script elements."""
import json

from django import template
from django.utils.html import json_script

register = template.Library()


@register.simple_tag
def secure_json_script(serialized, element_id):
    return json_script(json.loads(serialized), element_id)
