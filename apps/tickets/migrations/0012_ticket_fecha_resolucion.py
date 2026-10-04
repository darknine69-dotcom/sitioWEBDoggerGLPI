from django.db import migrations, models
from django.utils import timezone


def marcar_resueltos(apps, schema_editor):
    """Los tickets que ya estaban en "resuelto" sí se marcaron como tales.

    Con eso el distintivo "Resuelto" no se pierde en los tickets anteriores al
    campo. Los cerrados a los que no se pueda saber por qué camino llegaron se
    quedan sin marcar: es preferible no afirmar que se resolvieron.
    """
    Ticket = apps.get_model("tickets", "Ticket")
    Ticket.objects.filter(estado="resuelto", fecha_resolucion__isnull=True).update(
        fecha_resolucion=timezone.now()
    )


def quitar_marca(apps, schema_editor):
    Ticket = apps.get_model("tickets", "Ticket")
    Ticket.objects.filter(estado__in=["abierto", "en-progreso"]).update(
        fecha_resolucion=None
    )


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0011_remove_categoria_tecnicos_descripcion_ejemplos'),
    ]

    operations = [
        migrations.AddField(
            model_name='ticket',
            name='fecha_resolucion',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(marcar_resueltos, quitar_marca),
    ]
