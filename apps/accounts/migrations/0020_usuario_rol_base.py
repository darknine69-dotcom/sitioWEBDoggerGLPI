from django.db import migrations, models


def conservar_rol_actual(apps, schema_editor):
    Usuario = apps.get_model("accounts", "Usuario")
    Usuario.objects.filter(cambio_rol_habilitado=True).update(rol_base=models.F("rol"))


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0019_usuario_cambio_rol_habilitado"),
    ]

    operations = [
        migrations.AddField(
            model_name="usuario",
            name="rol_base",
            field=models.CharField(
                blank=True,
                choices=[
                    ("admin", "Administrador"),
                    ("tecnico", "Técnico"),
                    ("usuario", "Punto de venta"),
                    ("observador", "Observador"),
                ],
                default="",
                help_text="Rol original que se conserva cuando la cuenta cambia de vista.",
                max_length=20,
                verbose_name="Rol base",
            ),
        ),
        migrations.RunPython(conservar_rol_actual, migrations.RunPython.noop),
    ]
