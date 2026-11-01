from django.db import migrations, models
import django.utils.timezone
import apps.tickets.cifrado


class Migration(migrations.Migration):
    dependencies = [("tickets", "0041_actividad_glpi_oculta_por_defecto")]
    operations = [
        migrations.CreateModel(
            name="TareaDiferida",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo", models.CharField(max_length=30)),
                ("datos", apps.tickets.cifrado.CampoCifrado()),
                ("estado", models.CharField(choices=[("pendiente", "Pendiente"), ("procesando", "Procesando"), ("completada", "Completada"), ("fallida", "Fallida"), ("revisar", "Resultado desconocido")], default="pendiente", max_length=16)),
                ("intentos", models.PositiveIntegerField(default=0)),
                ("disponible_en", models.DateTimeField(default=django.utils.timezone.now)),
                ("reservado_en", models.DateTimeField(blank=True, null=True)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
                ("ultimo_error", models.CharField(blank=True, default="", max_length=120)),
            ],
            options={"indexes": [models.Index(fields=["estado", "disponible_en"], name="tarea_estado_disponible_idx")]},
        ),
    ]
