from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0020_usuario_rol_base"),
    ]

    operations = [
        migrations.AddField(
            model_name="usuario",
            name="atajos_rapidos",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "Claves del botón X de atajos, elegidas en Ajustes de cuenta. "
                    "Vacío = los que trae su rol por defecto."
                ),
                verbose_name="Atajos rápidos",
            ),
        ),
        migrations.AddField(
            model_name="usuario",
            name="atajos_enlaces",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "Enlaces que la persona agrega a mano al botón X: "
                    "lista de {nombre, url, icono}."
                ),
                verbose_name="Enlaces propios de atajos",
            ),
        ),
    ]
