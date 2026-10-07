"""Subcategorías de Siesa ERP con nombre entendible.

Los módulos se llamaban como los ve el equipo de sistemas (Biable, POS-FE,
Manufactura...). Para quien reporta un problema eso no dice nada, así que se
renombran con el nombre del día a día. Se cambia solo el texto: el pk de cada
categoría se mantiene, de modo que los tickets, las reglas de prioridad y los
IDs de GLPI siguen apuntando a la misma categoría.
"""
from django.db import migrations

# (viejo, nuevo)
RENOMBRES = [
    ("Comercial", "Ventas y pedidos"),
    ("Manufactura", "Producción y bodega"),
    ("Financiero", "Contabilidad y pagos"),
    ("POS-FE", "Facturación electrónica"),
    ("Biable", "Reportes y tableros"),
    ("Otros sistemas", "Otros problemas de Siesa"),
]


def renombrar(apps, schema_editor):
    Categoria = apps.get_model("tickets", "Categoria")
    grupo = "SIESA ERP"
    for viejo, nuevo in RENOMBRES:
        # Sin acentos ni mayúsculas: el nombre puede haber quedado escrito
        # de otra forma en la base (por ejemplo "Produccion y bodega").
        Categoria.objects.filter(grupo__iexact=grupo, nombre__iexact=viejo).update(nombre=nuevo)


def revertir(apps, schema_editor):
    Categoria = apps.get_model("tickets", "Categoria")
    grupo = "SIESA ERP"
    for viejo, nuevo in RENOMBRES:
        Categoria.objects.filter(grupo__iexact=grupo, nombre__iexact=nuevo).update(nombre=viejo)


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0014_calificacion_tecnico_y_actividad_glpi"),
    ]

    operations = [
        migrations.RunPython(renombrar, revertir),
    ]
