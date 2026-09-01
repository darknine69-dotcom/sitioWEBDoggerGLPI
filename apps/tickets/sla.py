"""
Acuerdos de Nivel de Servicio (ANS) del helpdesk Dogger.

Horas objetivo de resolución según la prioridad automática. Cada categoría
puede definir su propio ANS (Categoria.ans_horas); si no lo define, se usa
el valor por prioridad de esta tabla.
"""
from django.db.models import Case, IntegerField, Value, When

# Horas ANS por prioridad (usado como fallback por categoría).
ANS_POR_PRIORIDAD = {
    "urgente": 4,
    "alta": 8,
    "media": 24,
    "baja": 48,
}

PRIORIDAD_ORDEN = ["urgente", "alta", "media", "baja"]


def horas_por_prioridad(prioridad):
    """Horas ANS base para una prioridad."""
    return ANS_POR_PRIORIDAD.get(prioridad, 24)


def orden_prioridad_annotation():
    """
    Anotación de Django para ordenar por prioridad (urgente -> baja).
    Uso: Ticket.objects.annotate(_prioridad_orden=orden_prioridad_annotation())
         .order_by("_prioridad_orden", "-fecha_creacion")
    """
    return Case(
        *[When(prioridad=p, then=Value(i)) for i, p in enumerate(PRIORIDAD_ORDEN)],
        default=Value(99),
        output_field=IntegerField(),
    )


def formatear_duracion(delta):
    """Convierte un timedelta a texto legible: '2d 3h', '1h 20min', '45min'."""
    total_min = max(0, int(delta.total_seconds() // 60))
    if total_min < 1:
        return "menos de 1min"
    dias, rest = divmod(total_min, 1440)
    horas, mins = divmod(rest, 60)
    partes = []
    if dias:
        partes.append(f"{dias}d")
    if horas:
        partes.append(f"{horas}h")
    if mins and not dias:
        partes.append(f"{mins}min")
    return " ".join(partes)