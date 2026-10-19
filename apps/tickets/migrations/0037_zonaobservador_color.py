from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0036_ticketcomentario_es_presion"),
    ]

    operations = [
        migrations.AddField(
            model_name="zonaobservador",
            name="color",
            field=models.CharField(
                blank=True,
                db_column="Color",
                default="",
                help_text="Color que eligió el observador para su carpeta (hex).",
                max_length=7,
                verbose_name="Color de la carpeta",
            ),
        ),
    ]
