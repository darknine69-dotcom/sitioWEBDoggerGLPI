from django.db import migrations, models


def ocultar_actividad_existente(apps, schema_editor):
    ConfigSitio = apps.get_model("tickets", "ConfigSitio")
    ConfigSitio.objects.update(panel_mostrar_actividad_glpi=False)


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0040_categoria_descripcion"),
    ]

    operations = [
        migrations.AlterField(
            model_name="configsitio",
            name="panel_mostrar_actividad_glpi",
            field=models.BooleanField(
                default=False,
                help_text="Si está apagada, el bloque «Actividad reciente GLPI» no aparece en el panel de nadie.",
                verbose_name="Mostrar actividad de GLPI en los paneles",
            ),
        ),
        migrations.RunPython(ocultar_actividad_existente, migrations.RunPython.noop),
    ]
