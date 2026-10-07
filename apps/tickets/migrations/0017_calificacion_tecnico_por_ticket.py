# Los votos de "me gusta" dejan de ser solo al técnico en general: también
# pueden quedar atados a un ticket resuelto (el detalle del ticket), para que
# la barra cuente el trabajo de verdad y no una opinión suelta.
#
# Esta migración está escrita a mano, paso a paso y preguntando antes de tocar
# nada, por dos razones:
#
# 1. La base de producción es SQL Server, que no tiene transacciones para el
#    DDL. Si algo falla a mitad de camino, la base queda con parte del cambio
#    hecho y la migración sin registrar; con `migrate` normal, el siguiente
#    intento revienta al encontrar la columna o el índice ya hechos.
# 2. Los datos viejos no están limpios: hay tickets con el correo del
#    solicitante en NULL, y ahí fue donde se cayó la versión anterior
#    (`AttributeError: 'NoneType' object has no attribute 'strip'`).
#
# Por eso cada paso pregunta primero si falta lo que tiene que hacer y, si ya
# está hecho, no lo repite. Así `migrate` se puede volver a correr las veces
# que haga falta y siempre termina bien, tanto en una base limpia como en una
# que quedó a medias.
import django.db.models.deletion
from django.db import migrations, models

INDICE_VIEJO = "uq_calificacion_tecnico_usuario"
INDICE_NUEVO = "uq_calificacion_tecnico_usuario_ticket"


def _modelo(apps):
    """Modelo con el que se dibuja el SQL.

    A propósito NO se usa el modelo histórico de `apps`: a Django le llega el
    estado de *antes* de esta migración, y en ese estado todavía no existe el
    campo ticket, así que no hay forma de dibujar ni el ALTER ni el índice que
    lo usan. El modelo real siempre lo tiene y su tabla es la misma
    (db_table no cambia en 0017). Se importa aquí dentro y no arriba del todo
    para no cargarlo al importar el archivo de la migración.
    """
    from apps.tickets.models import CalificacionTecnico

    return CalificacionTecnico


def _tabla_existe(schema_editor, modelo):
    with schema_editor.connection.cursor() as cursor:
        return modelo._meta.db_table in schema_editor.connection.introspection.table_names(cursor)


def _unicos(schema_editor, modelo):
    """Nombres de los índices/constraints únicos de la tabla del modelo.

    El nombre es la *clave* del diccionario que devuelve la introspección, no
    un campo dentro del valor: por eso se leen las claves y no los valores. Si
    se busca "name" dentro de cada entrada (que no existe), la lista sale
    siempre vacía y esta migración cree que no hay nada que hacer.
    """
    with schema_editor.connection.cursor() as cursor:
        encontrados = schema_editor.connection.introspection.get_constraints(
            cursor, modelo._meta.db_table
        ).items()
        return {nombre.lower() for nombre, info in encontrados if info.get("unique") and nombre}


