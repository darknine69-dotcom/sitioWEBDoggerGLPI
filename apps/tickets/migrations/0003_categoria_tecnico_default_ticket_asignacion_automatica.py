from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tickets", "0002_ticketadjunto_sincronizado_glpi_glpievento"),
    ]

    operations = [
        migrations.AddField(
            model_name="categoria",
            name="tecnico_default",
            field=models.ForeignKey(
                blank=True,
                db_column="TecnicoDefaultId",
                help_text="Se asigna automáticamente a los tickets nuevos de esta categoría",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="categorias_asignadas",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Técnico por defecto",
            ),
        ),
        migrations.AddField(
            model_name="ticket",
            name="asignacion_automatica",
            field=models.BooleanField(
                default=False,
                help_text="True cuando el técnico se asignó por regla de categoría",
                verbose_name="Asignación automática",
            ),
        ),
    ]
