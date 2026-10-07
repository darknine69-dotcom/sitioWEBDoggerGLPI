"""Una sola categoría de facturación electrónica, dentro de SIESA ERP.

Había dos para lo mismo: «POS-FE» (módulo de Siesa) y «POS Facturación
Electrónica» (bajo Puntos de venta). Quien reportaba una factura rechazada o un
CUFE que no llegaba tenía que adivinar cuál tomar. Ahora queda una, con el
nombre que usa la gente y con el detalle de que sirve tanto en el ERP como en
el POS.

La que sobra no se borra: se deja inactiva para que los tickets que ya la
usaron sigan mostrando su categoría. Si ya estaba renombrada por la 0015,
también se acepta ese nombre.
"""
from django.db import migrations

VIEJOS_SIESA = ["POS-FE", "Caja y facturación electrónica", "Facturación electrónica"]
NUEVO = "Facturación electrónica"
VIEJA_POS = ["POS Facturacion Electronica", "POS Facturación Electrónica", "POS Facturación Electrónica"]


def unificar(apps, schema_editor):
    Categoria = apps.get_model("tickets", "Categoria")

    destino = None
    for nombre in VIEJOS_SIESA:
        destino = destino or Categoria.objects.filter(
            grupo__iexact="SIESA ERP", nombre__iexact=nombre
        ).first()

    if destino is not None:
        # Si la de Puntos de venta tenía el ID de GLPI y esta no, se le cede:
        # la categoría que queda es la que debe seguir sincronizando.
        for nombre in VIEJA_POS:
            vieja = Categoria.objects.filter(
                grupo__iexact="Puntos de venta", nombre__iexact=nombre
            ).first()
            if vieja is None:
                continue
            if not destino.glpi_category_id and vieja.glpi_category_id:
                destino.glpi_category_id = vieja.glpi_category_id
            vieja.activo = False
            vieja.save(update_fields=["activo", "glpi_category_id"])
        destino.nombre = NUEVO
        destino.save(update_fields=["nombre", "glpi_category_id"])
    else:
        # Base sin la fila de Siesa (catalogo raro): se desactiva la de POS.
        Categoria.objects.filter(
            grupo__iexact="Puntos de venta", nombre__in=VIEJA_POS
        ).update(activo=False)


def separar(apps, schema_editor):
    Categoria = apps.get_model("tickets", "Categoria")
    Categoria.objects.filter(
        grupo__iexact="SIESA ERP", nombre__iexact=NUEVO
    ).update(nombre="POS-FE")
    Categoria.objects.filter(
        grupo__iexact="Puntos de venta", nombre__in=VIEJA_POS
    ).update(activo=True)


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0015_subcategorias_siesa_entendibles"),
    ]

    operations = [
        migrations.RunPython(unificar, separar),
    ]