def _modelo_reducido(modelo, sin_indices=(), sin_campos=()):
    """Copia del modelo con menos índices o campos, solo para pintar SQL.

    En SQLite (y en cualquier motor que rehaga la tabla) quitar una restricción
    única o una columna significa recrear la tabla, y al recrearla Django vuelve
    a escribir *todas* las restricciones del modelo que se le pasó. Si ese modelo
    todavía trae la restricción que se está borrando, o el campo que se está
    quitando, el SQL sale con columnas que ya no existen y revienta
    con `FieldDoesNotExist`. Con esta copia se le entrega exactamente lo que
    debe quedar en la tabla, que es lo que hace Django internamente en sus
    propias migraciones.
    """
    from django.apps.registry import Apps

    # Los fields van clonados para no tocar los del modelo real (si se
    # reutilizaran los mismos, Django les cambiaría el `model` y el modelo de
    # verdad quedaría con las relaciones revueltas). Un clon pierde la relación
    # ya resuelta y la deja como texto, así que se vuelve a apuntar al modelo
    # real: si no, falla al buscar 'accounts.usuario' en el registro.
    cuerpo = {}
    for campo in modelo._meta.local_concrete_fields:
        if campo.name in sin_campos:
            continue
        copia = campo.clone()
        if campo.is_relation and copia.remote_field is not None:
            # Un clon deja la relación sin resolver (model en texto y
            # field_name vacío), así que se copian tal cual del original.
            copia.remote_field.model = campo.remote_field.model
            copia.remote_field.field_name = campo.remote_field.field_name
        cuerpo[campo.name] = copia
    cuerpo["__module__"] = modelo.__module__
    cuerpo["Meta"] = type(
        "Meta",
        (),
        {
            "app_label": modelo._meta.app_label,
            "db_table": modelo._meta.db_table,
            "managed": modelo._meta.managed,
            "unique_together": tuple(tuple(u) for u in modelo._meta.unique_together),
            "indexes": tuple(modelo._meta.indexes),
            "constraints": tuple(
                c for c in modelo._meta.constraints if c.name not in sin_indices
            ),
            # Un registro propio y desechable: si se usara el global, este
            # modelo falso de usar y tirar se apuntaría en él y Django
            # avisaría (y podría enredar consultas posteriores).
            "apps": Apps(),
        },
    )
    return type(modelo._meta.object_name, modelo.__bases__, cuerpo)


def _tiene_columna(schema_editor, modelo, campo):
    with schema_editor.connection.cursor() as cursor:
        columnas = {
            c.name.lower()
            for c in schema_editor.connection.introspection.get_table_description(
                cursor, modelo._meta.db_table
            )
        }
    return campo.lower() in columnas


def asegurar_columna(apps, schema_editor):
    """Agrega ticket_id si no está. Nullable, tal como el campo del modelo."""
    modelo = _modelo(apps)
    if not _tabla_existe(schema_editor, modelo):
        return
    if not _tiene_columna(schema_editor, modelo, "ticket_id"):
        schema_editor.add_field(modelo, modelo._meta.get_field("ticket"))


def quitar_columna(apps, schema_editor):
    """Al revertir: el voto vuelve a ser solo del técnico, así que la columna
    se va (los NULL se pierden con ella)."""
    modelo = _modelo(apps)
    if not _tabla_existe(schema_editor, modelo):
        return
    if _tiene_columna(schema_editor, modelo, "ticket_id"):
        schema_editor.remove_field(
            _modelo_reducido(modelo, sin_indices=(INDICE_NUEVO,)),
            modelo._meta.get_field("ticket"),
        )


def asegurar_indices(apps, schema_editor):
    """Quita el único (tecnico, usuario) y deja el de (tecnico, usuario, ticket).

    El viejo estorba: sin él no se podría votar al mismo técnico en dos tickets
    distintos. El nuevo, en SQL Server, también sigue dejando un solo voto
    general por persona y técnico, porque allí los nulos de un índice único se
    consideran iguales entre sí.
    """
    modelo = _modelo(apps)
    if not _tabla_existe(schema_editor, modelo):
        return
    unicos = _unicos(schema_editor, modelo)
    if INDICE_VIEJO in unicos:
        schema_editor.remove_constraint(
            _modelo_reducido(modelo, sin_indices=(INDICE_VIEJO,)),
            models.UniqueConstraint(fields=("tecnico", "usuario"), name=INDICE_VIEJO),
        )
    if INDICE_NUEVO not in _unicos(schema_editor, modelo):
        schema_editor.add_constraint(
            modelo,
            models.UniqueConstraint(fields=("tecnico", "usuario", "ticket"), name=INDICE_NUEVO),
        )


def revertir_indices(apps, schema_editor):
    """Al revertir el paso de los índices, el nuevo se va y vuelve el viejo."""
    modelo = _modelo(apps)
    if not _tabla_existe(schema_editor, modelo):
        return
    if INDICE_NUEVO in _unicos(schema_editor, modelo):
        schema_editor.remove_constraint(
            _modelo_reducido(modelo, sin_indices=(INDICE_NUEVO,)),
            models.UniqueConstraint(
                fields=("tecnico", "usuario", "ticket"), name=INDICE_NUEVO
            ),
        )
    if INDICE_VIEJO not in _unicos(schema_editor, modelo):
        schema_editor.add_constraint(
            modelo, models.UniqueConstraint(fields=("tecnico", "usuario"), name=INDICE_VIEJO)
        )


