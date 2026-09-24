from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_usuario_glpi_delete_preference"),
    ]

    operations = [
        migrations.AddField(
            model_name="usuario",
            name="ubicacion",
            field=models.CharField(
                "Ubicación / punto", max_length=120, blank=True, default=""
            ),
        ),
    ]