from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("programador", "0002_disponibilidadtecnico_hora"),
    ]

    operations = [
        migrations.AddField(
            model_name="calendarioevento",
            name="metadatos",
            field=models.JSONField(blank=True, default=dict, verbose_name="Metadatos"),
        ),
    ]