def atar_votos_existentes(apps, schema_editor):
    """Pega cada voto general al único ticket resuelto que le corresponde.

    Los tickets no guardan al usuario como clave foránea sino el correo, así
    que el cruce es por correo. Solo se atan los votos que no dejan duda: si la
    persona tiene un único ticket resuelto de ese técnico. Cuando hay varios, o
    ninguno, cualquier elección sería inventada y el voto se queda como general,
    que es lo que siempre se mostró.
    """
    Calificacion = _modelo(apps)
    # Los tickets y los usuarios sí se leen con los modelos del estado: son los
    # que reflejan la base en este punto de la historia. Con el modelo real de
    # usuario la consulta pediría columnas (teléfono, avatar, género) que se
    # agregaron después y aquí todavía no existen.
    Ticket = apps.get_model("tickets", "Ticket")
    Usuario = apps.get_model("accounts", "Usuario")
    if not _tabla_existe(schema_editor, Calificacion) or not _tiene_columna(
        schema_editor, Calificacion, "ticket_id"
    ):
        return

    correos = {}
    for u in Usuario.objects.all().only("id", "email"):
        correos[u.pk] = (u.email or "").strip().lower()

    por_persona = {}
    for t in Ticket.objects.filter(
        estado__in=["resuelto", "cerrado"], tecnico_asignado__isnull=False
    ).exclude(solicitante_email__isnull=True).exclude(solicitante_email=""):
        correo = (t.solicitante_email or "").strip().lower()
        if correo:
            por_persona.setdefault((correo, t.tecnico_asignado_id), []).append(t.pk)

    atados = 0
    votos = Calificacion.objects.filter(ticket__isnull=True).only("id", "usuario_id", "tecnico_id")
    for voto in votos:
        correo = correos.get(voto.usuario_id, "")
        if not correo:
            continue
        candidatas = por_persona.get((correo, voto.tecnico_id), [])
        if len(candidatas) == 1:
            Calificacion.objects.filter(pk=voto.pk).update(ticket_id=candidatas[0])
            atados += 1
    if atados:
        print(f"  {Calificacion._meta.db_table}: {atados} voto(s) atado(s) a su ticket resuelto")


class Migration(migrations.Migration):
    # SQL Server no deshace el DDL dentro de una transacción, así que cada paso
    # va por su cuenta. Los pasos son repetibles a propósito: si uno falla, se
    # vuelve a correr migrate y completa solo lo que faltaba.
    atomic = False

    dependencies = [
        ("tickets", "0016_facturacion_electronica_unificada"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        # Paso 1: la columna. El estado del modelo se declara aparte del SQL que
        # la crea, para que Django sepa que el campo existe sin intentar
        # crearlo otra vez y reventar en una base a medias.
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(asegurar_columna, quitar_columna)
            ],
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="calificaciontecnico", name=INDICE_VIEJO
                ),
                migrations.AddField(
                    model_name="calificaciontecnico",
                    name="ticket",
                    field=models.ForeignKey(
                        blank=True,
                        help_text="Vacío cuando el voto es al técnico en general, no a un ticket.",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="calificaciones_tecnicos",
                        to="tickets.ticket",
                        verbose_name="Ticket",
                    ),
                ),
            ],
        ),
        # Paso 2: los votos viejos que sí se pueden identificar.
        migrations.RunPython(atar_votos_existentes, migrations.RunPython.noop),
        # Paso 3: los índices, ya con los votos atados (en SQL Server el índice
        # único nuevo no admite dos nulos en la misma terna).
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(asegurar_indices, revertir_indices)
            ],
            state_operations=[
                migrations.AddConstraint(
                    model_name="calificaciontecnico",
                    constraint=models.UniqueConstraint(
                        fields=("tecnico", "usuario", "ticket"), name=INDICE_NUEVO
                    ),
                )
            ],
        ),
    ]
