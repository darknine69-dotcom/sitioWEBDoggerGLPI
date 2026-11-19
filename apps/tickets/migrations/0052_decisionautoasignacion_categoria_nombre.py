from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tickets", "0051_perfilautoasignacion_cobertura_general"),
    ]

    operations = [
        migrations.AddField(
            model_name="decisionautoasignacion",
            name="categoria_nombre",
            field=models.CharField(blank=True, default="", max_length=160),
        ),
    ]
