# Al basar el voto en ticket, el único (tecnico, usuario) estorba: sin quitarlo
# nadie puede volver a calificar al mismo técnico en otro ticket, que es
# justamente lo que ahora se permite.
#
# La 0017 ya hizo este cambio (y lo hace bien en instalaciones nuevas), pero en
# la base de producción quedó el índice viejo puesto: la 0017 buscaba el nombre
# de la restricción dentro del valor que devuelve la introspección de SQL
# Server, y ahí el nombre es la clave del diccionario, no un campo. La lista le
# salía siempre vacía, así que se saltó el paso sin avisar.
#
# Esta migración deja el tema cerrado y es idempotente: si el índice viejo ya no
# está, no hace nada.
from django.db import migrations, models

INDICE_VIEJO = "uq_calificacion_tecnico_usuario"


def quitar_indice_viejo(apps, schema_editor):
    """Quita el único (tecnico, usuario), si todavía está."""
    from apps.tickets.models import CalificacionTecnico

    modelo = CalificacionTecnico
    with schema_editor.connection.cursor() as cursor:
        if modelo._meta.db_table not in schema_editor.connection.introspection.table_names(cursor):
            return
        # El nombre de la restricción es la clave del diccionario.
        unicos = {
            nombre.lower()
            for nombre, info in schema_editor.connection.introspection.get_constraints(
                cursor, modelo._meta.db_table
            ).items()
            if info.get("unique") and nombre
        }
    if INDICE_VIEJO not in unicos:
        return
    schema_editor.remove_constraint(
        modelo, models.UniqueConstraint(fields=("tecnico", "usuario"), name=INDICE_VIEJO)
    )
    print(f"  {modelo._meta.db_table}: quitado el índice único {INDICE_VIEJO}")


class Migration(migrations.Migration):
    # Igual que 0017: SQL Server no deshace DDL en una transacción.
    atomic = False

    dependencies = [
        ("tickets", "0017_calificacion_tecnico_por_ticket"),
    ]

    operations = [
        migrations.RunPython(quitar_indice_viejo, migrations.RunPython.noop),
    ]
