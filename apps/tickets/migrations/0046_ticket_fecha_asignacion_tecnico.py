from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tickets", "0045_configsitio_escalamiento_inactividad")]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="fecha_asignacion_tecnico",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
